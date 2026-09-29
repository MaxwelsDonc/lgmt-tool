import json
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


def filter_false_samples(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    false_samples: list[dict[str, Any]] = []

    for record in records:
        judge_targets = record.get("judge_targets", [])
        if not isinstance(judge_targets, list):
            continue

        false_targets = []
        for target in judge_targets:
            if not isinstance(target, dict):
                continue
            if str(target.get("label", "")).strip() == "False":
                false_targets.append(target)

        if false_targets:
            false_samples.append(
                {
                    "mg_id": record.get("mg_id", ""),
                    "judge_targets": false_targets,
                }
            )

    return false_samples


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[4]

    # Key configurable parameters
    INPUT_FILE = (
        PROJECT_ROOT
        / "experiments"
        / "rq1"
        / "manual_check"
        / "llm_judge"
        / "sampled_350_seed42_judge_chatgpt_20260421_152832.jsonl"
    )
    OUTPUT_FILE = (
        PROJECT_ROOT
        / "experiments"
        / "rq1"
        / "manual_check"
        / "human_review"
        / "sampled_350_seed42_judge_chatgpt_20260421_152832_false_samples.jsonl"
    )

    records = read_jsonl(INPUT_FILE)
    false_samples = filter_false_samples(records)
    write_jsonl(OUTPUT_FILE, false_samples)

    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"False samples: {len(false_samples)}")
