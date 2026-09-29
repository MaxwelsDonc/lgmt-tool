"""
MR-C2: Disjunction with Falsehood 
规则: (Γ, q) => (Γ, q v 0)
"""
import copy
import sys
import os


from typing import List
from nltk.sem.logic import LogicParser, OrExpression
from lgmt.core.structure import MetamorphicRelation, TestCase

class MRC2(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-C2"
        self.name = "Disjunction with Falsehood"

    def check_applicability_logic(self, fol: str) -> bool:
        return True

    def source_templates(self) -> List[str]:
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        return bool(test_case.conclusion_logic)

    def transform(self, source_TC: TestCase) -> TestCase:
        """
        执行变换：
        Logic: q -> q | 0
        Text:  text -> [Changed_Conclusion] (text) or it is false
        """
        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()

        def _normalize(s: str) -> str:
            if not s: return ""
            return s.replace("∀", "all ").replace("∃", "exists ").replace("→", "->").replace("↔", "<->").replace("¬", "-").replace("∧", "&").replace("∨", "|")

        try:
            ascii_formula = _normalize(source_TC.conclusion_logic)
            ast = parser.parse(ascii_formula)
            
            #创建 '0' 的表达式节点
            false_expr = parser.parse("0")
            # (Original) | 0
            new_ast = OrExpression(ast, false_expr)
            new_conclusion_logic = str(new_ast)
            
            #更新文本
            new_conclusion_text = f"[Changed_conclusion] ({source_TC.conclusion_text}) or it is false"

            follow_TC.conclusion_logic = new_conclusion_logic
            follow_TC.conclusion_text = new_conclusion_text
            
            return follow_TC

        except Exception as e:
            return source_TC
        
if __name__ == "__main__":
    from colorama import Fore, Style

    print("=" * 80)
    print("测试 MRC2 (Disjunction with Falsehood)")
    print("=" * 80)

    mock_case = TestCase(
        premises_text=["Every student likes pizza."], 
        conclusion_text="Everyone likes pizza.",
        premises_logic=[
            "all x.(Student(x) -> Likes(x, pizza))"
        ], 
        conclusion_logic="all y. Likes(y, pizza)" 
    )
    
    print("\n[原始测试用例 (Original)]")
    print("  前提 (Premises):")
    for i, p in enumerate(mock_case.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  结论 (Conclusion Logic): {mock_case.conclusion_logic}")
    print(f"  结论文本 (Conclusion Text): {mock_case.conclusion_text}")

    # 实例化
    mr = MRC2()
    print(f"\n是否适用: {mr.check_applicability(mock_case)}")
    new_case = mr.transform(mock_case)
    
    print("\n[MRC2 变换后结果]")
    print("  前提 (Premises):")
    for i, p in enumerate(new_case.premises_logic, 1):
        print(f"    {i}. {p}")

    print(f"  结论 (Logic): {Fore.GREEN}{new_case.conclusion_logic}{Style.RESET_ALL}")
    print(f"  结论 (Text):  {Fore.CYAN}{new_case.conclusion_text}{Style.RESET_ALL}")
    
    print("=" * 80)
