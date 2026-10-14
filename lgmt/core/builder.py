"""Build metamorphic groups (MGs) from source entailment test cases.

Pipeline:
1. Normalize source records across four input forms:
   - Unstructured text (`raw_text`) -> extracted into `premises_text` + `conclusion_text`
   - Pure FOL (`premises_logic` + `conclusion_logic` only) -> text fields populated
   - Pure NL (`premises_text` + `conclusion_text` in English/Chinese) -> FOL synthesized & NLTK-validated
   - Dual NL + FOL -> used directly
2. Find applicable MRs and rewrite FOL syntax trees to obtain follow-up cases.
3. Optionally "realize" modified follow-up formulas (`[Changed_*]`) into natural language.
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
from lgmt.prompts.nl2fol import (
    EXTRACT_SYSTEM_PROMPT,
    SYSTEM_PROMPT as NL2FOL_SYSTEM_PROMPT,
    get_nl2fol_prompt,
    get_unstructured_extract_prompt,
)

_PREMISE_TAG = re.compile(r"^\[Changed_(\d+)\]\s*")
_CONCLUSION_TAG = re.compile(r"^\[Changed_conclusion\]\s*")
_FOL_HINT = re.compile(
    r"(?:\ball\s+[a-z]\b|\bexists\s+[a-z]\b|->|<->|[∀∃¬∧∨→↔]|[A-Z][A-Za-z0-9_]*\([a-zA-Z0-9_,\s]+\))"
)

RealizeFn = Callable[[TestCase, TestCase], TestCase]
FOLTranslator = Callable[[List[str], str], dict]
UnstructuredExtractor = Callable[[str], dict]


def looks_like_fol(s: str) -> bool:
    """Return True if string ``s`` is a valid NLTK FOL formula with logical structure."""
    if not s or not isinstance(s, str):
        return False
    text = s.strip()
    if not _FOL_HINT.search(text):
        return False
    norm = (
        text.replace("∀", "all ")
        .replace("∃", "exists ")
        .replace("→", "->")
        .replace("↔", "<->")
        .replace("¬", "-")
        .replace("∧", "&")
        .replace("∨", "|")
    )
    try:
        from nltk.sem.logic import ApplicationExpression, Expression

        expr = Expression.fromstring(norm)
        # A bare single word like " Socrates " is a VariableExpression, not a formula
        if not isinstance(expr, ApplicationExpression) and not any(
            tok in norm for tok in ("all ", "exists ", "->", "<->", "&", "|", "-")
        ):
            return False
        return True
    except Exception:
        return False


def make_unstructured_extractor(client: LLMClient, model: str) -> UnstructuredExtractor:
    """Extract structured `premises_text` and `conclusion_text` from a free-text paragraph."""

    def extract(raw_text: str) -> dict:
        prompt = {
            "system": EXTRACT_SYSTEM_PROMPT,
            "user": get_unstructured_extract_prompt(raw_text),
        }
        raw = client.generate(
            prompt, model=model, context={"task": "extract_nl"}, max_retries=0
        )
        if not raw:
            raise ValueError("empty extraction response")
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        obj = json.loads(repair_json(text))
        if (
            not isinstance(obj, dict)
            or not obj.get("premises_text")
            or not obj.get("conclusion_text")
        ):
            raise ValueError(f"unexpected extraction shape: {obj!r}")
        return {
            "premises_text": [str(p).strip() for p in obj["premises_text"] if str(p).strip()],
            "conclusion_text": str(obj["conclusion_text"]).strip(),
        }

    return extract


def make_nl2fol_translator(client: LLMClient, model: str) -> FOLTranslator:
    """Default NL→FOL translator backed by an LLM (see lgmt.prompts.nl2fol)."""

    def translate(premises_text: List[str], conclusion_text: str) -> dict:
        prompt = {
            "system": NL2FOL_SYSTEM_PROMPT,
            "user": get_nl2fol_prompt(premises_text, conclusion_text),
        }
        raw = client.generate(
            prompt, model=model, context={"task": "nl2fol"}, max_retries=0
        )
        if not raw:
            raise ValueError("empty translation response")
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        obj = json.loads(repair_json(text))
        if not isinstance(obj, dict) or "premises_logic" not in obj or "conclusion_logic" not in obj:
            raise ValueError(f"unexpected translation shape: {obj!r}")
        return obj

    return translate


def synthesize_missing_logic(
    records: List[dict],
    translator: Optional[FOLTranslator] = None,
    extractor: Optional[UnstructuredExtractor] = None,
    retries: int = 2,
) -> List[dict]:
    """Normalize raw source-case records across all 4 input types:

    1. Unstructured ``raw_text`` -> split into ``premises_text`` + ``conclusion_text`` via ``extractor``.
    2. Pure FOL (``premises_logic`` + ``conclusion_logic`` without ``premises_text``) ->
       populate ``premises_text`` / ``conclusion_text`` from the formulas.
    3. Pure FOL typed inside ``premises_text`` / ``conclusion_text`` -> auto-detected
       via ``looks_like_fol`` and copied into ``premises_logic`` / ``conclusion_logic``.
    4. Pure NL (English / Chinese / bilingual ``premises_text`` + ``conclusion_text``) ->
       translated to NLTK-validated FOL via ``translator``.
    """
    from nltk.sem.logic import LogicParser

    parser = LogicParser()
    filled = []
    for rec in records:
        rec = dict(rec)

        # Step 1: Unstructured paragraph extraction if needed
        if (
            not rec.get("premises_logic")
            and not rec.get("premises_text")
            and rec.get("raw_text")
        ):
            if extractor is None:
                logger.warning(
                    "Case dropped: unstructured 'raw_text' requires a model extractor"
                )
                continue
            try:
                extracted = extractor(str(rec["raw_text"]))
                rec["premises_text"] = extracted["premises_text"]
                rec["conclusion_text"] = extracted["conclusion_text"]
            except Exception as e:
                logger.warning(f"Unstructured extraction failed (case dropped): {e}")
                continue

        # Step 2: If logic is present but text is missing (Pure FOL record), fill text
        if rec.get("premises_logic") and rec.get("conclusion_logic"):
            if not rec.get("premises_text"):
                rec["premises_text"] = [str(f) for f in rec["premises_logic"]]
            if not rec.get("conclusion_text"):
                rec["conclusion_text"] = str(rec["conclusion_logic"])
            filled.append(rec)
            continue

        premises_text = [str(p).strip() for p in (rec.get("premises_text") or []) if str(p).strip()]
        conclusion_text = str(rec.get("conclusion_text") or "").strip()
        if not premises_text or not conclusion_text:
            logger.warning(
                "Case dropped: needs non-empty premises_text/conclusion_text or premises_logic/conclusion_logic"
            )
            continue

        # Step 3: Check if the user typed FOL formulas directly into premises_text/conclusion_text
        if all(looks_like_fol(p) for p in premises_text) and looks_like_fol(conclusion_text):
            norm_fn = lambda s: (
                s.replace("∀", "all ")
                .replace("∃", "exists ")
                .replace("→", "->")
                .replace("↔", "<->")
                .replace("¬", "-")
                .replace("∧", "&")
                .replace("∨", "|")
            )
            rec["premises_logic"] = [norm_fn(p) for p in premises_text]
            rec["conclusion_logic"] = norm_fn(conclusion_text)
            filled.append(rec)
            continue

        # Step 4: Pure NL -> synthesize FOL via translator
        if translator is None:
            logger.warning(
                "Case dropped: NL→FOL synthesis requires a real model translator"
            )
            continue

        ok = False
        last_error: Optional[Exception] = None
        for _attempt in range(retries + 1):
            try:
                result = translator(list(premises_text), conclusion_text)
                new_logic = [str(f) for f in result["premises_logic"]]
                new_conclusion = str(result["conclusion_logic"])
                if len(new_logic) != len(premises_text):
                    raise ValueError(
                        f"premise count mismatch: {len(new_logic)} formulas "
                        f"for {len(premises_text)} sentences"
                    )
                for formula in new_logic + [new_conclusion]:
                    parser.parse(formula)
                filled.append(
                    {
                        **rec,
                        "premises_text": premises_text,
                        "conclusion_text": conclusion_text,
                        "premises_logic": new_logic,
                        "conclusion_logic": new_conclusion,
                    }
                )
                ok = True
                break
            except Exception as e:
                last_error = e
        if not ok:
            logger.warning(
                f"NL→FOL synthesis failed after {retries + 1} attempts "
                f"(case dropped): {last_error}"
            )
    return filled


def build_metamorphic_groups(
    source_cases: List[TestCase],
    mr_list: Optional[List[MetamorphicRelation]] = None,
    max_per_case: int = 1,
    seed: int = 42,
    realize_fn: Optional[RealizeFn] = None,
    max_workers: int = 1,
) -> List[MetamorphicGroups]:
    """Apply MRs to source cases and collect metamorphic groups."""
    mrs = mr_list or ALL_MRS
    _transform_lock = threading.Lock()

    def _build_one(args: Tuple[int, TestCase]) -> List[MetamorphicGroups]:
        case_idx, case = args
        rng = random.Random(f"{seed}:{case_idx}")
        candidates = list(mrs)
        rng.shuffle(candidates)
        groups: List[MetamorphicGroups] = []
        for mr in candidates:
            if len(groups) >= max_per_case:
                break
            try:
                with _transform_lock:
                    random.seed(f"{seed}:{case_idx}:{mr.index}")
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
    language (matching the language of ``original_nl``); the tag is
    dropped after translation.
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
