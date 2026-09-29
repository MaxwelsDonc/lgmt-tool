"""
MR-E1.1: Implication and Biconditional Elimination
"""
from typing import List, Tuple
from nltk.sem.logic import (
    Expression, 
    ImpExpression, 
    IffExpression, 
    AndExpression, 
    OrExpression, 
    NegatedExpression
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer

# =============================================================================
# MR-E1.1: Implication and Biconditional Elimination
# =============================================================================

class MRE11(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.1", 
            name="Implication and Biconditional Elimination",
            transformer=self._Transformer(),
            logic_checker=None
        )

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E1.1 服务的 AST 重写器。
        继承自 utils.logic_visitor.LogicTransformer，复用其遍历能力。
        """
        def transform(self, expr: Expression) -> Expression:
            # 这里的 self 是 _Transformer 实例，不是外部 MR 实例
            # 调用父类 (LogicTransformer) 的 recursive 来递归处理子节点
            if isinstance(expr, ImpExpression):
                # 规则: P -> Q  =>  - P | Q
                left = self.recursive(expr.first)
                right = self.recursive(expr.second)
                return OrExpression(NegatedExpression(left), right)
            elif isinstance(expr, IffExpression):  
                # 规则: P <-> Q => (~P | Q) & (~Q | P)
                left = self.recursive(expr.first)
                right = self.recursive(expr.second)
                
                part1 = OrExpression(NegatedExpression(left), right)
                part2 = OrExpression(NegatedExpression(right), left)
                return AndExpression(part1, part2)
            else:
                return self.recursive(expr)


    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "A -> B", "A <-> B"]

    def check_applicability_logic(self, formula: str) -> bool:
        target_symbols = ["->", "<->"]
        return any(s in formula for s in target_symbols)

if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE11()
    
    # 准备几个经典的逻辑公式（包含 Unicode）
    test_cases = [
        "all x. (MichaelsNeightbor(x) & GrowIn(x, vegetable, garden) -> Have(x, ampleSpace))"
    ]