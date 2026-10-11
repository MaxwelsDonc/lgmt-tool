"""LGMT: Logic-Grounded Metamorphic Testing for LLM logical reasoning.

Apply first-order-logic metamorphic relations to entailment test cases,
run inference against an LLM, and evaluate metamorphic consistency.
"""
from lgmt.core.structure import MetamorphicGroups, MetamorphicRelation, TestCase

__version__ = "0.1.0"

__all__ = [
    "MetamorphicGroups",
    "MetamorphicRelation",
    "TestCase",
    "__version__",
]
