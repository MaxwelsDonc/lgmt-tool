LGMT documentation
==================

**LGMT** (Logic-Grounded Metamorphic Testing) checks whether an LLM reasons
*consistently*: it rewrites logical problems into provably equivalent
first-order-logic (FOL) variants, asks the model both, and flags every
self-contradiction. It is the tool companion of *"LGMT: Logic-Grounded
Metamorphic Testing for Evaluating the Reasoning Reliability of LLMs"*
(Knowledge-Based Systems, in press).

LGMT gives you:

- **20 first-order-logic metamorphic relations** — equivalence-law
  rewriting of FOL syntax trees (De Morgan, contraposition, quantifier
  dualities, premise restructuring, symbol renaming), plus auto-discovery
  for custom MRs;
- **Z3-guarded correctness** — every built-in MR's equivalence preservation
  is verified by SMT-based tests;
- **CLI + zero-dependency Web Studio** targeting any OpenAI-compatible
  endpoint — commercial APIs or local vLLM/Ollama — plus an offline mock
  mode that runs without an API key;
- **Self-contained HTML defect reports** — your model ranked against six
  reference SOTA LLMs, per-MR drill-down metrics, side-by-side FOL/NL
  diffs, and collapsible CoT reasoning traces;
- **Bundled 3,091-group evaluation benchmark** with documented provenance.

The same functionality is available three ways: the command line
(``lgmt <command>``), the Web Studio (``lgmt web``), and the Python
library (``import lgmt``).

.. toctree::
   :maxdepth: 2
   :caption: Getting started

   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Guides

   guides/demo
   guides/benchmark
   guides/custom-cases
   guides/custom-mrs

.. toctree::
   :maxdepth: 2
   :caption: Reference

   data-formats
   mr-catalog
   api
   recipes
