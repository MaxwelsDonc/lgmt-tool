# LGMT dataset — Zenodo package

This directory builds the Zenodo upload package for the LGMT artifacts
(`prepare_package.py` → `dist/`), and lets users rebuild the
license-restricted parts on their own machine (`rebuild_mgs.py`).

## What is in the package

| Item | Scale |
|---|---|
| Metamorphic groups derived from FOLIO | 12,091 (redistributed directly, CC BY-SA 4.0) |
| Metamorphic groups derived from LogicNLI + ProverQA | 64,207 (**index only**, rebuild required) |
| Total candidate MGs | **76,298** |
| Core evaluation set (in the tool repo, `data/`) | **3,091 groups** |
| Inference results | **6 models × 4 prompting presets** (24 jsonl files) |
| Back-translation audit labels | 404 records (350 LLM-judged + 54 human-reviewed) |

## Files produced in `dist/`

- `mgs_folio.jsonl` — FOLIO-derived MGs, redistributed directly.
  FOLIO is licensed CC BY-SA 4.0; see `LICENSE.folio.txt` for attribution.
  Schema per line:
  `{"source_case": TestCase, "followup_case": TestCase, "mr_name": str,
  "metadata": {"mr_index": str}}`
  where `TestCase = {"premises_logic": [...], "conclusion_logic": str,
  "premises_text": [...], "conclusion_text": str, "metadata": {...}}`.
- `mgs_logicnli_proverqa_index.jsonl` — one record per MG, **no source text**:
  - `mg_id` — package-local id (`logicnli_1`, `proverqa_1`, ...)
  - `data_source` — `LogicNLI` / `ProverQA`
  - `mr_index` — e.g. `MR-E1.4` (transformations implemented in `lgmt/mrs/`)
  - `example_id` — id of the originating source case
    (`{split}_{example}_{i}` for LogicNLI, original id for ProverQA)
  - `original_file` — ProverQA only (`easy.json` / `medium.json` / `hard.json`)
  - `source_sha256` — SHA-256 over the source case's logic + gold label
    (verifies your rebuild matches the indexed content)
  - `transform` — present only for the randomness-consuming MRs
    (MR-P1/P2/P3/P4), recording exactly what the transform did so a rebuild
    is byte-identical without RNG:
    - `{"kind": "premise_order", "premise_order": [...]}` (P1: final order
      of source premise indices)
    - `{"kind": "duplicate", "duplicated_indices": [...]}` (P2: source
      indices appended at the end)
    - `{"kind": "add_premise", "added_logic": ..., "added_text": ...}` (P3)
    - `{"kind": "fuse", "fused_indices": [i, j], "fused_logic": ...,
      "fused_text": ...}` (P4: the merged pair and the fused premise)
- `inference_results/<model>/sampled_mgs_label_<model>_<shot>_<cot|direct>.jsonl`
  — per-MG verdicts produced by the LGMT authors (our own artifact;
  contains model outputs). Models: chatgpt (GPT-5.2), chatgpt_reasoner
  (o4-mini), claude (Claude 4.5 Sonnet), deepseek (DeepSeek Chat),
  deepseek_reasoner (DeepSeek Reasoner), llama (Llama 3.3 70B).
- `audit_labels.jsonl` — back-translation fidelity labels; each record has
  `review_stage` (`llm_judge` / `human_review`), `mg_id`, and
  `judge_targets: [{fol, nl, label}]`.
- `README.md`, `LICENSE.folio.txt` — this file and the FOLIO attribution.

## License layering (why the index exists)

- **FOLIO** (CC BY-SA 4.0): derived MGs are redistributed directly, with
  attribution and share-alike.
- **LogicNLI and ProverQA**: their upstream repositories ship **no
  LICENSE**, so we do **not** redistribute derived content. Instead we ship
  the index above plus the conversion scripts in `scripts/` (archived from
  the research codebase), which let you reconstruct the full MGs locally
  from your own copy of the original datasets.
- Inference results and audit labels are produced by us and are shared
  under the repository's MIT license.

## Rebuilding the LogicNLI / ProverQA MGs

Prereqs: `pip install -e .` (LGMT) and, for the from-original chain,
`pip install z3-solver nltk`.

Fast path — from source-test-case files you already have (e.g. the ones in
the tool repo under `data/source_test_case/`, which are also derived from
LogicNLI/ProverQA and stay in the tool repo for research use):

```bash
python zenodo/rebuild_mgs.py \
    --index dist/mgs_logicnli_proverqa_index.jsonl \
    --source-cases ../lgmt-tool/data/source_test_case/logicnli_source_test_case.jsonl \
                   ../lgmt-tool/data/source_test_case/proverqa_source_test_case.jsonl \
    --out rebuilt_mgs.jsonl
```

Full path — starting from the original dataset downloads:

```bash
# LogicNLI:  original/{dev,test,train}_{language,logic}.json
# ProverQA:  {easy,medium,hard}.json
python zenodo/rebuild_mgs.py \
    --index dist/mgs_logicnli_proverqa_index.jsonl \
    --from-original /path/to/LogicNLI/original /path/to/ProverQA \
    --work-dir /tmp/lgmt_rebuild \
    --out rebuilt_mgs.jsonl
```

The from-original chain runs, in order:
`clean_logicnli_conflicts.py` (Z3 contradiction filtering of facts/rules)
→ `convert_logicnli_files.py` (structured facts/rules → FOL test cases)
→ `clean_logicnli_condlicts_phase2.py` (Z3 self-consistency filtering)
→ `convert_proverQA_files.py`. Every rebuilt MG is checked against
`source_sha256`; mismatches are skipped with a warning.

Smoke-test a small rebuild:

```bash
python zenodo/rebuild_mgs.py --index dist/mgs_logicnli_proverqa_index.jsonl \
    --source-cases ... --out smoke.jsonl --limit 50
```

## Citation

- The framework and MRs: KBS companion paper (**TODO: full citation**).
- This artifact and the tool: ICSE 2027 Tool Demonstration
  (**TODO: citation**).
- Underlying datasets: FOLIO (CC BY-SA 4.0), LogicNLI, ProverQA — see the
  tables in `data/README.md` of the tool repository.

Archive DOI: **TODO**.
