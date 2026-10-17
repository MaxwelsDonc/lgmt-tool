Data formats & metrics
======================

Source test case
----------------

One JSON object per line (``.jsonl``). All four shapes below are accepted
by :func:`~lgmt.core.builder.parse_and_normalize_cases`:

.. code-block:: json

    {
      "premises_text": ["All humans are mortal.", "Socrates is human."],
      "conclusion_text": "Socrates is mortal.",
      "premises_logic": ["all x.(H(x) -> M(x))", "H(s)"],
      "conclusion_logic": "M(s)",
      "metadata": {"label": "True", "data_source": "folio"}
    }

- ``premises_text`` / ``conclusion_text`` — natural language (English or
  Chinese). Optional if logic fields are present.
- ``premises_logic`` / ``conclusion_logic`` — NLTK FOL formulas (ASCII
  ``all x.`` / ``exists x.`` / ``-`` / ``&`` / ``|`` / ``->`` / ``<->``,
  or the Unicode equivalents).
- ``raw_text`` — alternative to the fields above: one unstructured
  paragraph the LLM extracts premises/conclusion from.
- ``metadata.label`` — ground-truth verdict: ``True`` / ``False`` /
  ``Unknown`` (optional; canonicalized by
  :mod:`lgmt.utils.labels`).

Metamorphic group (MG) record
-----------------------------

Produced by ``lgmt build-mgs`` /
:func:`~lgmt.core.builder.build_metamorphic_groups` and consumed by
``lgmt run``:

.. code-block:: json

    {
      "source_case": {"premises_logic": ["all x.(H(x) -> M(x))", "H(s)"],
                      "conclusion_logic": "M(s)",
                      "premises_text": ["All humans are mortal.", "Socrates is human."],
                      "conclusion_text": "Socrates is mortal.",
                      "metadata": {"label": "True", "data_source": "folio"}},
      "followup_case": {"premises_logic": ["all x.(H(x) -> M(x))", "H(s)"],
                        "conclusion_logic": "M(s)",
                        "premises_text": ["All humans are mortal.", "Socrates is human."],
                        "conclusion_text": "Socrates is mortal.",
                        "metadata": {"label": "True", "data_source": "folio"}},
      "mr_name": "Negation Normalization",
      "metadata": {"mg_id": "mg_1_1", "mr_index": "MR-E1.2",
                   "mr_name": "Negation Normalization", "data_source": "folio"}
    }

Inference result record
-----------------------

One JSON object per line, written by
:func:`~lgmt.core.runner.process_group`:

.. code-block:: json

    {
      "mg_id": "mg_1_1",
      "mr_name": "Negation Normalization",
      "mr_index": "MR-E1.2",
      "data_source": "folio",
      "model": "deepseek-flash",
      "prompting": "zero_cot",
      "ground_truth": "True",
      "source_input": {"premises_logic": ["all x.(H(x) -> M(x))", "H(s)"],
                       "conclusion_logic": "M(s)",
                       "premises_text": ["All humans are mortal.", "Socrates is human."],
                       "conclusion_text": "Socrates is mortal."},
      "followup_input": {"premises_logic": ["all x.(H(x) -> M(x))", "H(s)"],
                         "conclusion_logic": "M(s)",
                         "premises_text": ["All humans are mortal.", "Socrates is human."],
                         "conclusion_text": "Socrates is mortal."},
      "source_response": {"reasoning": "...", "response_label": "True", "is_correct": true},
      "followup_response": {"reasoning": "...", "response_label": "False", "is_correct": false},
      "is_consistent": false,
      "is_valid": true
    }

Records that exhausted every retry carry ``"error": "..."`` and
``"is_valid": false``; they are excluded from every metric denominator
and counted under ``failed``.

``config.yaml``
---------------

Copy ``config.example.yaml``:

.. code-block:: yaml

    model:
      name: deepseek-flash          # served model name (or an alias)
      base_url: "https://api.deepseek.com"
      api_key: ""                   # prefer the LGMT_API_KEY env var
      temperature: 0.0              # ignored for reasoning models
      aliases:                      # short name -> served model name
        chatgpt: gpt-4o

    inference:
      prompting: zero_direct        # zero_direct | zero_cot | few_direct | few_cot
      max_workers: 100              # thread-pool size

Evaluation metrics
------------------

Computed by :func:`~lgmt.utils.metrics.compute_metrics` (formulas follow
the LGMT evaluation):

- **MVR** (Metamorphic Violation Rate) — fraction of MGs whose source and
  follow-up verdicts disagree. The headline consistency metric.
- **ACC-static** — accuracy on source cases; **ACC-cons** — accuracy on
  both cases of a group.
- **HDR** (Hidden Defect Rate) — among judged pairs, the fraction
  where the source verdict is correct and the follow-up verdict is wrong
  (the violations that actually flip a correct answer).
- **FUR** (False Unreported Rate) — fraction of MGs where both
  verdicts are wrong yet consistent: the consistency oracle cannot flag
  them, so a low MVR does not imply a sound model.

The HTML report also shows a per-MR and per-category breakdown, and
compares your model against six reference SOTA LLMs on the same caliber.
