"""
MR-C1: Conjunction with Truth
Rule: (Γ, q) => (Γ, q ^ 1)
"""
import copy
import sys
import os

# path adaptation

from typing import List
from nltk.sem.logic import LogicParser, AndExpression
from lgmt.core.structure import MetamorphicRelation, TestCase

class MRC1(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-C1"
        self.name = "Conjunction with Truth"

    def check_applicability_logic(self, fol: str) -> bool:
        return True

    def source_templates(self) -> List[str]:
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        return bool(test_case.conclusion_logic)

    def transform(self, source_TC: TestCase) -> TestCase:
        """
        Transform:
        Logic: q -> q & 1
        Text:  text -> [Changed_Conclusion] (text) and it is true
        """
        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()

        def _normalize(s: str) -> str:
            if not s: return ""
            return s.replace("∀", "all ").replace("∃", "exists ").replace("→", "->").replace("↔", "<->").replace("¬", "-").replace("∧", "&").replace("∨", "|")

        try:
            ascii_formula = _normalize(source_TC.conclusion_logic)
            ast = parser.parse(ascii_formula)
            # build the constant '1' expression node
            true_expr = parser.parse("1")
            
            # (Original) & 1
            new_ast = AndExpression(ast, true_expr)
            new_conclusion_logic = str(new_ast)
            
            new_conclusion_text = f"[Changed_conclusion] ({source_TC.conclusion_text}) and it is true"

            follow_TC.conclusion_logic = new_conclusion_logic
            follow_TC.conclusion_text = new_conclusion_text
            
            return follow_TC

        except Exception as e:
            return source_TC

if __name__ == "__main__":
    from colorama import Fore, Style 

    print("=" * 80)
    print("Testing MRC1 (Conjunction with Truth)")
    print("=" * 80)

    mock_case = TestCase(
        premises_text=["All men are mortal.", "Socrates is a man."], 
        conclusion_text="Socrates is mortal.",
        premises_logic=[
            "all x.(Man(x) -> Mortal(x))", 
            "Man(socrates)"
        ], 
        conclusion_logic="Mortal(socrates)"
    )
    
    print("\n[Original test case]")
    print("  Premises:")
    for i, p in enumerate(mock_case.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  Conclusion logic: {mock_case.conclusion_logic}")
    print(f"  Conclusion text: {mock_case.conclusion_text}")

    # instantiate the MR
    mr = MRC1()
    print(f"\nApplicable: {mr.check_applicability(mock_case)}")
    new_case = mr.transform(mock_case)
    
    print("\n[MRC1 transformed]")
    print("  Premises (must stay unchanged):")
    for i, p in enumerate(new_case.premises_logic, 1):
        status = "(Unchanged)" if p == mock_case.premises_logic[i-1] else "(CHANGED - WARNING!)"
        print(f"    {i}. {p} {status}")

    print(f"  Conclusion logic: {Fore.GREEN}{new_case.conclusion_logic}{Style.RESET_ALL}")
    print(f"  Conclusion text: {Fore.CYAN}{new_case.conclusion_text}{Style.RESET_ALL}")
    
    print("=" * 80)
