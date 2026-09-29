"""
MR-E2.4: Distributivity Law
"""
import sys
import os


from functools import reduce
from lgmt.core.structure import TestCase
from nltk.sem.logic import (
    Expression, 
    AndExpression, 
    OrExpression, 
    LogicParser,
)
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker

# =============================================================================
# MR-E2.4: Distributivity Law
# =============================================================================

class MRE24(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E2.4", 
            name="Distributivity Law",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    # 内部类：专属 Transformer
    class _Transformer(LogicTransformer):
        """
        [Inner Class] 专门为 MR-E2.4 服务的 AST 重写器 (优化版)。
        """
        def __init__(self):
            self.targets = [AndExpression, OrExpression]

        def transform(self, expr: Expression) -> Expression:
            if isinstance(expr, (AndExpression, OrExpression)):
                # 1. 识别当前算子 (AND 还是 OR)
                target_class = expr.__class__
                if isinstance(expr, AndExpression):
                    target_id = 0 # Current is AND
                else:
                    target_id = 1 # Current is OR
                
                # 2. [修改点1] 使用 Stack 迭代代替递归 reduction
                # 目的：防止深层嵌套导致 RecursionError
                elements = []
                stack = [expr]
                
                while stack:
                    curr = stack.pop()
                    if isinstance(curr, target_class):
                        # 保持原有顺序 (左->右)，Stack 是后进先出，所以先压右，再压左
                        stack.append(curr.second)
                        stack.append(curr.first)
                    else:
                        # 递归变换子节点 (只变孩子，不变当前层逻辑)
                        elements.append(self.transform(curr))
                
                # 3. [修改点2] 复杂度熔断
                # 如果这一层元素太多(>20)，做分配律会爆炸，直接放弃变换，原样返回扁平化结果
                if len(elements) > 20:
                    return reduce(target_class, elements)

                # 4. 寻找分配机会 (例如在 AND 层里找 OR)
                other_expr_id = None
                search_target_type = self.targets[not target_id]

                for k in range(len(elements)):
                    if isinstance(elements[k], search_target_type):
                        other_expr_id = k
                        break
                
                if other_expr_id is not None:
                    # 找到了！执行分配律
                    other_expr = elements.pop(other_expr_id) # 取出那个 (B | C)
                    
                    # 剩余部分重新组合成 A
                    if elements:
                        rest_expr = reduce(target_class, elements)
                    else:
                        return other_expr 

                    # 构造新公式
                    # 例子: A & (B | C) -> (A & B) | (A & C)
                    new_op_class = self.targets[not target_id] # 外层变 OR
                    inner_op_class = self.targets[target_id]   # 内层变 AND

                    # [修改点3] 移除递归调用 self.transform
                    # 旧代码: return self.transform(new_op_class(...)) -> 会导致死循环
                    # 新代码: 直接返回单次变换结果
                    left_part = inner_op_class(rest_expr, other_expr.first)
                    right_part = inner_op_class(rest_expr, other_expr.second)
                    
                    return new_op_class(left_part, right_part)

                else:
                    # 没找到分配机会，返回扁平化重组后的结果
                    return reduce(target_class, elements)
            else:
                # 其他节点走通用递归
                return self.recursive(expr)
        
    class _LogicChecker(LogicChecker):
        """
        [Inner Class] 专门为 MR-E2.4 服务的 Checker (优化版)。
        """
        def __init__(self):
            self.targets = [AndExpression, OrExpression]

        def check(self, expr: Expression) -> bool:
            if isinstance(expr, (AndExpression, OrExpression)):
                if isinstance(expr, AndExpression):
                    target_id = 0
                else:
                    target_id = 1
                
                # [修改点] 使用 Stack 迭代检查
                stack = [expr]
                target_class = expr.__class__
                opposite_class = self.targets[not target_id]

                while stack:
                    curr = stack.pop()
                    if isinstance(curr, target_class):
                        stack.append(curr.second)
                        stack.append(curr.first)
                    elif isinstance(curr, opposite_class):
                        # 发现目标：例如在 AND 链中发现了 OR
                        return True
                    else:
                        # 检查子节点是否有更深层的机会
                        if self.recursive(curr):
                            return True
                return False
            else:
                return self.recursive(expr)

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> list[str]:
        return [ "a & (b | c)", "a | (b & c) | d", "a | (b & c) | (d & e)"]


if __name__ == "__main__":
    # 实例化你要测的 MR
    mr = MRE24()
    
    # 构造用户提供的测试用例 (Example ID: 594)
    # 这是一个非常复杂的嵌套 XOR 展开结构，可能导致性能问题
    test_case = TestCase(
        premises_logic=[
            "all x. (GreatLake(x) ->((-(((-(((-(((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & (Huron(x))) | ((((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & -(Huron(x))))) & (Erie(x))) | ((((-(((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & (Huron(x))) | ((((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & -(Huron(x))))) & -(Erie(x))))) & (Ontario(x))) | ((((-(((-(((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & (Huron(x))) | ((((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & -(Huron(x))))) & (Erie(x))) | ((((-(((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & (Huron(x))) | ((((-(Superior(x)) & (Michigan(x))) | ((Superior(x)) & -(Michigan(x))))) & -(Huron(x))))) & -(Erie(x))))) & -(Ontario(x)))))",
            "all x. (Erie (x) & MajorSettlement(x) -> In(x, nY) | In(x, pA) | In(x, oH) | In(x, mI))",
            "StateOf(nY, uS) & StateOf(pA, uS) & StateOf(oH, uS) & StateOf(mI, uS)",
            "StateOf(oN, canada)",
            "exists x. (Huron(x) & MajorSettlement(x) & In(x, oN))",
            "all x. all y. (StateOf(x, y) -> In(x, y))",
            "In(us, northAmerica)",
            "all x. (GreatLake(x) -> FormAtEndOf(x, lastGlacialPeriod))"
        ],
        conclusion_logic="exists x. exists y. (Erie(y) & MajorSettlementOf(x, y))",
        premises_text=[
            "The Great Lakes are Lake Superior, Lake Michigan, Lake Huron, Lake Erie, and Lake Ontario.",
            "Some major settlements of Lake Erie are in NY, PA, OH, and MI.",
            "NY, PA, OH, and MI are states in the US.",
            "ON is a state of Canada.",
            "There is a major settlement of Lake Huron in ON.",
            "All states are in their country.",
            "The US is in North America.",
            "The Great Lakes began to form at the end of the Last Glacial Period."
        ],
        conclusion_text="Lake Erie has a major settlement.",
        metadata={
            "label": "True",
            "num_premises": 8,
            "data_source": "FOLIO",
            "example_id": 594
        }
    )
    
    print("Checking applicability...")
    is_applicable = mr.check_applicability(test_case)
    print(f"Is applicable: {is_applicable}")
    
    if is_applicable:
        print("Transforming...")
        try:
            follow_up_case = mr.transform(test_case)
            print("Transformation successful!")
            follow_up_case.display()
        except Exception as e:
            print(f"Transformation failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Test case is not applicable for this MR.")

