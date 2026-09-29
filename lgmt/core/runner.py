"""Inference runner: LLM-based entailment judgment over metamorphic groups.

Adaptive concurrency + thread-safe I/O + JSON schema validation. This is a
library-ified port of the original ``core/infer_run.py``; the parsing and
validation logic is unchanged.
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import jsonschema
from json_repair import repair_json
from loguru import logger
from tqdm import tqdm

from lgmt.core.structure import MetamorphicGroups, TestCase
from lgmt.models.base import LLMClient
from lgmt.prompts.llm_infer import (
    SYS_FEW_SHOT_COT,
    SYS_FEW_SHOT_DIRECT,
    SYS_ZERO_SHOT_COT,
    SYS_ZERO_SHOT_DIRECT,
    USER_PROMPT_TEMPLATE,
)
from lgmt.utils.labels import canonical_label

# --- Global Resources ---
RESULT_LOCK = threading.Lock()

RESULT_SCHEMA_DIRECT = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
}

RESULT_SCHEMA_COT = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "label": {"type": "string"},
    },
    "required": ["reasoning", "label"],
}

#: Prompting presets: name -> (system prompt, cot)
PROMPTING_PRESETS: Dict[str, Tuple[str, bool]] = {
    "zero_direct": (SYS_ZERO_SHOT_DIRECT, False),
    "zero_cot": (SYS_ZERO_SHOT_COT, True),
    "few_direct": (SYS_FEW_SHOT_DIRECT, False),
    "few_cot": (SYS_FEW_SHOT_COT, True),
}


def build_user_prompt(test_case: TestCase) -> str:
    """Build user prompt from test case."""
    premises_text = "\n".join(test_case.premises_text)
    return USER_PROMPT_TEMPLATE.format(
        premises_text=premises_text, conclusion_text=test_case.conclusion_text
    )


def call_llm(
    client: LLMClient,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    cot: bool,
    context: Optional[dict] = None,
    retries: int = 3,
    delay: int = 2,
) -> dict:
    """API call with retry and strict schema validation."""
    prompt_payload = {"system": system_prompt, "user": user_prompt}
    llm_response = None

    for i in range(retries + 1):
        try:
            llm_response = client.generate(
                prompt_payload,
                model=model_name,
                max_retries=0,
                context=context,
                cot=cot,
            )
            if llm_response:
                # clean Markdown code block
                cleaned_response = llm_response.strip()
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response.strip("`").strip()
                    if cleaned_response.lower().startswith("json"):
                        cleaned_response = cleaned_response[4:].strip()

                # repair JSON
                cleaned_response = repair_json(cleaned_response)
                obj = json.loads(cleaned_response)

                # ==========================================
                # 新增的拦截与容错逻辑：应对模型外层包裹了 List 的情况
                # ==========================================
                if isinstance(obj, list):
                    extracted_dict = None
                    for item in reversed(obj):  # 倒序遍历，通常模型把答案放最后
                        if isinstance(item, dict):
                            extracted_dict = item
                            break

                    if extracted_dict is not None:
                        obj = extracted_dict
                    else:
                        # 如果列表里一个字典都没有，主动抛出异常触发重试
                        raise ValueError(
                            f"Parsed JSON is a list without a valid dict object: {obj}"
                        )
                # ==========================================

                # Validation logic
                if not cot:
                    jsonschema.validate(instance=obj, schema=RESULT_SCHEMA_DIRECT)
                elif cot:  # 这里的 elif 也可以直接写成 else: if cot is a boolean
                    jsonschema.validate(instance=obj, schema=RESULT_SCHEMA_COT)
                else:
                    raise ValueError("Invalid system prompt type")

                return obj
            else:
                raise ValueError("Empty response")

        except Exception as e:
            if i < retries:
                logger.warning(f"Retry {i+1}/{retries} | Error: {e}")
                time.sleep(delay)
            else:
                logger.error(f"Final failure | Model: {model_name} | Error: {e}")
                if llm_response:
                    logger.error(f"Raw response: {llm_response}")
                    return {"error": str(e), "raw_response": llm_response}
                else:
                    logger.error("No raw response available")
                    raise e


def process_group(
    mg: MetamorphicGroups,
    client: LLMClient,
    model_name: str,
    system_prompt_text: str,
    result_save_path: str,
    cot: bool,
    prompting: str = "",
) -> bool:
    """Process single metamorphic group and save result."""
    mg_id = mg.metadata.get("mg_id", "unknown")
    try:
        source_test_case = mg.source_case
        followup_test_cases = mg.followup_case
        ground_truth_label = canonical_label(
            source_test_case.metadata.get("label", "")
        )

        base_context = {
            "task": "infer",
            "mr_index": mg.metadata.get("mr_index", ""),
            "mr_name": getattr(mg, "mr_name", ""),
            "ground_truth": ground_truth_label,
        }

        # 1. Get Responses
        source_response = call_llm(
            client,
            model_name,
            system_prompt_text,
            build_user_prompt(source_test_case),
            cot,
            context={**base_context, "role": "source"},
        )
        followup_response = call_llm(
            client,
            model_name,
            system_prompt_text,
            build_user_prompt(followup_test_cases),
            cot,
            context={**base_context, "role": "followup"},
        )

        # 2. Extract and Format Labels
        source_pred_label = canonical_label(source_response.get("label", ""))
        followup_pred_label = canonical_label(followup_response.get("label", ""))

        # 3. Calculate Metrics
        source_is_correct = source_pred_label == ground_truth_label
        followup_is_correct = followup_pred_label == ground_truth_label
        is_consistent = source_pred_label == followup_pred_label

        # 4. Construct Result (Original Version Restored)
        result = {
            "mg_id": mg_id,
            "mr_name": getattr(mg, "mr_name", ""),
            "mr_index": mg.metadata.get("mr_index", ""),
            "data_source": mg.metadata.get("data_source", ""),
            "model": model_name,
            "prompting": prompting,
            "ground_truth": ground_truth_label,
            "source_input": {
                "premises_text": source_test_case.premises_text,
                "conclusion_text": source_test_case.conclusion_text,
            },
            "followup_input": {
                "premises_text": followup_test_cases.premises_text,
                "conclusion_text": followup_test_cases.conclusion_text,
            },
            "source_response": {
                "reasoning": source_response.get("reasoning", ""),
                "response_label": source_pred_label,
                "is_correct": source_is_correct,
            },
            "followup_response": {
                "reasoning": followup_response.get("reasoning", ""),
                "response_label": followup_pred_label,
                "is_correct": followup_is_correct,
            },
            "is_consistent": is_consistent,
        }

        # 5. Thread-safe Write
        with RESULT_LOCK:
            with open(result_save_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.error(f"Task Failed | MG_ID: {mg_id} | Error: {e}")
        return False


def run_inference(
    mgs: List[MetamorphicGroups],
    client: LLMClient,
    model_name: str,
    prompting: str = "zero_cot",
    result_save_path: str = "infer_results/results.jsonl",
    max_workers: int = 100,
    quiet: bool = False,
) -> str:
    """Run entailment inference over all MGs and write per-MG JSONL."""
    if prompting not in PROMPTING_PRESETS:
        raise ValueError(
            f"Unknown prompting {prompting!r}; choose from {sorted(PROMPTING_PRESETS)}"
        )
    system_prompt_text, cot = PROMPTING_PRESETS[prompting]

    os.makedirs(os.path.dirname(os.path.abspath(result_save_path)), exist_ok=True)

    log_dir = os.path.join(os.path.dirname(os.path.abspath(result_save_path)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"inference_{time.strftime('%Y%m%d_%H%M%S')}.log")
    logger.add(log_file, rotation="10 MB", retention="5 days", level="INFO")

    logger.info(
        f"Concurrency set to {max_workers} for mode: "
        f"{model_name}_{prompting}"
    )
    logger.info(f"Loaded {len(mgs)} groups. Running...")

    start_time = time.perf_counter()
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_group,
                mg,
                client,
                model_name,
                system_prompt_text,
                result_save_path,
                cot,
                prompting,
            ): mg
            for mg in mgs
        }
        iterator = as_completed(futures)
        if not quiet:
            iterator = tqdm(iterator, total=len(mgs), desc="Inference")
        for future in iterator:
            if future.result():
                success_count += 1

    total_time = time.perf_counter() - start_time
    logger.success(
        f"Finished. Success: {success_count}/{len(mgs)} | Total Time: {total_time:.2f}s"
    )
    return result_save_path
