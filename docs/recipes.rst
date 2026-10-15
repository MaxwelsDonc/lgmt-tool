Recipes
=======

Copy-paste snippets for common setups.

Point at an endpoint
--------------------

OpenAI:

.. code-block:: bash

    export LGMT_API_KEY=sk-...
    lgmt run --mgs demo --model gpt-4o --output results.jsonl

DeepSeek:

.. code-block:: bash

    export LGMT_API_KEY=sk-...
    export LGMT_BASE_URL=https://api.deepseek.com
    lgmt run --mgs demo --model deepseek-chat --output results.jsonl

Local vLLM:

.. code-block:: bash

    export LGMT_BASE_URL=http://localhost:8000/v1
    export LGMT_API_KEY=dummy          # vLLM ignores the value
    lgmt run --mgs demo --model <served-model-name> --output results.jsonl

Local Ollama:

.. code-block:: bash

    export LGMT_BASE_URL=http://localhost:11434/v1
    export LGMT_API_KEY=dummy
    lgmt run --mgs demo --model llama3.1:8b --output results.jsonl

Use short model aliases
-----------------------

Define aliases in ``config.yaml`` (see :doc:`/data-formats`) and reference
them anywhere a model name is accepted:

.. code-block:: bash

    lgmt run --mgs demo --model chatgpt --output results.jsonl

Run fully offline on your own FOL cases
---------------------------------------

Records that already carry ``premises_logic`` / ``conclusion_logic`` need
no LLM:

.. code-block:: bash

    lgmt build-mgs --input my_fol.jsonl --output my_mgs.jsonl \
                   --mock --no-realize
    lgmt run --mgs my_mgs.jsonl --mock --output my_results.jsonl
    lgmt report --results my_results.jsonl --output my_report.html

Restrict the MRs used for building
----------------------------------

.. code-block:: bash

    # a single relation
    lgmt build-mgs --input cases.jsonl --output mgs.jsonl \
                   --model gpt-4o --mr MR-E1.2

    # several relations, including one loaded from a file
    lgmt build-mgs --input cases.jsonl --output mgs.jsonl \
                   --model gpt-4o --mr MR-P1 --mr MR-C3 \
                   --mr-file my_mr.py --mr MR-X1

Rank several models at once
---------------------------

.. code-block:: bash

    bash examples/run_multiple_models.sh        # edit the model list first

Regenerate the report without re-running inference
--------------------------------------------------

.. code-block:: bash

    lgmt report --results results.jsonl --output report.html

Audit the benchmark data
------------------------

.. code-block:: bash

    # back-translation fidelity over built MGs
    lgmt audit --mgs my_mgs.jsonl --output audit.jsonl --model gpt-4o

    # MR regression checker (compare two revisions of the MR library)
    python tools/mr_smoke_compare.py
