#!/usr/bin/env python3
"""Build the Zenodo upload package for the LGMT dataset.

License-aware packaging:
  - FOLIO is CC BY-SA 4.0: derived MGs are redistributed directly.
  - LogicNLI / ProverQA have no license in their repositories: derived MGs
    are NOT redistributed. Instead we ship an *index* (source-case IDs,
    content hashes, MR references, and RNG seeds) plus the conversion
    scripts under zenodo/scripts/, so users can rebuild the full MGs from
    their own copy of the original datasets (see zenodo/rebuild_mgs.py).
  - Inference results and audit labels are produced by us and are
    redistributed directly.

Outputs (under --out, default zenodo/dist/):
  mgs_folio.jsonl                         FOLIO-derived MGs (CC BY-SA 4.0)
  mgs_logicnli_proverqa_index.jsonl       rebuild index for the other two
  inference_results/<model>/*.jsonl       per-model, per-prompting verdicts
  audit_labels.jsonl                      back-translation audit labels
  README.md, LICENSE.folio.txt            package docs
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lgmt.core.structure import MetamorphicGroups, TestCase  # noqa: E402
from lgmt.mrs import get_mr  # noqa: E402

KBS_CODE = Path(__file__).resolve().parents[2] / "KBS_LGMT" / "code"

#: MRs whose transform consumes global randomness; each index record for
#: these carries an rng_seed that reproduces the original follow-up exactly.
RANDOM_MRS = {"MR-P1", "MR-P2", "MR-P3", "MR-P4"}

DATA_SOURCE_FILES = {
    "folio": "folio_raw_mgs.jsonl",
    "logicnli": "logicnli_raw_mgs.jsonl",
    "proverqa": "proverqa_raw_mgs.jsonl",
}

INFER_FILE_PATTERN = "sampled_mgs_label_*.jsonl"


def source_fingerprint(tc: TestCase) -> str:
    """Hash of the logic content + label of a source case."""
    payload = {
        "premises_logic": tc.premises_logic,
        "conclusion_logic": tc.conclusion_logic,
        "label": tc.metadata.get("label", ""),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def followup_signature(mg: MetamorphicGroups):
    fol = mg.followup_case
    return (
        list(fol.premises_logic),
        fol.conclusion_logic,
        list(fol.premises_text),
        fol.conclusion_text,
    )


def find_reproducing_seed(mr, source: TestCase, target) -> int | None:
    """Search a small seed space for one that reproduces the follow-up."""
    for seed in range(1000):
        random.seed(seed)
        try:
            cand = mr.transform(source)
        except Exception:
            continue
        if (
            cand.premises_logic,
            cand.conclusion_logic,
            cand.premises_text,
            cand.conclusion_text,
        ) == target:
            return seed
    return None


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def build_index(raw_mgs_path: Path, data_source: str, stats: dict) -> list:
    """One index record per MG, in the original file order."""
    records = []
    mr_cache = {}
    for mg_obj in iter_jsonl(raw_mgs_path):
        src = TestCase(**mg_obj["source_case"])
        fol = TestCase(**mg_obj["followup_case"])
        mg = MetamorphicGroups(
            source_case=src,
            followup_case=fol,
            mr_name=mg_obj["mr_name"],
            metadata=mg_obj.get("metadata", {}),
        )
        mr_index = mg.metadata.get("mr_index", "")
        rec = {
            "data_source": src.metadata.get("data_source", data_source),
            "mr_index": mr_index,
            "example_id": src.metadata.get("example_id"),
            "source_sha256": source_fingerprint(src),
        }
        if src.metadata.get("original_file"):
            rec["original_file"] = src.metadata["original_file"]

        if mr_index in RANDOM_MRS:
            if mr_index not in mr_cache:
                mr_cache[mr_index] = get_mr(mr_index)
            seed = find_reproducing_seed(mr_cache[mr_index], src, followup_signature(mg))
            if seed is None:
                stats["seed_search_failed"] += 1
                raise RuntimeError(
                    f"could not find an rng seed reproducing {mr_index} for "
                    f"example {rec['example_id']} — extend the search space"
                )
            rec["rng_seed"] = seed
        records.append(rec)
        stats["indexed"] += 1
    return records


def collect_inference_files(infer_dir: Path, out_dir: Path) -> int:
    count = 0
    for model_dir in sorted(infer_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        target_dir = out_dir / model_dir.name
        for file in sorted(model_dir.glob(INFER_FILE_PATTERN)):
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target_dir / file.name)
            count += 1
    return count


def build_audit_labels(manual_check_dir: Path, out_file: Path) -> int:
    """Merge the LLM-judge labels and the human-review labels."""
    count = 0
    with open(out_file, "w", encoding="utf-8") as out:
        llm_judge = sorted(
            manual_check_dir.glob("llm_judge/*judge_*.jsonl")
        )
        human_review = sorted(
            manual_check_dir.glob("human_review/*false_samples.jsonl")
        )
        for stage, files in (("llm_judge", llm_judge), ("human_review", human_review)):
            for path in files:
                for rec in iter_jsonl(path):
                    out.write(
                        json.dumps(
                            {"review_stage": stage, **rec}, ensure_ascii=False
                        )
                        + "\n"
                    )
                    count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--raw-mgs-dir",
        type=Path,
        default=KBS_CODE / "data" / "metamorphic_group" / "raw_mgs",
        help="Directory with the full candidate MG files (raw_mgs).",
    )
    parser.add_argument(
        "--infer-results-dir",
        type=Path,
        default=KBS_CODE / "infer_results",
        help="Directory with per-model inference result jsonl files.",
    )
    parser.add_argument(
        "--manual-check-dir",
        type=Path,
        default=KBS_CODE / "rqs" / "rq1" / "manual_check",
        help="Directory with the audit label files.",
    )
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).resolve().parent / "dist"
    )
    args = parser.parse_args()

    start = time.perf_counter()
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # --- FOLIO: redistribute directly (CC BY-SA 4.0) ---
    folio_src = args.raw_mgs_dir / DATA_SOURCE_FILES["folio"]
    folio_dst = out / "mgs_folio.jsonl"
    shutil.copy2(folio_src, folio_dst)
    folio_lines = sum(1 for _ in open(folio_dst, encoding="utf-8"))

    # --- LogicNLI + ProverQA: license-free index only ---
    stats = {"indexed": 0, "seed_search_failed": 0}
    index_records = []
    for key in ("logicnli", "proverqa"):
        path = args.raw_mgs_dir / DATA_SOURCE_FILES[key]
        print(f"indexing {path.name} ...")
        index_records.extend(build_index(path, key, stats))
    index_path = out / "mgs_logicnli_proverqa_index.jsonl"
    with open(index_path, "w", encoding="utf-8") as f:
        for rec in index_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- inference results (our own artifact) ---
    n_infer = collect_inference_files(args.infer_results_dir, out / "inference_results")

    # --- audit labels (our own artifact) ---
    n_audit = build_audit_labels(args.manual_check_dir, out / "audit_labels.jsonl")

    # --- package docs ---
    shutil.copy2(Path(__file__).resolve().parent / "README.md", out / "README.md")
    license_note = out / "LICENSE.folio.txt"
    license_note.write_text(
        "mgs_folio.jsonl is derived from the FOLIO dataset, which is\n"
        "licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/).\n"
        "Attribution: Hanjie Chen, Faeze Brahman, Xiang Ren. "
        "\"CLUTRR: A Diagnostic Benchmark for Inductive Reasoning on Natural Language\"\n"
        "is NOT the source; the correct citation is:\n"
        "Simeng Han et al. \"FOLIO: Natural Language Reasoning with First-Order Logic.\" (2024).\n"
        "Share adaptations under the same license.\n",
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - start
    print("\n=== package summary ===")
    print(f"output dir : {out}")
    print(f"folio MGs  : {folio_lines}  ({folio_dst.stat().st_size / 1e6:.1f} MB)")
    print(f"index      : {len(index_records)} records ({index_path.stat().st_size / 1e6:.1f} MB)")
    print(f"inference  : {n_infer} files")
    print(f"audit      : {n_audit} label records")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"total size : {total / 1e6:.1f} MB")
    print(f"elapsed    : {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
