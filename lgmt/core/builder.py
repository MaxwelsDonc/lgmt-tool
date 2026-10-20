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
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def _progress_tick(progress_callback: Optional[Callable[[int], None]]) -> None:
    if progress_callback is not None:
        try:
            progress_callback(1)
        except Exception:
            pass


def synthesize_missing_logic(
    records: List[dict],
    translator: Optional[FOLTranslator] = None,
    extractor: Optional[UnstructuredExtractor] = None,
    retries: int = 2,
    progress_callback: Optional[Callable[[int], None]] = None,
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
        _progress_tick(progress_callback)

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
    """Apply MRs to source cases and collect metamorphic groups.

    Each source case is paired with the first ``max_per_case`` applicable
    MRs (candidate order shuffled deterministically per case).

    Args:
        source_cases: entailment test cases to transform.
        mr_list: relations to try (defaults to every registered MR).
        max_per_case: maximum groups created per source case.
        seed: deterministic shuffle/transform seed.
        realize_fn: optional logic-to-NL back-translation applied to each
            follow-up case.
        max_workers: thread-pool size for the per-case loop.

    Returns:
        The built groups, sorted by ``mg_id``.
    """
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
        # Every statement re-generated below is recorded so that
        # ``lgmt audit`` can later check it against its FOL formula.
        realized: List[Dict[str, Any]] = []

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
            realized.append(
                {
                    "kind": f"premise_{i}",
                    "fol": followup.premises_logic[i],
                    "nl": translated,
                }
            )
        followup.premises_text = texts

        conc_match = _CONCLUSION_TAG.match(followup.conclusion_text)
        if conc_match:
            with lock:
                translated = _translate(
                    source.conclusion_logic,
                    source.conclusion_text,
                    followup.conclusion_logic,
                )
            followup.conclusion_text = translated
            realized.append(
                {
                    "kind": "conclusion",
                    "fol": followup.conclusion_logic,
                    "nl": translated,
                }
            )

        if realized:
            # copy-on-write: some MRs deep-copy a case, but never mutate a
            # metadata dict shared with the source case.
            followup.metadata = dict(followup.metadata or {})
            followup.metadata["realized_items"] = (
                list(followup.metadata.get("realized_items") or []) + realized
            )
        return followup

    return realize


def parse_and_normalize_cases(
    raw_input: str,
    translator: Optional[FOLTranslator] = None,
    extractor: Optional[UnstructuredExtractor] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> List[TestCase]:
    """Sniff the input format and normalize it into ``TestCase`` objects.

    Branch A (JSONL): every non-empty line starts with ``{`` — parse per line;
    records may carry logic fields, text fields, or ``raw_text``.
    Branch B (plain text): split into blank-line-separated blocks; a block
    whose every line parses as FOL becomes a pure-FOL case (last line is the
    conclusion), anything else is treated as an unstructured NL paragraph.
    No ``input_mode`` is needed — the backend decides.
    """
    from lgmt.utils.labels import canonical_label

    text = (raw_input or "").strip()
    if not text:
        raise ValueError("no test cases found — provide at least one test case")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    records: List[dict] = []

    if all(ln.lstrip().startswith("{") for ln in lines):
        # ---- Branch A: JSONL ----
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {lineno}: invalid JSON ({e})") from e
            if not isinstance(obj, dict):
                raise ValueError(f"line {lineno}: expected a JSON object")
            has_logic = bool(obj.get("premises_logic") and obj.get("conclusion_logic"))
            has_text = bool(obj.get("premises_text") and obj.get("conclusion_text"))
            has_raw = bool(obj.get("raw_text"))
            if not (has_logic or has_text or has_raw):
                raise ValueError(
                    f"line {lineno}: each record needs ('premises_text' & "
                    "'conclusion_text'), ('premises_logic' & 'conclusion_logic'), "
                    "or 'raw_text'"
                )
            records.append(obj)
    else:
        # ---- Branch B: plain text / FOL blocks / unstructured paragraphs ----
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        for block in blocks:
            block_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if len(block_lines) >= 2 and all(looks_like_fol(ln) for ln in block_lines):
                records.append(
                    {
                        "premises_logic": block_lines[:-1],
                        "conclusion_logic": block_lines[-1],
                        "premises_text": block_lines[:-1],
                        "conclusion_text": block_lines[-1],
                        "metadata": {"label": "Unknown"},
                    }
                )
            else:
                records.append({"raw_text": block, "metadata": {"label": "Unknown"}})

    # friendly up-front error when natural language needs a model we don't have
    needs_llm = False
    for r in records:
        if r.get("premises_logic") and r.get("conclusion_logic"):
            continue
        pt = [str(p).strip() for p in (r.get("premises_text") or []) if str(p).strip()]
        ct = str(r.get("conclusion_text") or "").strip()
        if pt and ct and all(looks_like_fol(p) for p in pt) and looks_like_fol(ct):
            continue
        needs_llm = True
        break
    if needs_llm and translator is None:
        raise ValueError(
            "Natural-language or unstructured cases require a real LLM API key & model to "
            "extract and synthesize FOL formulas. Either configure an API key & model, "
            "or provide premises_logic/conclusion_logic fields for offline mock runs."
        )

    normalized = synthesize_missing_logic(
        records,
        translator=translator,
        extractor=extractor,
        progress_callback=progress_callback,
    )
    if not normalized:
        raise ValueError(
            "Could not construct valid NLTK FOL formulas from the provided cases. "
            "Check your input sentences or FOL syntax."
        )

    cases: List[TestCase] = []
    for obj in normalized:
        premises_logic = list(obj["premises_logic"])
        conclusion_logic = str(obj["conclusion_logic"])
        cases.append(
            TestCase(
                premises_logic=premises_logic,
                conclusion_logic=conclusion_logic,
                premises_text=list(obj.get("premises_text") or premises_logic),
                conclusion_text=str(obj.get("conclusion_text") or conclusion_logic),
                metadata={
                    **(obj.get("metadata") or {}),
                    "label": canonical_label((obj.get("metadata") or {}).get("label")),
                },
            )
        )
    return cases
