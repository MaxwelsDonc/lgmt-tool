"""Back-translation fidelity audit.

For every follow-up premise/conclusion whose text was re-generated from a
transformed FOL formula, ask an LLM judge whether the natural language
faithfully preserves the FOL structure (reuses the FOL2NL_validate prompt).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from json_repair import repair_json
from loguru import logger

from lgmt.core.structure import MetamorphicGroups
from lgmt.models.base import LLMClient
from lgmt.prompts.fol2nl_validate import SYSTEM_PROMPT, get_FOL2NL_validate_prompt

_PREMISE_TAG = re.compile(r"^\[Changed_(\d+)\]\s*")
_CONCLUSION_TAG = re.compile(r"^\[Changed_conclusion\]\s*")


def _parse_verdict(raw: str) -> bool:
    obj = json.loads(repair_json(raw.strip().strip("`")))
    return str(obj.get("label", "")).strip().lower() == "true"


def audit_mgs(
    mgs: List[MetamorphicGroups],
    client: LLMClient,
    model: str,
    max_workers: int = 8,
) -> List[Dict[str, Any]]:
    """Audit all changed follow-up texts; returns one record per item."""

    def _audit_item(mg: MetamorphicGroups):
        followup = mg.followup_case
        items = []
        for i, text in enumerate(followup.premises_text):
            match = _PREMISE_TAG.match(text)
            if match:
                items.append((f"premise_{i}", followup.premises_logic[i], text))
        if _CONCLUSION_TAG.match(followup.conclusion_text):
            items.append(
                ("conclusion", followup.conclusion_logic, followup.conclusion_text)
            )

        records = []
        for kind, fol, nl in items:
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
                    "nl": re.sub(r"^\[(Changed_\d+|Changed_conclusion)\]\s*", "", nl),
                    "valid": valid,
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
    total = len(records)
    valid = sum(1 for r in records if r.get("valid"))
    return {"total": total, "valid": valid, "fidelity": valid / total if total else 0.0}
