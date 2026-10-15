"""Deterministic offline LLM client for demos and tests.

Two personas are provided:

- ``consistent``: always returns the logically correct verdict (the ground
  truth label attached to the test case).
- ``flawed``: answers correctly on source cases but deliberately returns an
  inconsistent verdict on follow-up cases of selected MR categories,
  simulating a model whose reasoning is not invariant under the MR
  transformation.
"""
import json
from typing import Any, Dict, Optional, Sequence

from lgmt.models.base import LLMClient
from lgmt.utils.labels import canonical_label

_FLIP_MAP = {"True": "False", "False": "True", "Unknown": "False"}


class MockLLMClient(LLMClient):
    """Offline, deterministic mock client. No network, no keys.

    Two personas are provided (see the module docstring for details):

    - ``consistent`` — always returns the logically correct verdict;
    - ``flawed`` — correct on source cases but inconsistent on follow-ups
      of the configured MR categories.
    """

    #: Default MR categories the ``flawed`` persona gets wrong on follow-ups.
    DEFAULT_FLIP_CATEGORIES = ("E", "P")

    def __init__(
        self,
        persona: str = "consistent",
        flip_categories: Sequence[str] = DEFAULT_FLIP_CATEGORIES,
    ):
        """Initialize the mock client.

        Args:
            persona: ``"consistent"`` (always correct) or ``"flawed"``
                (inconsistent on follow-ups of ``flip_categories``).
            flip_categories: MR category letters (``"E"``, ``"S"``,
                ``"P"``, ``"C"``) the flawed persona gets wrong on
                follow-up cases.
        """
        if persona not in ("consistent", "flawed"):
            raise ValueError(f"Unknown persona: {persona!r} (use 'consistent' or 'flawed')")
        self.persona = persona
        self.flip_categories = tuple(c.upper() for c in flip_categories)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _category(mr_index: str) -> str:
        parts = str(mr_index or "").split("-")
        return parts[1][0].upper() if len(parts) >= 2 and parts[1] else "?"

    def _infer_label(self, context: Dict[str, Any]) -> str:
        ground_truth = canonical_label(context.get("ground_truth"))
        if self.persona == "consistent":
            return ground_truth
        role = context.get("role", "source")
        mr_index = str(context.get("mr_index", ""))
        if role == "followup" and self._category(mr_index) in self.flip_categories:
            return _FLIP_MAP.get(ground_truth, "False")
        return ground_truth

    # ------------------------------------------------------------------ #
    # interface
    # ------------------------------------------------------------------ #
    def generate(
        self,
        prompt_data: Dict[str, str],
        model: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cot: bool = False,
        **_unused: Any,
    ) -> Optional[str]:
        """Return the persona-dictated verdict as a JSON string.

        Implements :meth:`~lgmt.models.base.LLMClient.generate`; dispatches
        on ``context["task"]`` (``infer`` / ``logic2nl`` / ``validate``).
        """
        context = context or {}
        task = context.get("task", "infer")

        if task == "infer":
            label = self._infer_label(context)
            if cot:
                role = context.get("role", "source")
                reasoning = (
                    f"[mock:{self.persona}] Step 1: parse premises. "
                    f"Step 2: apply rules. Step 3: verdict is {label}."
                )
                return json.dumps({"reasoning": reasoning, "label": label})
            return json.dumps({"label": label})

        if task == "logic2nl":
            return json.dumps(
                {"translation": "[mock] faithful mock translation of the transformed formula."}
            )

        if task == "validate":
            # mock back-translations always preserve FOL structure
            return json.dumps({"label": "True"})

        raise ValueError(f"MockLLMClient: unknown task {task!r}")
