"""
MR-C3: Double Negation
Rule: (Γ, q) => (Γ, --q)
"""
import copy
import sys
import os


from typing import List
from nltk.sem.logic import LogicParser, NegatedExpression
from lgmt.core.structure import MetamorphicRelation, TestCase

class MRC3(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-C3"
        self.name = "Double Negation"

    def check_applicability_logic(self, fol: str) -> bool:
        return True

    def source_templates(self) -> List[str]:
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        return bool(test_case.conclusion_logic)

    def transform(self, source_TC: TestCase) -> TestCase:
        """
        Transform:
        Logic: q -> --q
        Text:  text -> [Changed_Conclusion] It is not the case that not (text)
        """
        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()

        def _normalize(s: str) -> str:
            if not s: return ""
            return s.replace("∀", "all ").replace("∃", "exists ").replace("→", "->").replace("↔", "<->").replace("¬", "-").replace("∧", "&").replace("∨", "|")

        try:
            ascii_formula = _normalize(source_TC.conclusion_logic)
            ast = parser.parse(ascii_formula)
            # double negation: -(-Original)
            new_ast = NegatedExpression(NegatedExpression(ast))
            new_conclusion_logic = str(new_ast)
            # update the text
            new_conclusion_text = f"[Changed_conclusion] It is not the case that not ({source_TC.conclusion_text})"

            follow_TC.conclusion_logic = new_conclusion_logic
            follow_TC.conclusion_text = new_conclusion_text
            
            return follow_TC

        except Exception as e:
            return source_TC


if __name__ == "__main__":
    from colorama import Fore, Style
    print("=" * 80)
    print("Testing MRC3 (Double Negation)")
    print("=" * 80)

    mock_case = TestCase(
        premises_text=["No logic is flawed."], 
        conclusion_text="It is not the case that logic is flawed.",
        premises_logic=["all x. (Logic(x) -> -Flawed(x))"], 
        conclusion_logic="-exists x. (Logic(x) & Flawed(x))" 
    )
    
    print("\n[Original test case]")
    print("  Premises:")
    for i, p in enumerate(mock_case.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  Conclusion logic: {mock_case.conclusion_logic}")
    print(f"  Conclusion text: {mock_case.conclusion_text}")

    # instantiate the MR
    mr = MRC3()
    print(f"\nApplicable: {mr.check_applicability(mock_case)}")
    
    new_case = mr.transform(mock_case)
    
    print("\n[MRC3 transformed]")
    print("  Premises:")
    for i, p in enumerate(new_case.premises_logic, 1):
        print(f"    {i}. {p}")

    print(f"  Conclusion logic: {Fore.GREEN}{new_case.conclusion_logic}{Style.RESET_ALL}")
    print(f"  Conclusion text: {Fore.CYAN}{new_case.conclusion_text}{Style.RESET_ALL}")
    
    print("=" * 80)
  
