'''
MR-P4: Premise Fusion
'''
import sys
from pathlib import Path
import random
import json
from typing import List, Dict, Any

# force UTF-8 stdout so unicode formulas print correctly
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P4: Premise Fusion
# =============================================================================

class MRP4(MetamorphicRelation):
    """
    MR-P4: premise fusion
    {P(a), Q(b)} |- R(c) becomes {P(a) & Q(b)} |- R(c)
    - the two fused premises are removed
    - only the new conjunctive premise remains
    """
    
    def __init__(self):
        self.index = "MR-P4"
        self.name = "Premise Fusion"

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P4 is universal: any test case with multiple premises.
        """
        return []  # universal

    def check_applicability_logic(self, fol: str) -> bool:
        """
        Per-formula applicability check (MR-P4 applies to every formula).
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        Per-formula applicability check.
        """
        return True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        Check whether MR-P4 applies to the test case.
        
        Requires at least 2 premises (nothing to fuse otherwise).
        """
        return len(test_case.premises_logic) >= 2

    # =========================================================================
    # premise fusion
    # =========================================================================
    def _fuse_premises(self, premise1_logic: str, premise2_logic: str,
                      premise1_text: str, premise2_text: str) -> tuple:
        """
        Fuse two premises into a single conjunctive premise.
        
        Args:
            premise1_logic: logic form of the first premise
            premise2_logic: logic form of the second premise
            premise1_text: text form of the first premise
            premise2_text: text form of the second premise
        
        Returns:
            tuple: (fused logic form, fused text form)
        """
        # logic form: joined with &
        # kept ASCII for parser compatibility
        fused_logic = f"({premise1_logic}) & ({premise2_logic})"
        
        # text form: natural-language conjunction
        fused_text = f"Both {premise1_text[0].lower()}{premise1_text[1:].rstrip('.')} and {premise2_text[0].lower()}{premise2_text[1:].rstrip('.')}."
        
        return fused_logic, fused_text

    # =========================================================================
    # main transform
    # =========================================================================
    def transform(self, stc: TestCase) -> TestCase:
        """
        Perform the premise fusion.
        
        Steps:
        1. Check applicability (at least 2 premises).
        2. Sample two distinct premise indices.
        3. Fuse the two premises into a conjunction.
        4. Remove the two original premises.
        5. Append the fused premise to the set.
        6. Keep the conclusion unchanged.
        7. Return the new TestCase.
        """
        # check applicability
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P4 not applicable: need at least 2 premises, got {len(stc.premises_logic)}")
            return stc
        
        # copy the premise lists
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # sample two distinct premise indices
        indices = random.sample(range(len(stc.premises_logic)), 2)
        # sort the indices descending
        idx1, idx2 = sorted(indices, reverse=True)
        
        # fetch the two picked premises
        premise1_logic = stc.premises_logic[min(indices)]
        premise2_logic = stc.premises_logic[max(indices)]
        premise1_text = stc.premises_text[min(indices)]
        premise2_text = stc.premises_text[max(indices)]
        
        # fuse the two premises
        fused_logic, fused_text = self._fuse_premises(
            premise1_logic, premise2_logic,
            premise1_text, premise2_text
        )
        
        # tag the fused premise with both source indices
        fused_text = f"[Changed_{min(indices)}][Changed_{max(indices)}] {fused_text}"
        
        # remove the originals, higher index first to keep indices valid
        del new_premises_logic[idx1]
        del new_premises_logic[idx2]
        del new_premises_text[idx1]
        del new_premises_text[idx2]
        
        # append the fused premise at the end
        new_premises_logic.append(fused_logic)
        new_premises_text.append(fused_text)
        
        # return the new TestCase with the conclusion unchanged
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # preserve metadata
        )
