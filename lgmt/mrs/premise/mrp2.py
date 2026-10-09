'''
MR-P2: Premise Duplication

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
    except AttributeError:
        pass


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P2: Premise Duplication
# =============================================================================

class MRP2(MetamorphicRelation):
    """
    MR-P2: premise duplication
    
    Rule: randomly pick n premises from Γ, duplicate them, and append the copies.
    Applies to: test cases with at least 1 premise.
    
    Rationale: in FOL duplicating a premise does not change entailment.
    E.g. {P(a), Q(b)} |- R(c) is equivalent to {P(a), P(a), Q(b)} |- R(c).
    
    The added redundancy carries no new information, probing robustness to noise.
    
    Args:
        n_duplicates: how many premises to duplicate (default 1)
                     - if >= premise count, every premise is duplicated once
                     - otherwise n_duplicates distinct premises are sampled
    """
    
    def __init__(self, n_duplicates: int = 1):
        self.index = "MR-P2"
        self.name = "Premise Duplication"
        self.n_duplicates = max(1, n_duplicates)  # at least one copy

    # =========================================================================
    # standard MR interface implementation
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P2 is universal: any test case with premises.
        """
        return []  # universal
    def check_applicability_logic(self, fol: str) -> bool:
        """
        Per-formula applicability check (MR-P2 applies to every formula).
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        MR-P2 checks the premise count, not individual formulas.
        """
        return True  # always true for a single formula

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        Check whether MR-P2 applies to the test case.
        
        Requires at least 1 premise (nothing to duplicate otherwise).
        """
        return len(test_case.premises_logic) >= 1

    def transform(self, stc: TestCase) -> TestCase:
        """
        Perform the premise duplication.
        
        Steps:
        1. Copy the premise lists (logic and text).
        2. Randomly pick n_duplicates premises (all of them if fewer).
        3. Append copies of the picked premises.
        4. Keep the conclusion unchanged.
        5. Return the new TestCase.
        """
        # check applicability
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P2 not applicable: need at least 1 premise, got {len(stc.premises_logic)}")
            return stc
        
        # copy the premise lists
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # resolve the actual number of copies
        actual_n = min(self.n_duplicates, len(new_premises_logic))
        
        # sample actual_n distinct premise indices
        if actual_n >= len(new_premises_logic):
            # duplicating everything when n >= premise count
            duplicate_indices = list(range(len(new_premises_logic)))
        else:
            # otherwise sample actual_n distinct premises
            duplicate_indices = random.sample(range(len(new_premises_logic)), actual_n)
        
        # append copies of the picked premises
        for idx in duplicate_indices:
            new_premises_logic.append(new_premises_logic[idx])
            # (copies keep the original text; no tag needed)
            new_premises_text.append(new_premises_text[idx])
        
        # return the new TestCase with the conclusion unchanged
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # preserve metadata
        )
