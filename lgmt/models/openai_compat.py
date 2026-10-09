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

from lgmt.models.base import LLMClient

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
        lowered = model_name.lower()
        return any(marker in lowered for marker in REASONING_MARKERS)

    def resolve_model(self, model: str) -> str:
        """Map a short alias (e.g. ``chatgpt``) to the served model name."""
        return self.models_map.get(model, model)

    def generate(
        self,
        prompt_data: Dict[str, str],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        stream: bool = False,
        return_raw: bool = False,
        max_tokens: int = 4096,
        **_unused: Any,
    ) -> Optional[str]:
        """Unified generation interface.

        Args:
            prompt_data: ``{"system": ..., "user": ...}``
            model: model alias or served model name
            temperature: ignored for reasoning models (they reject it)
            max_retries: retries with exponential back-off on failure
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

        kwargs: Dict[str, Any] = {"model": model_name, "messages": messages, "stream": stream}
        if not self.is_reasoning_model(model_name):
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                if stream:
                    full_content = ""
                    print(f"\n[Stream Start - {model}]: ", end="", flush=True)
                    for chunk in response:
                        delta_content = getattr(chunk.choices[0].delta, "content", "")
                        if delta_content:
                            full_content += delta_content
                            print(delta_content, end="", flush=True)
                    print("\n[Stream End]\n")
                    final_raw = response if return_raw else None
                    return (full_content, final_raw) if return_raw else full_content

                full_content = response.choices[0].message.content.strip()
                return (full_content, response) if return_raw else full_content

            except Exception as e:
                logger.warning(f"Model: {model} | attempt {attempt + 1}: {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                else:
                    return (None, None) if return_raw else None

        return (None, None) if return_raw else None
