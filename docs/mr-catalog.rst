Metamorphic relation catalog
=============================

LGMT ships **20 built-in first-order-logic metamorphic relations**, grouped
into four categories. Every relation rewrites the FOL syntax tree of a
test case into a provably equivalent variant — the model under test should
answer both identically. Equivalence preservation of each built-in MR is
guarded by Z3-backed tests.

Resolve any relation programmatically with
:func:`~lgmt.mrs.get_mr` (by class name, index, or fuzzy key), or list
them from the CLI with ``lgmt list-mrs``.

Equivalence laws (MR-E)
-----------------------

**Syntactic equivalence (E1).**

.. list-table::
   :header-rows: 1
   :widths: 12 20 45

   * - Index
     - Class
     - Name
   * - MR-E1.1
     - ``MRE11``
     - Implication and Biconditional Elimination
   * - MR-E1.2
     - ``MRE12``
     - Negation Normalization
   * - MR-E1.3
     - ``MRE13``
     - Quantifier Lifting
   * - MR-E1.4
     - ``MRE14``
     - Structural Normalization
   * - MR-E1.5
     - ``MRE15``
     - Alpha-Renaming
   * - MR-E1.6
     - ``MRE16``
     - Canonical Quantifier Ordering

**Semantic equivalence (E2).**

.. list-table::
   :header-rows: 1
   :widths: 12 20 45

   * - Index
     - Class
     - Name
   * - MR-E2.1
     - ``MRE21``
     - Redundancy Elimination
   * - MR-E2.2
     - ``MRE22``
     - Tautology and Contradiction Elimination
   * - MR-E2.3
     - ``MRE23``
     - Identity and Domination Laws
   * - MR-E2.4
     - ``MRE24``
     - Distributivity Law

Symbol renaming (MR-S)
----------------------

.. list-table::
   :header-rows: 1
   :widths: 12 20 45

   * - Index
     - Class
     - Name
   * - MR-S1
     - ``MRS1``
     - Symbol Renaming Invariance
   * - MR-S2
     - ``MRS2``
     - Predicate Renaming Invariance

Premise restructuring (MR-P)
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 12 20 45

   * - Index
     - Class
     - Name
   * - MR-P1
     - ``MRP1``
     - Premise Reordering
   * - MR-P2
     - ``MRP2``
     - Premise Duplication
   * - MR-P3
     - ``MRP3``
     - Irrelevant Extension
   * - MR-P4
     - ``MRP4``
     - Premise Fusion
   * - MR-P5
     - ``MRP5``
     - Premise Decomposition

Conclusion rewriting (MR-C)
---------------------------

.. list-table::
   :header-rows: 1
   :widths: 12 20 45

   * - Index
     - Class
     - Name
   * - MR-C1
     - ``MRC1``
     - Conjunction with Truth
   * - MR-C2
     - ``MRC2``
     - Disjunction with Falsehood
   * - MR-C3
     - ``MRC3``
     - Double Negation

Custom relations
----------------

Additional relations subclass
:class:`~lgmt.core.structure.MetamorphicRelation` and are Z3-verified at
registration time — see :doc:`/guides/custom-mrs`.
