Workflow 3: Test your own domain cases
======================================

Audit your own domain rules — no FOL knowledge and no ground-truth labels
needed. One test case is just a few premise lines plus one conclusion.

Supported input forms
---------------------

The backend **sniffs the format automatically** — no ``input_mode`` flag
(see :func:`~lgmt.core.builder.parse_and_normalize_cases`):

- **Plain English / Chinese** — premise sentences + one conclusion;
  the LLM synthesizes FOL and NLTK's parser validates every formula.
- **Pure FOL** — formulas typed directly (``all x.(P(x) -> Q(x))``);
  also accepted in Unicode form (``∀ ∃ ¬ ∧ ∨ → ↔``).
- **Dual NL + FOL** — both levels provided; used as-is.
- **Unstructured text** — a free-text paragraph; the LLM extracts
  premises and conclusion first.

A ready-made example file is
`examples/custom_cases.example.jsonl
<https://github.com/MaxwelsDonc/lgmt-tool/blob/main/examples/custom_cases.example.jsonl>`_.

CLI
---

.. code-block:: bash

    lgmt build-mgs --input examples/custom_cases.example.jsonl \
                   --output my_mgs.jsonl --model <your-model>
    lgmt run --mgs my_mgs.jsonl --model <your-model> --output my_results.jsonl
    lgmt report --results my_results.jsonl --output my_report.html

- ``build-mgs`` normalizes the input, applies every applicable
  metamorphic relation, and optionally *realizes* the transformed FOL
  back into natural language (logic-to-NL translation of the
  ``[Changed_*]``-tagged lines).
- Records that already include ``premises_logic`` / ``conclusion_logic``
  are used as-is — ``--mock`` and ``--no-realize`` run fully offline for
  those.
- ``--mr`` restricts building to specific MRs; ``--mr-file`` loads custom
  MRs from a Python file (see :doc:`/guides/custom-mrs`).

Web Studio
----------

In the Web Studio's **3. Test Custom Cases** tab you can paste cases into
a single smart input box (plain text, FOL blocks, or JSONL), use the
quick form, or upload a batch file.

Back-translation fidelity audit
-------------------------------

To check that the regenerated natural language faithfully preserves the
transformed FOL, run an independent judge model over the built MGs:

.. code-block:: bash

    lgmt audit --mgs my_mgs.jsonl --output audit.jsonl --model <judge-model>

Each record of the audit output carries ``fol``, ``nl``, and a boolean
``valid`` verdict (:func:`~lgmt.core.audit.audit_mgs`).
