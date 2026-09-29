"""
Inference script for FOL-to-NL structural validation.
"""

import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

import jsonschema
from json_repair import repair_json
from loguru import logger
from tqdm import tqdm

# Project environment setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR))))
sys.path.insert(0, PROJECT_ROOT)

import yaml  # noqa: E402

from lgmt.models import OpenAICompatClient  # noqa: E402
from lgmt.prompts.fol2nl_validate import SYSTEM_PROMPT, get_FOL2NL_validate_prompt  # noqa: E402


def load_client(api_key_file: str | None = None) -> OpenAICompatClient:
    """Build a client from an api_keys.yaml-style file or LGMT_* env vars."""
    api_key = base_url = None
    if api_key_file and os.path.exists(api_key_file):
        with open(api_key_file, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        api_key = cfg.get("api_key")
        base_url = cfg.get("base_url")
    if not api_key:
        from lgmt.config import resolve_settings

        settings = resolve_settings()
        api_key, base_url = settings.api_key, settings.base_url
    return OpenAICompatClient(api_key=api_key, base_url=base_url)


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["True", "False"]},
    },
    "required": ["label"],
}


def read_jsonl(file_path: str) -> list[dict[str, Any]]:
    """Read JSONL records from file."""
    records: list[dict[str, Any]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(file_path: str, records: list[dict[str, Any]]) -> None:
    """Write JSONL records to file."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_judge_items(sample: dict[str, Any]) -> list[dict[str, str]]:
    """Extract FOL/NL pairs from judge_targets."""
    judge_targets = sample.get("judge_targets", [])
    if not isinstance(judge_targets, list):
        return []

    judge_items: list[dict[str, str]] = []
    for target in judge_targets:
        if not isinstance(target, dict):
            continue

        fol = str(target.get("fol", "")).strip()
        nl = str(target.get("nl", "")).strip()
        if not fol or not nl:
            continue

        judge_items.append({"fol": fol, "nl": nl})
    return judge_items


def call_llm(
    client: OpenAICompatClient,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    retries: int = 3,
    delay: float = 2.0,
) -> dict[str, Any]:
    """Call LLM with retry and strict JSON validation."""
    prompt_payload = {"system": system_prompt, "user": user_prompt}
    llm_response = None

    for i in range(retries + 1):
        try:
            llm_response = client.generate(
                prompt_payload, model=model_name, max_retries=0
            )
            if not llm_response:
                raise ValueError("Empty response")

            cleaned_response = llm_response.strip()
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.strip("`").strip()
                if cleaned_response.lower().startswith("json"):
                    cleaned_response = cleaned_response[4:].strip()

            cleaned_response = repair_json(cleaned_response)
            obj = json.loads(cleaned_response)

            if isinstance(obj, list):
                extracted_dict = None
                for item in reversed(obj):
                    if isinstance(item, dict):
                        extracted_dict = item
                        break
                if extracted_dict is None:
                    raise ValueError(
                        f"Parsed JSON is a list without a valid dict object: {obj}"
                    )
                obj = extracted_dict

            jsonschema.validate(instance=obj, schema=RESULT_SCHEMA)
            return obj

        except Exception as e:
            if i < retries:
                logger.warning(f"Retry {i+1}/{retries} | Error: {e}")
                time.sleep(delay)
            else:
                logger.error(f"Final failure | Model: {model_name} | Error: {e}")
                if llm_response:
                    logger.error(f"Raw response: {llm_response}")
                    return {"label": "False"}
                raise e


def judge_one_sample(
    sample: dict[str, Any],
    client: OpenAICompatClient,
    model_name: str,
    retries: int,
    delay: float,
) -> dict[str, Any]:
    """Judge all available FOL/NL pairs in one sample."""
    pair_results: list[dict[str, str]] = []

    for item in extract_judge_items(sample):
        response = call_llm(
            client=client,
            model_name=model_name,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=get_FOL2NL_validate_prompt(
                fol=item["fol"],
                nl=item["nl"],
            ),
            retries=retries,
            delay=delay,
        )
        pair_results.append(
            {
                "fol": item["fol"],
                "nl": item["nl"],
                "label": str(response.get("label", "False")).strip(),
            }
        )

    return {
        "mg_id": str(sample.get("mg_id", "")),
        "judge_targets": pair_results,
    }


def main(
    sample_file: str,
    output_file: str,
    api_key_file: str,
    judge_model: str,
    max_workers: int,
    retries: int,
    retry_delay: float,
) -> None:
    """Run FOL-to-NL structural validation inference."""
    records = read_jsonl(sample_file)
    client = load_client(api_key_file or None)
    results: list[dict[str, Any] | None] = [None] * len(records)

    def worker(i: int) -> dict[str, Any]:
        return judge_one_sample(
            sample=records[i],
            client=client,
            model_name=judge_model,
            retries=retries,
            delay=retry_delay,
        )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:
        futures = {executor.submit(worker, i): i for i in range(len(records))}
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="FOL2NL Validate",
        ):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:
                logger.error(f"Task Failed | Index: {i} | Error: {e}")
                results[i] = {
                    "mg_id": str(records[i].get("mg_id", "")),
                    "judge_targets": [],
                }

    final_results: list[dict[str, Any]] = [item for item in results if item is not None]

    write_jsonl(output_file, final_results)

    total = len(final_results)
    total_pairs = sum(len(item.get("judge_targets", [])) for item in final_results)
    n_true = sum(
        1
        for item in final_results
        for pair in item.get("judge_targets", [])
        if pair.get("label") == "True"
    )
    n_false = total_pairs - n_true

    logger.success(
        f"Finished. Samples: {total} | Pairs: {total_pairs} | True: {n_true} | False: {n_false}"
    )
    print(f"Input: {sample_file}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    logging_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logging_dir, exist_ok=True)
    logger.add(
        os.path.join(
            logging_dir, f"fol2nl_validate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        rotation="10 MB",
        retention="5 days",
        level="INFO",
    )

    # Key configurable parameters
    SAMPLE_FILE = os.path.join(
        PROJECT_ROOT,
        "experiments",
        "rq1",
        "manual_check",
        "check_data",
        "sampled_350_seed42.jsonl",
    )
    API_KEY_FILE = os.path.join(PROJECT_ROOT, "api_keys.yaml")
    JUDGE_MODEL = "chatgpt"
    MAX_WORKERS = 20
    RETRIES = 2
    RETRY_DELAY = 0.8

    OUTPUT_DIR = os.path.join(
        PROJECT_ROOT,
        "experiments",
        "rq1",
        "manual_check",
        "llm_judge",
    )
    OUTPUT_FILE = os.path.join(
        OUTPUT_DIR,
        f"{os.path.splitext(os.path.basename(SAMPLE_FILE))[0]}_judge_{JUDGE_MODEL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
    )

    main(
        sample_file=SAMPLE_FILE,
        output_file=OUTPUT_FILE,
        api_key_file=API_KEY_FILE,
        judge_model=JUDGE_MODEL,
        max_workers=MAX_WORKERS,
        retries=RETRIES,
        retry_delay=RETRY_DELAY,
    )
