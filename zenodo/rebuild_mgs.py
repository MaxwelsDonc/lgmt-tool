#!/usr/bin/env python3
"""Rebuild the LogicNLI/ProverQA metamorphic groups from the Zenodo index.

License background: the LogicNLI and ProverQA upstream repositories ship no
LICENSE, so their derived MGs cannot be redistributed. The Zenodo package
therefore ships only an *index* (source-case ids, content hashes, MR
references, and RNG seeds). This script reconstructs the full MG jsonl on
a user's machine from:

  1. a source-case JSONL in LGMT ``source_test_case`` format — either the
     files shipped in this repository's ``data/source_test_case/`` or files
     rebuilt from the original datasets with the conversion scripts in
     ``zenodo/scripts/`` (``--from-original``), and
  2. ``mgs_logicnli_proverqa_index.jsonl`` from the Zenodo package.

The FOLIO-derived MGs are redistributed directly (CC BY-SA 4.0) and do not
need rebuilding.

Usage:
    # from source-test-case files
    python zenodo/rebuild_mgs.py \
        --index zenodo/dist/mgs_logicnli_proverqa_index.jsonl \
        --source-cases data/source_test_case/logicnli_source_test_case.jsonl \
                       data/source_test_case/proverqa_source_test_case.jsonl \
        --out rebuilt_mgs.jsonl

    # from the original LogicNLI/ProverQA downloads
    python zenodo/rebuild_mgs.py \
        --index zenodo/dist/mgs_logicnli_proverqa_index.jsonl \
        --from-original logic_nli_dir proverQA_dir \
        --work-dir /tmp/lgmt_rebuild \
        --out rebuilt_mgs.jsonl
"""
import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lgmt.core.structure import MetamorphicGroups, TestCase  # noqa: E402
from lgmt.mrs import get_mr  # noqa: E402

ZENODO_SCRIPTS = Path(__file__).resolve().parent / "scripts"


def source_fingerprint(tc: TestCase) -> str:
    import hashlib

    payload = {
        "premises_logic": tc.premises_logic,
        "conclusion_logic": tc.conclusion_logic,
        "label": tc.metadata.get("label", ""),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_source_cases(paths) -> Dict[Tuple[str, str, Optional[str]], TestCase]:
    """Index source cases by (normalized data_source, str(example_id), original_file)."""
    index: Dict[Tuple[str, str, Optional[str]], TestCase] = {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                tc = TestCase(**data)
                ds = str(tc.metadata.get("data_source", "")).lower()
                key = (ds, str(tc.metadata.get("example_id")), tc.metadata.get("original_file"))
                index[key] = tc
    return index


def lookup_source(index, rec) -> TestCase:
    ds = str(rec.get("data_source", "")).lower()
    eid = str(rec.get("example_id"))
    candidates = [
        (ds, eid, rec.get("original_file")),
        (ds, eid, None),
    ]
    for key in candidates:
        if key in index:
            return index[key]
    raise KeyError(
        f"source case not found for index record {rec.get('mg_id')}: "
        f"data_source={rec.get('data_source')} example_id={rec.get('example_id')} "
        f"original_file={rec.get('original_file')}"
    )


def build_source_cases_from_originals(
    logicnli_dir: Path,
    proverqa_dir: Path,
    work_dir: Path,
    splits: Tuple[str, ...] = ("dev", "test", "train"),
) -> List[Path]:
    """Run the archived conversion/cleaning chain on original downloads.

    LogicNLI chain (scripts archived from the research repository):
      original/{dev,test,train}_{language,logic}.json
        -> clean_logicnli_conflicts.py (Z3 contradiction filtering)
        -> {split}_{language,logic}_clean.jsonl
        -> convert_logicnli_files.py (facts/rules -> FOL test cases, "dirty")
        -> clean_logicnli_condlicts_phase2.py (Z3 self-consistency filtering)
        -> logicnli_source_test_case.jsonl
    ProverQA chain:
      {easy,medium,hard}.json -> convert_proverQA_files.py
        -> proverqa_source_test_case.jsonl
    """
    sys.path.insert(0, str(ZENODO_SCRIPTS))
    work_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    # ---- LogicNLI ----
    clean_dir = work_dir / "logicnli_clean"
    clean_dir.mkdir(exist_ok=True)
    from clean_logicnli_conflicts import clean_dataset

    for split in splits:
        lang_in = logicnli_dir / f"{split}_language.json"
        logic_in = logicnli_dir / f"{split}_logic.json"
        if not (lang_in.exists() and logic_in.exists()):
            print(f"  skipping LogicNLI split {split}: original files not found")
            continue
        clean_dataset(
            str(lang_in),
            str(logic_in),
            str(clean_dir / f"{split}_language_clean.jsonl"),
            str(clean_dir / f"{split}_logic_clean.jsonl"),
        )

    from convert_logicnli_files import LogicNLIConverter

    converter = LogicNLIConverter()
    dirty_path = work_dir / "logicnli_source_test_case_dirty.jsonl"
    fail_path = work_dir / "logicnli_parse_failures_dirty.jsonl"
    with open(dirty_path, "w", encoding="utf-8") as out_f, open(
        fail_path, "w", encoding="utf-8"
    ) as fail_f:
        for split in splits:
            lang = clean_dir / f"{split}_language_clean.jsonl"
            logic = clean_dir / f"{split}_logic_clean.jsonl"
            if lang.exists() and logic.exists():
                converter.process_split(
                    str(lang), str(logic), out_f, fail_f, split=split
                )
    print(f"  LogicNLI dirty cases: {dirty_path}")

    from clean_logicnli_condlicts_phase2 import clean_conflicts_phase2

    logicnli_out = work_dir / "logicnli_source_test_case.jsonl"
    clean_conflicts_phase2(str(dirty_path), str(logicnli_out))
    outputs.append(logicnli_out)

    # ---- ProverQA ----
    from convert_proverQA_files import process_proverqa_files

    proverqa_out = work_dir / "proverqa_source_test_case.jsonl"
    process_proverqa_files(
        input_dir=str(proverqa_dir),
        output_path=str(proverqa_out),
        failure_path=str(work_dir / "proverqa_parse_failures.jsonl"),
    )
    outputs.append(proverqa_out)
    return outputs


def apply_transform(rec: dict, src: TestCase) -> TestCase:
    """Rebuild the follow-up case: recorded params for random MRs, otherwise
    the deterministic ``lgmt.mrs`` transform."""
    t = rec.get("transform") or {}
    kind = t.get("kind")
    if kind == "premise_order":
        order = t["premise_order"]
        return TestCase(
            premises_logic=[src.premises_logic[i] for i in order],
            premises_text=[src.premises_text[i] for i in order],
            conclusion_logic=src.conclusion_logic,
            conclusion_text=src.conclusion_text,
            metadata=src.metadata.copy(),
        )
    if kind == "duplicate":
        dup = t["duplicated_indices"]
        return TestCase(
            premises_logic=src.premises_logic + [src.premises_logic[i] for i in dup],
            premises_text=src.premises_text + [src.premises_text[i] for i in dup],
            conclusion_logic=src.conclusion_logic,
            conclusion_text=src.conclusion_text,
            metadata=src.metadata.copy(),
        )
    if kind == "add_premise":
        return TestCase(
            premises_logic=src.premises_logic + [t["added_logic"]],
            premises_text=src.premises_text + [t["added_text"]],
            conclusion_logic=src.conclusion_logic,
            conclusion_text=src.conclusion_text,
            metadata=src.metadata.copy(),
        )
    if kind == "fuse":
        i, j = t["fused_indices"]
        drop = {i, j}
        return TestCase(
            premises_logic=[p for k, p in enumerate(src.premises_logic) if k not in drop]
            + [t["fused_logic"]],
            premises_text=[p for k, p in enumerate(src.premises_text) if k not in drop]
            + [t["fused_text"]],
            conclusion_logic=src.conclusion_logic,
            conclusion_text=src.conclusion_text,
            metadata=src.metadata.copy(),
        )
    mr_index = rec["mr_index"]
    if mr_index not in _MR_CACHE:
        _MR_CACHE[mr_index] = get_mr(mr_index)
    return _MR_CACHE[mr_index].transform(src)


_MR_CACHE: Dict[str, object] = {}


def rebuild(index_path: str, source_paths, out_path: str, limit: int = 0) -> dict:
    index = load_source_cases(source_paths)
    stats = {"rebuilt": 0, "sha_mismatch": 0, "missing": 0}
    start = time.perf_counter()
    with open(index_path, "r", encoding="utf-8") as fin, open(
        out_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            if not line.strip():
                continue
            rec = json.loads(line)
            try:
                src = lookup_source(index, rec)
            except KeyError as e:
                stats["missing"] += 1
                print(f"WARNING: {e}")
                continue
            if source_fingerprint(src) != rec["source_sha256"]:
                stats["sha_mismatch"] += 1
                print(
                    f"WARNING: sha mismatch for {rec.get('mg_id')} "
                    f"(example {rec.get('example_id')}) — source case content "
                    "differs from the indexed one; skipping"
                )
                continue
            followup = apply_transform(rec, src)
            mg = MetamorphicGroups(
                source_case=src,
                followup_case=followup,
                mr_name=get_mr(rec["mr_index"]).name,
                metadata={"mr_index": rec["mr_index"]},
            )
            fout.write(
                json.dumps(asdict(mg), ensure_ascii=False) + "\n"
            )
            stats["rebuilt"] += 1
            if limit and stats["rebuilt"] >= limit:
                break
    stats["elapsed_s"] = round(time.perf_counter() - start, 1)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", required=True, help="Zenodo index jsonl.")
    parser.add_argument(
        "--source-cases",
        nargs="+",
        default=None,
        help="source_test_case-format jsonl files (repo data/ or rebuilt).",
    )
    parser.add_argument(
        "--from-original",
        nargs=2,
        metavar=("LOGICNLI_DIR", "PROVERQA_DIR"),
        default=None,
        help="Directories with the ORIGINAL LogicNLI / ProverQA downloads; "
        "runs the zenodo/scripts conversion chain first (needs z3-solver).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(".") / "rebuild_work",
        help="Intermediate outputs for --from-original.",
    )
    parser.add_argument("--out", required=True, help="Output MG jsonl.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Rebuild only the first N index records (smoke tests).",
    )
    args = parser.parse_args()

    source_paths = list(args.source_cases or [])
    if args.from_original:
        logicnli_dir, proverqa_dir = (Path(p) for p in args.from_original)
        print("building source cases from original downloads ...")
        source_paths = build_source_cases_from_originals(
            logicnli_dir, proverqa_dir, args.work_dir
        )
    if not source_paths:
        parser.error("provide --source-cases or --from-original")

    print(f"rebuilding MGs from {args.index} ...")
    stats = rebuild(args.index, source_paths, args.out, limit=args.limit)
    print(
        f"rebuilt {stats['rebuilt']} MGs -> {args.out} "
        f"({stats['elapsed_s']}s; missing={stats['missing']}, "
        f"sha_mismatch={stats['sha_mismatch']})"
    )
    return 0 if stats["rebuilt"] else 1


if __name__ == "__main__":
    sys.exit(main())
