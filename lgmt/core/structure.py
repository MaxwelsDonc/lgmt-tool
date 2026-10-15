"""Core data structures:

- test case
- source/follow-up pairs (metamorphic groups)
- metamorphic relations (MR)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from enum import Enum
import re
from colorama import Fore, Style

#===========================================
# test case
#===========================================
@dataclass
class TestCase:
    """An entailment test case: premises (Gamma) and conclusion (q).

    Attributes:
        premises_logic: FOL formulas of the premises, e.g.
            ``["all x.(P(x) -> Q(x))", "P(a)"]``.
        conclusion_logic: FOL formula of the conclusion, e.g. ``"Q(a)"``.
        premises_text: natural-language premises (what the model sees).
        conclusion_text: natural-language conclusion.
        metadata: free-form extras; ``label`` (``True``/``False``/
            ``Unknown``) and ``data_source`` are used by the pipeline.
    """
    # logic-level content
    premises_logic: List[str]  # e.g. ["all x.(P(x) -> Q(x))", "P(a)"]
    conclusion_logic: str      # e.g. "Q(a)"

    # natural-language content (what the model sees)
    premises_text: List[str]   # e.g. ["All humans are mortal.", "Socrates is human."]
    conclusion_text: str       # e.g. "Socrates is mortal."

    # field() so every instance gets a fresh dict
    metadata: Dict[str, Any] = field(default_factory=dict)

    def display(self) -> None:
        """Print all fields to the console."""
        print("=" * 50)
        print("\nLogic level:")
        print("  Premises logic:")
        for i, premise in enumerate(self.premises_logic, 1):
            print(f"    {i}. {premise}")
        print(f"  Conclusion logic: {self.conclusion_logic}")

        print("\nNatural language:")
        print("  Premises text:")
        for i, premise in enumerate(self.premises_text, 1):
            print(f"    {i}. {premise}")
        print(f"  Conclusion text: {self.conclusion_text}")

        print("\nMetadata:")
        if self.metadata:
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
        else:
            print("  (none)")
        print("=" * 50)


#===========================================
#  Metamorphic groups
#===========================================
@dataclass
class MetamorphicGroups:
    """
    One MR application: source case -> follow-up case,
    i.e. (Γ, q) => (Γ', q').

    Attributes:
        source_case: the original entailment test case.
        followup_case: the transformed, provably equivalent variant.
        mr_name: human-readable name of the relation that produced the
            pair, e.g. ``"Negation Normalization"``.
        metadata: pipeline extras; ``mg_id``, ``mr_index``, ``mr_name``,
            and ``data_source`` are set by the builder.
    """
    source_case: TestCase
    followup_case: TestCase

    # which MR produced this pair, e.g. "MR-E1.2 (Negation Normalization)"
    mr_name: str
    # field() so every instance gets a fresh dict
    metadata: Dict[str, Any] = field(default_factory=dict)

    def display(self) -> None:
        """Print all fields to the console."""
        print("=" * 50)
        print("\nMR name:")
        print(f" {self.mr_name}")
        print("=" * 50)

        print("\nSource test case:")
        self.source_case.display()

        print("\nFollow-up test case:")
        self.followup_case.display()

        print("\nMetadata:")
        if self.metadata:
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
        else:
            print("  (none)")
        print("=" * 50)

#===========================================
# metamorphic relations (MR)
#===========================================

class MetamorphicRelation(ABC):
    """Abstract base class for all metamorphic relations."""
    index: str
    name: str
    @abstractmethod
    def check_applicability_logic(self, fol: str) -> bool:
        """Check whether a single FOL formula can use this MR."""
        return False

    @abstractmethod
    def source_templates(self) -> List[str]:
        """
        Source-case templates this MR applies to.
        An empty list means the MR is universal (any structure).
        """
        return []

    @abstractmethod
    def check_applicability(self,test_case: TestCase) -> bool:
        """Check whether this MR applies to the given test case."""
        return False

    @abstractmethod
    def transform(self, source_case: TestCase) -> TestCase:
        """
        Core method: map a source case to its follow-up case,
        i.e. (Gamma, q) => (Gamma', q').
        """
        pass
