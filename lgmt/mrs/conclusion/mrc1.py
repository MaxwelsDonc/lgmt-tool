"""
MR-C1: Conjunction with Truth
规则: (Γ, q) => (Γ, q ^ 1)
"""
import copy
import sys
import os

# 路径适配

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
        执行变换：
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
            # 创建  '1' 的表达式节点
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
    print("测试 MRC1 (Conjunction with Truth)")
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
    
    print("\n[原始测试用例 (Original)]")
    print("  前提 (Premises):")
    for i, p in enumerate(mock_case.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  结论 (Conclusion Logic): {mock_case.conclusion_logic}")
    print(f"  结论文本 (Conclusion Text): {mock_case.conclusion_text}")

    # 实例化 MR
    mr = MRC1()
    print(f"\n是否适用 (Applicability): {mr.check_applicability(mock_case)}")
    new_case = mr.transform(mock_case)
    
    print("\n[MRC1 变换后结果 (Transformed)]")
    print("  前提 (Premises) [应保持不变]:")
    for i, p in enumerate(new_case.premises_logic, 1):
        status = "(Unchanged)" if p == mock_case.premises_logic[i-1] else "(CHANGED - WARNING!)"
        print(f"    {i}. {p} {status}")

    print(f"  结论 (Conclusion Logic): {Fore.GREEN}{new_case.conclusion_logic}{Style.RESET_ALL}")
    print(f"  结论文本 (Conclusion Text): {Fore.CYAN}{new_case.conclusion_text}{Style.RESET_ALL}")
    
    print("=" * 80)
