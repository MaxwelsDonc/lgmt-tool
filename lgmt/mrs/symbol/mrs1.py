"""
MRS1: Constant Renaming Invariance
"""
import copy
import sys
import os


from typing import List, Tuple
from lgmt.core.structure import MetamorphicRelation, TestCase
from nltk.sem.logic import(
    LogicParser, 
    AbstractVariableExpression, 
    VariableBinderExpression, 
    ApplicationExpression, 
    BinaryExpression, 
    NegatedExpression
)


# =============================================================================
# MR-S1: Constant Renaming Invariance
# =============================================================================
class MRS1(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-S1"
        self.name = "Symbol Renaming Invariance"

    def _extract_constants(self,expr, bound_vars=None, in_arg=False, in_app=False):
        """递归提取公式中的个体常量（只提取作为参数出现的个体常量，不提取谓词名或独立命题符号）。
        """
        if bound_vars is None:
            bound_vars = set()

        # 常见的逻辑变量名，不视为常量
        common_vars = {'x', 'y', 'z', 'u', 'v', 'w', 't', 's'}
        constants = set()

        if isinstance(expr, VariableBinderExpression):
            # 量词表达式 (all x.P(x), exists y.Q(y))
            new_bound = bound_vars | {str(expr.variable)}
            constants.update(self._extract_constants(expr.term, new_bound, in_arg=False, in_app=False))

        elif isinstance(expr, ApplicationExpression):
            # 函数应用 (P(a), R(x,y))。
            constants.update(self._extract_constants(expr.function, bound_vars, in_arg=False, in_app=True))
            constants.update(self._extract_constants(expr.argument, bound_vars, in_arg=True, in_app=True))
        
        elif isinstance(expr, AbstractVariableExpression):
            # 变量或常量。
            var_name = str(expr)
            if in_arg and var_name not in bound_vars and var_name not in common_vars:
                constants.add(var_name)

        elif isinstance(expr, BinaryExpression):
            # 二元表达式 (A & B, A | B, A -> B)
            constants.update(self._extract_constants(expr.first, bound_vars, in_arg=False, in_app=False))
            constants.update(self._extract_constants(expr.second, bound_vars, in_arg=False, in_app=False))

        elif isinstance(expr, NegatedExpression):
            # 否定表达式 (-A)
            constants.update(self._extract_constants(expr.term, bound_vars, in_arg=False, in_app=False))

        return constants
    
    class _SymbolRenamer():
        """
        替换个体常量
        """
        def __init__(self, const_mapping=None):
            self.const_mapping = const_mapping if const_mapping else {}
        
        def transform(self, expr):
            """遍历AST，替换常量"""
            if isinstance(expr, AbstractVariableExpression):
                var_name = str(expr)
                if var_name in self.const_mapping:
                    # 替换常量
                    return expr.__class__.fromstring(self.const_mapping[var_name])
                else:
                    return expr
            else:
                return self.recursive(expr)
        
        def recursive(self, expr):
            """递归处理各种类型的表达式"""
            if isinstance(expr, VariableBinderExpression):
                # 处理量词表达式 (all x.P(x), exists y.Q(y))
                return expr.__class__(expr.variable, self.transform(expr.term))
            
            elif isinstance(expr, ApplicationExpression):
                # 处理函数应用 (P(a), R(x,y))
                return ApplicationExpression(self.transform(expr.function), self.transform(expr.argument))
            
            elif isinstance(expr, BinaryExpression):
                # 处理二元表达式 (A & B, A | B, A -> B)
                return expr.__class__(self.transform(expr.first), self.transform(expr.second))
            
            elif isinstance(expr, NegatedExpression):
                # 处理否定表达式 (-A)
                return NegatedExpression(self.transform(expr.term))
            
            else:
                # 其他类型直接返回
                return expr
    
    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def check_applicability_logic(self, fol: str) -> bool:
        """
        判断是否存在常量可以替换。
        """
        try:
            expr = LogicParser().parse(fol)
            constants = self._extract_constants(expr)
            return len(constants) > 0
        except:
            return False   
    def source_templates(self) -> List[str]:
        return ["P(a)", "R(x,c)", "all x.(P(x) -> Q(a))", "Mortal(socrates)", "exists y.Loves(john,y)"]

    def check_applicability(self, test_case: TestCase) -> bool:
        """判断数据是否能够运用MRS1"""
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)
    
    def transform(self, source_TC: TestCase, new_const_list=None) -> TestCase:
        """
        (Γ, q) => (Γ', q') 其中所有常量统一重命名
        将前提和结论中的所有个体常量替换为新的常量名
        """
        if new_const_list is None:
            new_const_list = ['Con1', 'Con2', 'Con3', 'Con4', 'Con5', 'Con6', 'Con7', 'Con8', 'Con9', 'Con10']
        
        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()
        
        # 步骤1: 提取所有常量
        all_constants = set()
        for formula in source_TC.premises_logic + [source_TC.conclusion_logic]:
            try:
                expr = parser.parse(formula)
                constants = self._extract_constants(expr)
                all_constants.update(constants)
            except Exception as e:
                pass
        
        # 步骤2: 构建常量映射
        const_mapping = {}
        sorted_constants = sorted(list(all_constants))
        for i, const in enumerate(sorted_constants):
            if i < len(new_const_list):
                const_mapping[const] = new_const_list[i]
            else:
                const_mapping[const] = f'Con{i+1}'
        
        # 步骤3: 创建转换器
        transformer = self._SymbolRenamer(const_mapping)
        
        # 步骤4: 处理前提
        new_premises_logic = []
        new_premises_text = []
        for idx, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                expr = parser.parse(p_logic)
                consts = self._extract_constants(expr)
                if consts:
                    new_expr = transformer.transform(expr)
                    new_premises_logic.append(str(new_expr))
                    new_premises_text.append(f"[Changed_{idx}] {p_text}")
                else:
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
            except Exception:
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        # 步骤5: 处理结论
        try:
            expr = parser.parse(source_TC.conclusion_logic)
            if self._extract_constants(expr):
                new_conclusion = str(transformer.transform(expr))
                new_conclusion_text = f"[Changed_conclusion] {source_TC.conclusion_text}"
            else:
                new_conclusion = source_TC.conclusion_logic
                new_conclusion_text = source_TC.conclusion_text
        except Exception:
            new_conclusion = source_TC.conclusion_logic
            new_conclusion_text = source_TC.conclusion_text

        # 步骤6: 更新follow-up测试用例
        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text
        follow_TC.conclusion_logic = new_conclusion
        follow_TC.conclusion_text = new_conclusion_text
        follow_TC.metadata["mapping"] = const_mapping

        return follow_TC
    
if __name__ == "__main__":
    print("=" * 80)
    print("测试 MRS1")
    print("=" * 80)

    # MRS1测试：前提和结论中的常量统一变换
    mock_case = TestCase(
        premises_text=["All men are mortal.", "Socrates is a man.","w","x","y","z","a","b","c","d","e"], 
        conclusion_text="Socrates is mortal.",
        premises_logic=[
            "P(a)", 
            "Q(x,y)", 
            "R(x,a,c)", 
            "L(c,d)",
            "Man(socrates)", 
            "all x.(Man(x) -> Mortal(x))", 
            "exists y.Loves(john,y)",
            "J(socrates)",
            "K(b,g,h,l)",
            "M(x,n)",
            "O(q,r)",
        ], 
        conclusion_logic="Mortal(socrates)"
    )
    
    print("\n原始测试用例逻辑公式:")
    print("  前提:")
    for i, p in enumerate(mock_case.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  结论: {mock_case.conclusion_logic}")

    # 实例化 MR-S1
    mr1 = MRS1()

    # 检查适用性
    print(f"\n是否适用 MRS1: {mr1.check_applicability(mock_case)}")

    # 执行 MR-S1 变换
    new1 = mr1.transform(mock_case)
    
    print("\nMRS1变异后的结果:")
    print("  前提:")
    for i, p in enumerate(new1.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  结论: {new1.conclusion_logic}")
    print(f"\n常量映射: {new1.metadata.get('mapping', {})}")
    print("=" * 80)

        
