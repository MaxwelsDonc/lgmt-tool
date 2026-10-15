Extending LGMT with a custom MR
===============================

Inspect all currently registered MRs at any time:

.. code-block:: bash

    lgmt list-mrs

Implementing a relation
-----------------------

Subclass :class:`~lgmt.core.structure.MetamorphicRelation` and implement
four methods:

.. code-block:: python

    from lgmt.core.structure import MetamorphicRelation, TestCase

    class MyMR(MetamorphicRelation):
        def __init__(self):
            self.index = "MR-X1"          # unique id, shown in reports
            self.name = "My Relation"     # human-readable name

        def check_applicability_logic(self, fol: str) -> bool:
            ...                            # can a single FOL formula use this MR?

        def source_templates(self) -> list[str]:
            return []                      # minimal applicable patterns ([] = universal)

        def check_applicability(self, tc: TestCase) -> bool:
            ...                            # can this test case use this MR?

        def transform(self, tc: TestCase) -> TestCase:
            ...                            # the follow-up case: (Γ, q) => (Γ', q')

Every custom MR is **verified for logical equivalence with Z3 before it
can run** (five standard FOL samples; skipped only via ``--no-verify`` —
:func:`~lgmt.mrs.verifier.verify_mr_equivalence_with_z3`). A relation whose
follow-up is not provably equivalent is rejected with an error.

Three ways to register
----------------------

1. **Web Studio drawer** — in Workflow 3 click ``➕ Register Custom MR``,
   edit the pre-filled template, and press ``Verify with Z3 & Register``.
   A green bar confirms ``Z3 Equivalence Verified (5/5)`` and the MR
   joins the category row. *(Executes Python locally — only paste code
   you trust.)*
2. **CLI file loading** — save the class in a ``.py`` file and pass it to
   any MR-consuming command:

   .. code-block:: bash

       lgmt list-mrs --mr-file examples/custom_mr_example.py
       lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl \
                      --mr-file my_mr.py --mr MR-X1 --no-realize

   `examples/custom_mr_example.py
   <https://github.com/MaxwelsDonc/lgmt-tool/blob/main/examples/custom_mr_example.py>`_
   is the runnable reference implementation.
3. **Package drop-in** — save the class in any module under ``lgmt/mrs/``;
   it is discovered and registered automatically on the next import.

Python API
----------

The same machinery is available programmatically
(:mod:`lgmt.mrs`):

- :func:`~lgmt.mrs.load_mr_from_source` — load and register every
  ``MetamorphicRelation`` subclass defined in a source string;
- :func:`~lgmt.mrs.register_mr_class` — validate and register one class;
- :func:`~lgmt.mrs.get_mr` — resolve an MR by class name, index, or fuzzy
  key.

The 20 built-in MRs (see :doc:`/mr-catalog`) use this exact API, and
their equivalence preservation is guarded by Z3-backed tests.
