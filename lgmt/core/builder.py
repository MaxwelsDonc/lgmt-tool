"""Build metamorphic groups (MGs) from source entailment test cases.

Pipeline: for each source case, find applicable MRs, apply the first
``max_per_case`` of them to obtain follow-up cases, and optionally
"realize" the follow-up natural language via an LLM back-translation
(Logic-to-NL). Without realization the follow-up keeps the tagged FOL
skeleton text produced by the transform (``--no-realize`` mode).
"""
import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, Tuple

from json_repair import repair_json
from loguru import logger

from lgmt.core.structure import MetamorphicGroups, MetamorphicRelation, TestCase
from lgmt.models.base import LLMClient
from lgmt.mrs import ALL_MRS
from lgmt.prompts.logic2nl import SYSTEM_PROMPT as LOGIC2NL_SYSTEM_PROMPT
from lgmt.prompts.logic2nl import get_logic2NL_prompt

_PREMISE_TAG = re.compile(r"^\[Changed_(\d+)\]\s*")
_CONCLUSION_TAG = re.compile(r"^\[Changed_conclusion\]\s*")

RealizeFn = Callable[[TestCase, TestCase], TestCase]


def build_metamorphic_groups(
    source_cases: List[TestCase],
    mr_list: Optional[List[MetamorphicRelation]] = None,
    max_per_case: int = 1,
    seed: int = 42,
    realize_fn: Optional[RealizeFn] = None,
    max_workers: int = 1,
) -> List[MetamorphicGroups]:
    """Apply MRs to source cases and collect metamorphic groups.

    Args:
        source_cases: source entailment test cases
        mr_list: MRs to try (default: all 20)
        max_per_case: max MGs produced per source case
        seed: RNG seed for MR selection order and shuffle-based MRs
        realize_fn: optional Logic-to-NL back-translation; when ``None``
            the follow-up keeps the FOL-skeleton text with ``[Changed_*]``
            tags
        max_workers: parallel build workers (safe for LLM-backed realize)
    """
    mrs = mr_list or ALL_MRS

    def _build_one(args: Tuple[int, TestCase]) -> List[MetamorphicGroups]:
        case_idx, case = args
        rng = random.Random(f"{seed}:{case_idx}")
        candidates = list(mrs)
        rng.shuffle(candidates)
        groups: List[MetamorphicGroups] = []
        for mr in candidates:
            if len(groups) >= max_per_case:
                break
            random.seed(f"{seed}:{case_idx}:{mr.index}")
            try:
                if not mr.check_applicability(case):
                    continue
                followup = mr.transform(case)
            except Exception as e:
                logger.warning(f"MR {mr.index} failed on case {case_idx}: {e}")
                continue
            if realize_fn is not None:
                try:
                    followup = realize_fn(case, followup)
                except Exception as e:
                    logger.warning(f"Realize failed on case {case_idx}: {e}")
            groups.append(
                MetamorphicGroups(
                    source_case=case,
                    followup_case=followup,
                    mr_name=mr.name,
                    metadata={
                        "mg_id": f"mg_{case_idx + 1}_{len(groups) + 1}",
                        "mr_index": mr.index,
                        "mr_name": mr.name,
                        "data_source": case.metadata.get("data_source", ""),
                    },
                )
            )
        return groups

    indexed = list(enumerate(source_cases))
    all_groups: List[MetamorphicGroups] = []
    if max_workers and max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_build_one, item) for item in indexed]
            for future in as_completed(futures):
                all_groups.extend(future.result())
    else:
        for item in indexed:
            all_groups.extend(_build_one(item))

    all_groups.sort(key=lambda g: g.metadata.get("mg_id", ""))
    return all_groups


def make_realize_fn(
    client: LLMClient,
    model: str,
    retries: int = 3,
) -> RealizeFn:
    """Create a Logic-to-NL back-translation function backed by an LLM.

    Every follow-up premise/conclusion still carrying a ``[Changed_*]``
    tag is translated from its transformed FOL formula into natural
    language; the tag is dropped after translation.
    """

    def _translate(original_fol: str, original_nl: str, transformed_fol: str) -> str:
        prompt = {
            "system": LOGIC2NL_SYSTEM_PROMPT,
            "user": get_logic2NL_prompt(
                original_fol=original_fol,
                transformed_fol=transformed_fol,
                original_nl=original_nl,
            ),
        }
        last_error: Optional[Exception] = None
        for attempt in range(retries):
            try:
                raw = client.generate(
                    prompt, model=model, context={"task": "logic2nl"}, max_retries=0
                )
                if not raw:
                    raise ValueError("Empty response")
                obj = json.loads(repair_json(raw.strip().strip("`")))
                translation = obj.get("translation", "").strip()
                if not translation:
                    raise ValueError(f"Empty translation: {raw}")
                return translation
            except Exception as e:
                last_error = e
                logger.warning(f"logic2NL retry {attempt + 1}/{retries}: {e}")
        raise RuntimeError(f"logic2NL failed after {retries} retries: {last_error}")

    lock = threading.Lock()

    def realize(source: TestCase, followup: TestCase) -> TestCase:
        texts = list(followup.premises_text)
        for i, text in enumerate(texts):
            match = _PREMISE_TAG.match(text)
            if not match:
                continue
            src_idx = int(match.group(1))
            if src_idx >= len(source.premises_logic):
                continue
            with lock:
                translated = _translate(
                    source.premises_logic[src_idx],
                    source.premises_text[src_idx],
                    followup.premises_logic[i],
                )
            texts[i] = translated
        followup.premises_text = texts

        conc_match = _CONCLUSION_TAG.match(followup.conclusion_text)
        if conc_match:
            with lock:
                followup.conclusion_text = _translate(
                    source.conclusion_logic,
                    source.conclusion_text,
                    followup.conclusion_logic,
                )
        return followup

    return realize
