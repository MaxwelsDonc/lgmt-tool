Workflow 2: Benchmark a model
=============================

Rank any OpenAI-compatible LLM against the bundled benchmark and six
reference SOTA models.

.. code-block:: bash

    export LGMT_API_KEY=sk-...                  # and LGMT_BASE_URL if not the default
    export LGMT_BASE_URL=https://api.deepseek.com
    lgmt run --mgs benchmark --model deepseek-flash --output results.jsonl
    lgmt report --results results.jsonl --output report.html

Dataset shorthands
------------------

- ``--mgs benchmark`` resolves to ``data/metamorphic_group/processed_mgs_core/processed_mgs_3091.jsonl``
  (3,091 groups);
- ``--mgs demo`` resolves to the 40-group fast subset;
- explicit file paths also work.

Cost transparency
-----------------

The full 3,091-group benchmark issues one judgment per source and per
follow-up case — **6,182 API calls** per model (~10^7 tokens). Run
``--mgs demo`` first for an 80-call sanity check.

Configuration precedence
------------------------

From lowest to highest:

1. built-in defaults;
2. ``config.yaml`` (``model.*`` / ``inference.*`` — copy
   ``config.example.yaml`` to get started);
3. ``LGMT_API_KEY`` / ``LGMT_BASE_URL`` / ``LGMT_MODEL`` environment
   variables;
4. explicit CLI flags (``--api-key`` etc.).

When the key is missing everywhere, the CLI prompts for it interactively
on a terminal (hidden input; held in memory only).

Prompting presets
-----------------

``--prompting`` selects the system prompt and output schema (see
:data:`~lgmt.core.runner.PROMPTING_PRESETS`):

- ``zero_direct`` — zero-shot, answer only;
- ``zero_cot`` — zero-shot with chain-of-thought (default);
- ``few_direct`` / ``few_cot`` — few-shot variants.

Reasoning models (detected by name markers such as ``reasoner``, ``o1``,
``r1``) reject sampling parameters, so ``temperature`` is ignored for
them client-side.

Reference leaderboard
---------------------

``lgmt report`` compares your results against a snapshot of six reference
LLMs stored in ``lgmt/data/reference_metrics.json`` (zero-shot CoT,
snapshot dated in the report). Reference models only appear on matching
calibers (same prompting style).

Reproducing the paper's multi-model table
-----------------------------------------

The repository ships a driver script for running several models in one
go: ``examples/run_multiple_models.sh``.
