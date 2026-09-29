"""
MR-E1.4: Structural Normalization
"""
from functools import reduce
import operator
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker, get_indiv_vars

# =============================================================================
# MR-E1.4: Structural Normalization
# =============================================================================

class MRE14(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.4", 
            name="Structural Normalization",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.4 服务的 AST 重写器。
        继承自 utils.logic_visitor.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            """
            规则: 递归提取且或，按字符串排序
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
                def sort_method(e):
                    e_list = get_indiv_vars(e)
                    e_str = [str(obj) for obj in e_list]
                    return reduce(operator.add, e_str, "")
                elements.sort(key=sort_method)
                result = elements.pop(0)
                while len(elements):
                    result = expr.__class__(result, elements.pop(0))
                return result
            else:
                return self.recursive(expr)
        
    # 内部类：专属 Checker
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E1.4 服务的 AST 重写器。
        继承自 equivalence_utils.LogicChecker，复用其遍历能力。
        """
        def check(self, expr: Expression) -> bool:
            """
            规则: 递归提取且或
            """
            if isinstance(expr, (AndExpression, OrExpression)):
                if isinstance(expr.first, expr.__class__) or isinstance(expr.second, expr.__class__):
                    return True
                else:
                    return self.recursive(expr.first) | self.recursive(expr.second)
            else:
                return self.recursive(expr)

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "c ∨ (b ∨ a)", "a ∧ (b ∧ a)", "c ∨ ((b ∧ d) ∨ a)", "c ∨ ((d ∧ b) ∨ a)"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE14()
    
    # 运行检查
    mr.sanity_check()