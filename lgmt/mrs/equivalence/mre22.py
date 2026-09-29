"""
MR-E2.2: Tautology and Contradiction Elimination
"""
from functools import reduce
import operator
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
    NegatedExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker, get_indiv_vars

# =============================================================================
# MR-E2.2: Tautology and Contradiction Elimination
# =============================================================================

class MRE22(MetamorphicTransform):
    def __init__(self):
        transform_check = MRE22.UtilClass()
        super().__init__(
            index="MR-E2.2", 
            name="Tautology and Contradiction Elimination",
            transformer=transform_check,
            logic_checker=transform_check
        )

    class UtilClass:
        def __init__(self):
            self.expr = None
            self.transform_result = None
            self.check_result = None
            self.util_transformer = MRE22.UtilClass._Transformer()

        # 内部类：专属 Transformer
        class _Transformer(LogicTransformer):
            """
            [Inner Class] 专门为 MR-E2.2 服务的 AST 重写器。
            继承自 metamorphic_relations.mr_equivalence.equivalence_utils.LogicTransformer，复用其遍历能力。
            """
            def transform(self, expr: Expression) -> Expression:
                """
                规则: 递归提取且或，匹配是否有非表达式
                """
                if isinstance(expr, (AndExpression, OrExpression)):
                    elements = []
                    def reduction(sub_expr: AndExpression | OrExpression, target_class):
                        if isinstance(sub_expr.first, target_class):
                            reduction(sub_expr.first, target_class)
                        else:
                            elements.append(self.transform(sub_expr.first))
                        if isinstance(sub_expr.second, target_class):
                            reduction(sub_expr.second, target_class)
                        else:
                            elements.append(self.transform(sub_expr.second))
                    reduction(expr, expr.__class__)

                    positive_expr = []
                    negative_expr = []
                    for e in elements:
                        if isinstance(e, NegatedExpression):
                            negative_expr.append(e)
                        else:
                            positive_expr.append(e)
                    for i in range(len(positive_expr)):
                        for j in range(len(negative_expr)):
                            if positive_expr[i] == negative_expr[j].term:
                                if isinstance(expr, AndExpression):
                                    return Expression.fromstring('0')
                                elif isinstance(expr, OrExpression):
                                    return Expression.fromstring('1')
                    return expr
                else:
                    return self.recursive(expr)

        def _transform(self, expr: Expression) -> None:
            self.transform_result = self.util_transformer.transform(expr)
            self.check_result = self.transform_result != expr
            self.expr = expr
        
        def check(self, expr: Expression) -> bool:
            if self.expr is None or self.expr != expr:
                self._transform(expr)
                return self.check_result
            else:
                return self.check_result
        
        def transform(self, expr: Expression) -> Expression:
            if self.expr is None or self.expr != expr:
                self._transform(expr)
                return self.transform_result
            else:
                return self.transform_result

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "a & -a", "-a | a", "a & b & c & -a", "a & b | -a"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE22()
    
    # 运行检查
    mr.sanity_check()