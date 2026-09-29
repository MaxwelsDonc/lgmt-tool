"""
MR-P5: Premise Decomposition
"""
import copy
import sys
import os


from typing import List, Tuple
from lgmt.core.structure import MetamorphicRelation, TestCase
from nltk.sem.logic import LogicParser, AndExpression

# =============================================================================
# MRP5: Premise Decomposition   
# =============================================================================

class MRP5(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-P5"
        self.name = "Premise Decomposition"

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def check_applicability_logic(self, fol: str) -> bool:
        """
        判断这数据能不能用这个 MR。
        只要顶层或递归拆解后是 A & B 结构（且不在量词内部），就可以拆分。
        但在 check 阶段，我们简单检查是否包含 '&' 即可，实际能否拆分由 transform 决定。
        """
        return "&" in fol

    def source_templates(self) -> List[str]:
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        判断这数据能不能用这个 MR。
        只要顶层或递归拆解后是 A & B 结构（且不在量词内部），就可以拆分。
        但在 check 阶段，我们简单检查是否包含 '&' 即可，实际能否拆分由 transform 决定。
        """
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)    
    
    def transform(self, source_TC: TestCase) -> TestCase:
        """
        拆分前提：
        如果前提是 A & B 形式（顶层），则拆分为 A 和 B 两个前提。
        递归执行：A & B & C -> A, B, C
        注意：不处理量词内部的 &。例如 all x.(A(x) & B(x)) 不拆分。
        """
        follow_TC = copy.deepcopy(source_TC)
        new_premises_logic = []
        new_premises_text = []

        parser = LogicParser()

        def split_expression(expression) -> List[str]:
            """
            递归拆分 AndExpression
            """
            if isinstance(expression, AndExpression):
                # 递归拆分左边和右边
                return split_expression(expression.first) + split_expression(expression.second)
            else:
                # 基础情况，返回当前表达式的字符串形式
                return [str(expression)]

        # 遍历每个前提进行处理
        # 使用 enumerate 获取 index
        for index, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                # 尝试解析
                expr = parser.parse(p_logic)
                
                # 检查是否是顶层的 AndExpression
                if isinstance(expr, AndExpression):
                    # 可以拆分
                    split_parts = split_expression(expr)
                    
                    # 将拆分后的部分添加到新列表
                    for part in split_parts:
                        new_premises_logic.append(part)
                        # 显式标记 Changed_{index}，对应 Source TC 的第 index 个前提（0-based）
                        new_premises_text.append(f"[Changed_{index}] {p_text}") 
                else:
                    # 不能拆分 (包括 all x.(A&B) 这种情况，因为顶层是 AllExpression 不是 AndExpression)
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
                    
            except Exception as e:
                # 解析失败，原样保留
                # print(f"Error parsing logic: {p_logic}, error: {e}")
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text
        
        return follow_TC
