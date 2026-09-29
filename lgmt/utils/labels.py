"""Label canonicalization shared by inference, metrics, and reporting.

The paper and the tool use "Unknown" for the undetermined verdict; older
inference prompts and result files may carry the legacy "Uncertain" tag.
Both spellings are accepted and normalized to "Unknown".
"""

_VALID_LABELS = ("True", "False", "Unknown")
_LEGACY_ALIASES = {"Uncertain": "Unknown"}


def canonical_label(label) -> str:
    """Normalize a raw label to one of ``True`` / ``False`` / ``Unknown``.

    Unrecognized or missing values map to ``Unknown``.
    """
    if label is None:
        return "Unknown"
    text = str(label).strip()
    if not text:
        return "Unknown"
    text = text[0].upper() + text[1:].lower()
    if text in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[text]
    return text if text in _VALID_LABELS else "Unknown"
