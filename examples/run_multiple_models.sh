#!/usr/bin/env bash
# Evaluate several models on the bundled benchmark, then build a combined
# leaderboard report (models ranked against each other on the same data).
#
# Usage:
#   export LGMT_API_KEY=sk-...
#   bash examples/run_multiple_models.sh gpt-5.2 claude-4.5 deepseek-chat
#
# Each model runs sequentially (each run is already internally concurrent).
# Results land in runs/ and the combined report in runs/report.html.
#
# Optional env overrides:
#   BENCH=path/to/mgs.jsonl   (default: the bundled 3,091-group benchmark)
#   LGMT_MOCK=flawed          (offline smoke test: use the mock model)
set -euo pipefail

MODELS=("$@")
[ ${#MODELS[@]} -eq 0 ] && { echo "usage: run_multiple_models.sh <model> [model...]" >&2; exit 1; }

BENCH=${BENCH:-data/metamorphic_group/processed_mgs_core/processed_mgs_3091.jsonl}
MOCK_ARGS=()
[ -n "${LGMT_MOCK:-}" ] && MOCK_ARGS=(--mock "$LGMT_MOCK")

mkdir -p runs
RESULTS=(); NAMES=()

for m in "${MODELS[@]}"; do
  safe=$(echo "$m" | tr '/: ' '___')
  out="runs/results_${safe}.jsonl"
  echo "=== evaluating $m -> $out"
  lgmt run --mgs "$BENCH" --model "$m" "${MOCK_ARGS[@]}" --output "$out"
  RESULTS+=("--results" "$out"); NAMES+=("--model" "$m")
done

lgmt report "${RESULTS[@]}" "${NAMES[@]}" --mgs "$BENCH" --output runs/report.html
echo "Combined leaderboard: runs/report.html"
