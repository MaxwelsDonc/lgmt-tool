import argparse
import json
import random
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")


def load_mgs(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def build_judge_targets(mg: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build minimal judge targets for logic-vs-language checking.
    Source of truth: metadata.translation_index
    """
    followup_case = mg.get("followup_case", {})
    followup_logic = followup_case.get("premises_logic", [])
    followup_text = followup_case.get("premises_text", [])

    metadata = mg.get("metadata", {})
    translation_index = metadata.get("translation_index", [])
    if not isinstance(translation_index, list):
        translation_index = []

    judge_targets: list[dict[str, Any]] = []
    seen_premise_indices: set[int] = set()

    for item in translation_index:
        if isinstance(item, int):
            if item in seen_premise_indices:
                continue
            if item < 0 or item >= len(followup_logic) or item >= len(followup_text):
                continue
            seen_premise_indices.add(item)
            judge_targets.append(
                {
                    "followup_index": item,
                    "fol": followup_logic[item],
                    "nl": followup_text[item],
                }
            )
        elif item == "conclusion":
            conclusion_logic = followup_case.get("conclusion_logic", "")
            conclusion_text = followup_case.get("conclusion_text", "")
            if conclusion_logic or conclusion_text:
                judge_targets.append(
                    {
                        "followup_index": "conclusion",
                        "fol": conclusion_logic,
                        "nl": conclusion_text,
                    }
                )

    return judge_targets


def prepare_shared_check_data(
    processed_mgs_path: Path,
    output_path: Path,
    sample_size: int,
    seed: int,
) -> Path:
    mgs = load_mgs(processed_mgs_path)
    if len(mgs) < sample_size:
        raise ValueError(
            f"Only {len(mgs)} metamorphic groups available, < sample_size={sample_size}"
        )

    rng = random.Random(seed)
    sampled_mgs = rng.sample(mgs, k=sample_size)

    output_records: list[dict[str, Any]] = []
    for rank, mg in enumerate(sampled_mgs, start=1):
        metadata = mg.get("metadata", {})
        source_case = mg.get("source_case", {})
        followup_case = mg.get("followup_case", {})

        output_records.append(
            {
                "sample_rank": rank,
                "sample_seed": seed,
                "mg_id": metadata.get("mg_id", ""),
                "mr_name": mg.get("mr_name", ""),
                "mr_index": metadata.get("mr_index", ""),
                "data_source": metadata.get("data_source", ""),
                "source_case": {
                    "premises_logic": source_case.get("premises_logic", []),
                    "premises_text": source_case.get("premises_text", []),
                    "conclusion_logic": source_case.get("conclusion_logic", ""),
                    "conclusion_text": source_case.get("conclusion_text", ""),
                },
                "followup_case": {
                    "premises_logic": followup_case.get("premises_logic", []),
                    "premises_text": followup_case.get("premises_text", []),
                    "conclusion_logic": followup_case.get("conclusion_logic", ""),
                    "conclusion_text": followup_case.get("conclusion_text", ""),
                },
                "judge_targets": build_judge_targets(mg),
            }
        )

    write_jsonl(output_path, output_records)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare shared manual-check data from processed metamorphic groups."
    )
    parser.add_argument("--sample-size", type=int, default=350)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
    args = parse_args()

    # Key configurable paths and defaults
    PROCESSED_MGS_PATH = (
        PROJECT_ROOT
        / "data"
        / "metamorphic_group"
        / "processed_mgs_core"
        / "processed_mgs_200.jsonl"
    )
    OUTPUT_PATH = (
        PROJECT_ROOT
        / "experiments"
        / "rq1"
        / "manual_check"
        / "check_data"
        / f"sampled_{args.sample_size}_seed{args.seed}.jsonl"
    )

    out = prepare_shared_check_data(
        processed_mgs_path=PROCESSED_MGS_PATH,
        output_path=OUTPUT_PATH,
        sample_size=args.sample_size,
        seed=args.seed,
    )
    print(out)
