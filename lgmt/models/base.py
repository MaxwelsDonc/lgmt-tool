"""Abstract interface for LLM clients used by the LGMT pipeline."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Union


class LLMClient(ABC):
    """Minimal contract every LGMT model client must satisfy.

    ``generate`` receives a ``prompt_data`` dict with ``system`` and ``user``
    keys and returns the model's raw text output (``None`` on total failure).
    Implementations may accept additional keyword arguments (e.g. ``context``
    for mock clients); callers pass them optionally.
    """

    @abstractmethod
    def generate(
        self,
        prompt_data: Dict[str, str],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        ...
