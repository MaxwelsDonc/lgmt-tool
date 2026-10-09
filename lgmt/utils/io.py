"""JSONL I/O for test cases, metamorphic groups, and inference records."""
import json
import os

from loguru import logger
from dataclasses import asdict
from typing import Any, Dict, Iterable, List

from lgmt.core.structure import MetamorphicGroups, TestCase


def _load_jsonl(file_path: str) -> List[Dict[str, Any]]:
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def load_test_cases(file_path: str) -> List[TestCase]:
    """Load entailment test cases (``TestCase`` JSONL, one per line)."""
    try:
        return [TestCase(**record) for record in _load_jsonl(file_path)]
    except FileNotFoundError:
        logger.error(f"File not found - {file_path}")
        return []
    except json.JSONDecodeError:
        logger.error(f"JSON decoding error in file - {file_path}")
        return []


def save_test_cases(file_path: str, test_cases: List[TestCase]) -> None:
    """Save ``TestCase`` objects as JSONL."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for tc in test_cases:
            f.write(json.dumps(asdict(tc), ensure_ascii=False) + "\n")
    logger.success(f"Saved {len(test_cases)} test cases to {file_path}")


def load_metamorphic_groups(file_path: str) -> List[MetamorphicGroups]:
    """Load metamorphic groups (MG JSONL with source/followup cases)."""
    mgs = []
    try:
        for data in _load_jsonl(file_path):
            source_case = TestCase(**data["source_case"])
            followup_case = TestCase(**data["followup_case"])
            mgs.append(
                MetamorphicGroups(
                    source_case=source_case,
                    followup_case=followup_case,
                    mr_name=data["mr_name"],
                    metadata=data.get("metadata", {}),
                )
            )
        return mgs
    except FileNotFoundError:
        logger.error(f"File not found - {file_path}")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Malformed metamorphic group in {file_path}: {e}")
        return []


def save_metamorphic_groups(file_path: str, mgs: List[MetamorphicGroups]) -> None:
    """Save ``MetamorphicGroups`` objects as JSONL."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for mg in mgs:
            f.write(json.dumps(asdict(mg), ensure_ascii=False) + "\n")
    logger.success(f"Saved {len(mgs)} metamorphic groups to {file_path}")


def load_inference_records(file_path: str) -> List[Dict[str, Any]]:
    """Load raw inference result records (one JSON object per line)."""
    try:
        return _load_jsonl(file_path)
    except FileNotFoundError:
        logger.error(f"File not found - {file_path}")
        return []


def write_jsonl(file_path: str, records: Iterable[Dict[str, Any]]) -> int:
    """Append-free JSONL writer; returns the number of records written."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    count = 0
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count
