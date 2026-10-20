"""Back-translation fidelity audit.

``build-mgs`` records every follow-up premise/conclusion that the LLM
re-realized from its transformed FOL formula in
``followup_case.metadata["realized_items"]``.  This module replays those
items through a judge model and asks whether the natural language still
preserves the FOL structure (reuses the FOL2NL_validate prompt).
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from json_repair import repair_json
from loguru import logger

from lgmt.core.structure import MetamorphicGroups
from lgmt.models.base import LLMClient
from lgmt.prompts.fol2nl_validate import SYSTEM_PROMPT, get_FOL2NL_validate_prompt


def _parse_verdict(raw: str) -> bool:
    obj = json.loads(repair_json(raw.strip().strip("`")))
    return str(obj.get("label", "")).strip().lower() == "true"


def _realized_items(mg: MetamorphicGroups) -> List[Dict[str, Any]]:
    """Return the re-generated statements recorded for ``mg``'s follow-up."""
    items = (mg.followup_case.metadata or {}).get("realized_items") or []
    return [item for item in items if item.get("fol") and item.get("nl")]


def audit_mgs(
    mgs: List[MetamorphicGroups],
    client: LLMClient,
    model: str,
    max_workers: int = 8,
) -> List[Dict[str, Any]]:
    """Audit every re-generated follow-up text for FOL→NL faithfulness.

    Only statements recorded by the realizer (``realized_items``) are
    audited: they are the ones whose natural language was written by an
    LLM and therefore may have drifted from the transformed formula.
    Groups built with ``--no-realize`` have no such items and yield no
    records.

    Args:
        mgs: metamorphic groups to audit.
        client: LLM client used as the judge.
        model: judge model name.
        max_workers: thread-pool size.

    Returns:
        One record per audited item, each with ``mg_id``, ``mr_index``,
        ``kind`` (``"premise_<i>"`` or ``"conclusion"``), ``fol``, ``nl``,
        a boolean ``valid`` verdict, and ``judge_model``.
    """

    def _audit_item(mg: MetamorphicGroups) -> List[Dict[str, Any]]:
        records = []
        for item in _realized_items(mg):
            kind = item.get("kind", "")
            fol = item["fol"]
            nl = item["nl"]
            prompt = {
                "system": SYSTEM_PROMPT,
                "user": get_FOL2NL_validate_prompt(fol=fol, nl=nl),
            }
            try:
                raw = client.generate(
                    prompt, model=model, context={"task": "validate"}, max_retries=0
                )
                valid = _parse_verdict(raw) if raw else False
            except Exception as e:
                logger.warning(f"Audit failed | {mg.metadata.get('mg_id')} | {kind}: {e}")
                valid = False
            records.append(
                {
                    "mg_id": mg.metadata.get("mg_id", ""),
                    "mr_index": mg.metadata.get("mr_index", ""),
                    "kind": kind,
                    "fol": fol,
                    "nl": nl,
                    "valid": valid,
                    "judge_model": model,
                }
            )
        return records

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_audit_item, mg) for mg in mgs]
        for future in as_completed(futures):
            results.extend(future.result())
    results.sort(key=lambda r: (r["mg_id"], r["kind"]))
    return results


def audit_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate audit records into ``total``/``valid``/``fidelity``.

    ``fidelity`` is ``None`` when there is nothing to audit, so callers can
    distinguish "no re-generated statements" from "0% faithful".
    """
    total = len(records)
    valid = sum(1 for r in records if r.get("valid"))
    return {"total": total, "valid": valid, "fidelity": valid / total if total else None}
