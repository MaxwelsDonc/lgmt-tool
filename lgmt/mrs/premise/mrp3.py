'''
MR-P3: Irrelevant Premise Extension

this MR is special because it do not need to regenerate the nl premises
'''
import sys
from pathlib import Path
import random
import json
from typing import List, Dict, Any

# force UTF-8 stdout so unicode formulas print correctly (once)
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass  # keep the existing encoding if it cannot be changed


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase


class MRP3(MetamorphicRelation):
    """
    MR-P3: irrelevant extension
    
    Rule: add a logically irrelevant (but consistent) premise to Γ.
    
    Irrelevant-premise generation:
    - arithmetic identities such as "1+1=2", "5*2=10"
    """
    
    def __init__(self):
        self.index = "MR-P3"
        self.name = "Irrelevant Extension"

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P3 is universal: any test case.
        """
        return []  # universal

    def check_applicability_logic(self, fol: str) -> bool:
        """
        Per-formula applicability check (MR-P3 applies to every formula).
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        MR-P3 applies to every formula.
        """
        return True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        Check whether MR-P3 applies to the test case.
        
        Always applicable: an irrelevant premise can extend any premise set.
        """
        return True

    # =========================================================================
    # irrelevant-premise generation
    # =========================================================================
    def _generate_arithmetic_formula(self) -> tuple:
        """
        Generate a random arithmetic formula (the irrelevant premise).
        Uses powers for a non-trivial shape.
        
        Returns:
            tuple: (logic form, natural-language form)
        """
        # powers of a small base
        num1 = random.randint(2, 12)
        power = random.randint(2, 4)
        result = num1 ** power
        logic = f"{num1}^{power}={result}"
        text = f"{num1} to the power of {power} equals {result}."
        
        return logic, text

    def _generate_irrelevant_premise(self) -> tuple:
        """
        Generate one irrelevant premise.
        
        Returns:
            tuple: (logic form, natural-language form)
        """
        return self._generate_arithmetic_formula()

    # =========================================================================
    # main transform
    # =========================================================================
    def transform(self, stc: TestCase) -> TestCase:
        """
        Perform the irrelevant extension.
        
        Steps:
        2. Generate an irrelevant premise (arithmetic identity).
        3. Append it to the premise set.
        4. Keep the conclusion unchanged.
        5. Return the new TestCase.
        """
        
        # copy the premise lists
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # generate the irrelevant premise
        irrelevant_logic, irrelevant_text = self._generate_irrelevant_premise()
        
        # append it to the premise set
        new_premises_logic.append(irrelevant_logic)
        # (tagging note)
        # an [Added_{index}] tag would mark the appended premise at position index
        index = len(new_premises_logic) - 1  # index of the new premise
        new_premises_text.append(irrelevant_text)
        
        # return the new TestCase with the conclusion unchanged
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # preserve metadata
        )

