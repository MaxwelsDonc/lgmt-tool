Quickstart
==========

Install the library and CLI straight from the repository (Python >= 3.10):

.. code-block:: bash

    git clone https://github.com/MaxwelsDonc/lgmt-tool.git
    cd lgmt-tool
    python -m venv .venv && source .venv/bin/activate
    pip install -e .

.. tip::

    **Option — Docker** (nothing to install beyond Docker):

    .. code-block:: bash

        docker build -t lgmt .
        docker run --rm -v $(pwd)/demo_output:/app/demo_output lgmt

Experience LGMT in 30 seconds (no API key, no network)
------------------------------------------------------

The bundled offline demo runs a deterministic mock model over bundled
data and writes a self-contained HTML report:

.. code-block:: bash

    lgmt demo          # 40 groups, fast
    lgmt demo --full   # full 3,091-group benchmark (overwrites demo_output/)

Open ``demo_output/report.html`` in any browser — the leaderboard, metric
cards, and side-by-side FOL/NL violation evidence work completely offline.

Prefer a Web UI?
----------------

Launch the built-in **LGMT Web Studio** (zero extra dependencies):

.. code-block:: bash

    lgmt web --port 7860

Then open http://localhost:7860 to access the three guided workflow tabs
(**1. Quick Demo**, **2. Benchmark Your Model**, **3. Test Custom Cases**)
with live interactive report rendering.

Benchmark a real model
----------------------

Works with any OpenAI-compatible endpoint (OpenAI, DeepSeek, a Claude
proxy, or local vLLM / Ollama):

.. code-block:: bash

    export LGMT_API_KEY=sk-...                 # and LGMT_BASE_URL if needed
    export LGMT_BASE_URL=https://api.deepseek.com
    lgmt run --mgs benchmark --model deepseek-flash --output results.jsonl
    lgmt report --results results.jsonl --output report.html

Next steps
----------

- :doc:`guides/demo` — what the offline tour does and what to look at in
  the report.
- :doc:`guides/benchmark` — dataset shorthands, prompting presets, config
  precedence, and API cost expectations.
- :doc:`guides/custom-cases` — test LGMT on your own domain rules.
- :doc:`guides/custom-mrs` — extend LGMT with your own metamorphic
  relation (Z3-verified before it can run).
