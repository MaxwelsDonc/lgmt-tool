Workflow 1: Offline demo tour
=============================

``lgmt demo`` runs the whole pipeline end to end — build metamorphic
groups, run inference, evaluate consistency, render the report — using a
deterministic **mock model** and bundled data. No API key, no network.

.. code-block:: bash

    lgmt demo          # 40-group fast subset (~80 judgments)
    lgmt demo --full   # full 3,091-group benchmark

Both write a self-contained ``demo_output/report.html`` (the ``--full``
run overwrites it) that opens by double-click in any browser.

The mock model
--------------

:class:`~lgmt.models.mock.MockLLMClient` implements two personas:

- ``consistent`` — always returns the logically correct verdict (the
  ground-truth label attached to the test case), so the report shows zero
  violations;
- ``flawed`` — answers correctly on source cases but deliberately returns
  an inconsistent verdict on follow-up cases of selected MR categories
  (``E`` and ``P`` by default), simulating a model whose reasoning is not
  invariant under the MR transformation. This is the persona ``lgmt
  demo`` uses, so you immediately see violation evidence in the report.

What to look at in the report
-----------------------------

- **Leaderboard** — your mock run ranked against six reference SOTA LLMs.
- **Metric cards** — MVR / ACC / HDR / FUR with per-MR drill-down tables;
  violation counts link into the per-group view with filters applied.
- **Per-group audit view** — every metamorphic violation as a full card
  with side-by-side FOL/NL diffs and collapsible CoT reasoning traces.

Python equivalent
-----------------

.. code-block:: python

    from lgmt.models.mock import MockLLMClient
    from lgmt.core.runner import run_inference
    from lgmt.utils.io import load_metamorphic_groups

    mgs = load_metamorphic_groups("data/metamorphic_group/processed_mgs_demo.jsonl")
    client = MockLLMClient(persona="flawed")
    run_inference(mgs, client, model_name="mock", result_save_path="results.jsonl")

See :doc:`/data-formats` for the exact paths and file schemas, and
:doc:`/recipes` for tweaking the demo (persona, flip categories).
