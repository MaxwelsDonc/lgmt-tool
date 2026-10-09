'''
MR-P1: Premise Reordering

this MR is special because it do not need to regenerate the nl premises
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
    except (AttributeError, ValueError):
        pass  # keep the existing encoding if it cannot be changed


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P1: Premise Reordering
# =============================================================================

class MRP1(MetamorphicRelation):
    """
    MR-P1: premise reordering
    
    Rule: shuffle the premise order randomly; the conclusion stays unchanged.
    Applies to: test cases with at least 2 premises.
    
    Rationale: in FOL the premise order does not affect entailment.
    E.g. {P(a), Q(b)} |- R(c) is equivalent to {Q(b), P(a)} |- R(c).
    """
    
    def __init__(self):
        self.index = "MR-P1"
        self.name = "Premise Reordering"
    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P1 is universal: any test case with multiple premises.
        """
        return []  # universal

    def check_applicability_logic(self, fol: str) -> bool:
        """
        Per-formula applicability check (MR-P1 applies to every formula).
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        MR-P1 checks the premise count, not individual formulas.
        """
        return True  # always true for a single formula

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        Check whether MR-P1 applies to the test case.
        
        Requires at least 2 premises (nothing to reorder otherwise).
        """
        return len(test_case.premises_logic) >= 2

    def transform(self, stc: TestCase) -> TestCase:
        """
        Perform the premise reordering.
        
        Steps:
        1. Copy the premise lists (logic and text).
        2. Shuffle the order with random.shuffle.
        3. Keep the conclusion unchanged.
        4. Return the new TestCase.
        """
        # check applicability
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P1 not applicable: need at least 2 premises, got {len(stc.premises_logic)}")
            return stc
        
        # copy the premise lists
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        original_logic = new_premises_logic.copy()
        
        # build an index list and shuffle it
        indices = list(range(len(new_premises_logic)))
        max_attempts = 20  # avoid an unbounded loop in pathological cases
        attempts = 0
        while attempts < max_attempts:
            random.shuffle(indices)
            # reshuffle if the order came out unchanged
            if [new_premises_logic[i] for i in indices] != original_logic:
                break
            attempts += 1
        
        # reorder premises by the shuffled indices
        new_premises_logic = [new_premises_logic[i] for i in indices]
        # (text tagging disabled: reordering needs no NL regeneration)
        new_premises_text = [new_premises_text[i] for i in indices]
        
        # new_premises_text = [
        #     f"[Changed_{indices[new_pos]}] {new_premises_text[indices[new_pos]]}" 
        #     if indices[new_pos] != new_pos  # tag only moved premises
        #     else new_premises_text[indices[new_pos]]
        #     for new_pos in range(len(indices))
        # ]
        
        # return the new TestCase with the conclusion unchanged
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()
        )
