"""OpenAI-compatible chat client with connection pooling and retries.

Works with any endpoint speaking the OpenAI chat-completions protocol:
OpenAI itself, proxies, vLLM, Ollama, DeepSeek, etc. Configuration comes
from explicit arguments, a YAML config file, or ``LGMT_*`` environment
variables (see :mod:`lgmt.config`).
"""
import time
from typing import Any, Dict, Optional

from loguru import logger

import httpx
from openai import OpenAI

from lgmt.models.base import LLMClient, NonRetryableRequestError

#: Substrings marking reasoning models that reject sampling parameters.
REASONING_MARKERS = ("reasoner", "o1", "o3", "o4", "r1", "deepseek-reasoner")


class OpenAICompatClient(LLMClient):
    """Generic OpenAI-protocol client with pooled connections and retry."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        models_map: Optional[Dict[str, str]] = None,
        timeout: float = 600.0,
        max_connections: int = 1500,
        max_keepalive_connections: int = 500,
    ):
        """Initialize the client.

        Args:
            api_key: API key for the endpoint (required).
            base_url: OpenAI-compatible base URL (required).
            models_map: optional short-name -> served-model-name aliases.
            timeout: HTTP timeout in seconds per request.
            max_connections: httpx connection-pool limit.
            max_keepalive_connections: httpx keep-alive connection limit.
        """
        if not api_key:
            raise ValueError(
                "Missing API key. Set the LGMT_API_KEY environment variable, "
                "or provide 'model.api_key' in the config file "
                "(copy config.example.yaml)."
            )
        if not base_url:
            raise ValueError(
                "Missing base URL. Set the LGMT_BASE_URL environment variable, "
                "or provide 'model.base_url' in the config file "
                "(copy config.example.yaml)."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.models_map = models_map or {}

        custom_http_client = httpx.Client(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            timeout=timeout,
        )
        self.client = OpenAI(
            api_key=self.api_key, base_url=self.base_url, http_client=custom_http_client
        )
        logger.info(f"OpenAICompat client initialized. Endpoint: {self.base_url}")

    @staticmethod
    def is_reasoning_model(model_name: str) -> bool:
        """Return ``True`` if ``model_name`` marks a reasoning model.

        Reasoning models reject sampling parameters, so ``temperature``
        and ``max_tokens`` are not sent to them.
        """
        lowered = model_name.lower()
        return any(marker in lowered for marker in REASONING_MARKERS)

    def resolve_model(self, model: str) -> str:
        """Map a short alias (e.g. ``chatgpt``) to the served model name.

        Falls back to ``model`` itself when no alias matches.
        """
        return self.models_map.get(model, model)

    def generate(
        self,
        prompt_data: Dict[str, str],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        max_tokens: int = 4096,
        **_unused: Any,
    ) -> Optional[str]:
        """Unified generation interface.

        Args:
            prompt_data: ``{"system": ..., "user": ...}``
            model: model alias or served model name
            temperature: ignored for reasoning models (they reject it)
            max_retries: retries with exponential back-off on retryable
                failures (429/5xx/network); 401/402/403 fail fast
            max_tokens: token budget per call; doubled up to 8192 when a
                response comes back truncated (``finish_reason="length"``)

        Raises:
            NonRetryableRequestError: on authentication/billing errors and
                on truncated responses that stay empty after the budget is
                raised — the message carries the provider's error detail.
        """
        if model is None:
            raise ValueError("OpenAICompatClient.generate requires a model name")
        model_name = self.resolve_model(model)

        messages = []
        system_text = (
            prompt_data.get("system", "") if isinstance(prompt_data, dict) else ""
        )
        user_text = prompt_data.get("user", "") if isinstance(prompt_data, dict) else ""
        if system_text:
            messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": user_text})

        max_tokens_eff = max_tokens
        last_error: Optional[BaseException] = None
        for attempt in range(max_retries + 1):
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                # reasoning models still honor max_tokens (budget for
                # reasoning_content); omitting it risks truncation
                "max_tokens": max_tokens_eff,
            }
            if not self.is_reasoning_model(model_name):
                kwargs["temperature"] = temperature
            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as e:
                detail = self._error_detail(e)
                if self._is_non_retryable(e):
                    raise NonRetryableRequestError(detail) from e
                last_error = e
                logger.warning(
                    f"Model: {model} | attempt {attempt + 1}: {detail}"
                )
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None

            choice = response.choices[0]
            content = (getattr(choice.message, "content", None) or "").strip()
            reasoning = getattr(choice.message, "reasoning_content", None)
            finish = getattr(choice, "finish_reason", None)
            if finish == "length":
                # truncated: even a partial reasoning_content is incomplete —
                # raise the budget and retry instead of accepting it
                if max_tokens_eff < 8192:
                    max_tokens_eff = min(max_tokens_eff * 2, 8192)
                    logger.warning(
                        f"Model: {model} | response truncated "
                        f"(finish_reason=length); raising max_tokens to "
                        f"{max_tokens_eff} and retrying"
                    )
                    last_error = None
                    continue
                raise NonRetryableRequestError(
                    "response truncated (finish_reason=length) — "
                    "consider raising max_tokens"
                )
            if not content and reasoning:
                # reasoning models (deepseek-reasoner/-flash, OpenAI o-series)
                # may emit the whole answer in reasoning_content with content
                # left empty
                content = str(reasoning).strip()
            if content:
                return content
            raise NonRetryableRequestError(
                f"empty response content (finish_reason={finish!r})"
            )

        return None

    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_non_retryable(exc: BaseException) -> bool:
        """401/402/403 must fail fast; 429 and transient errors retry."""
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        return status in (401, 402, 403)

    @staticmethod
    def _error_detail(exc: BaseException) -> str:
        """Best-effort extraction of provider error detail, including
        non-standard bodies like ``{"statusCode":402,"message":"..."}``."""
        parts = [f"{type(exc).__name__}: {exc}"]
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                body = response.json()
            except Exception:
                body = None
            if isinstance(body, dict):
                status = body.get("statusCode") or body.get("status") or getattr(
                    response, "status_code", None
                )
                message = body.get("message") or body.get("error")
                if status:
                    parts.append(f"statusCode={status}")
                if message:
                    parts.append(f"message={message}")
            elif getattr(response, "status_code", None):
                parts.append(f"statusCode={response.status_code}")
        return " | ".join(parts)
