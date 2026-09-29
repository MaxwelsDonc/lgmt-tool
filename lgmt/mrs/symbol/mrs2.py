"""
MRS2: Predicate Renaming Invariance
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
# MR-S2: Predicate Renaming Invariance
# =============================================================================
class MRS2(MetamorphicRelation):
    def __init__(self):
        self.index="MR-S2"
        self.name="Predicate Renaming Invariance"

    def _extract_predicates(self, expr):
        """递归提取公式中的所有谓词符号"""
        from nltk.sem.logic import ApplicationExpression, BinaryExpression, NegatedExpression, VariableBinderExpression
        predicates = set()
        
        if isinstance(expr, ApplicationExpression):
            func = expr.function
            while isinstance(func, ApplicationExpression):
                func = func.function
            pred_name = str(func)
            predicates.add(pred_name)
            predicates.update(self._extract_predicates(expr.argument))
        elif isinstance(expr, BinaryExpression):
            predicates.update(self._extract_predicates(expr.first))
            predicates.update(self._extract_predicates(expr.second))
        elif isinstance(expr, NegatedExpression):
            predicates.update(self._extract_predicates(expr.term))
        elif isinstance(expr, VariableBinderExpression):
            predicates.update(self._extract_predicates(expr.term))
        
        return predicates
    
    class _PredicateRenamer():
        """
        [Inner Class] 专门为 MR-S2 服务的 AST 重写器。
        替换谓词符号
        """
        def __init__(self, predicate_mapping=None):
            self.predicate_mapping = predicate_mapping if predicate_mapping else {}
        
        def transform(self, expr):
            """遍历AST，替换谓词"""
            if isinstance(expr, ApplicationExpression):
                # 处理谓词应用，如 Man(socrates)
                func = expr.function
                arg = expr.argument
                pred_name = str(func)

                if pred_name in self.predicate_mapping:
                    new_func = func.__class__.fromstring(self.predicate_mapping[pred_name])
                    new_arg = self.transform(arg)
                    return ApplicationExpression(new_func, new_arg)
                else:
                    return self.recursive(expr)
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
        判断是否存在谓词可以替换。
        """
        try:
            expr = LogicParser().parse(fol)
            predicates = self._extract_predicates(expr)
            return len(predicates) > 0
        except:
            return False   
    def source_templates(self) -> List[str]:
        return ["P(a)", "R(x,c)", "all x.(P(x) -> Q(a))", "Mortal(socrates)", "exists y.Loves(john,y)"]

    def check_applicability(self, test_case: TestCase) -> bool:
        """判断数据是否能够运用MRS2变换"""
        premises_logic : List[str] = test_case.premises_logic
        return any(self.check_applicability_logic(s) for s in premises_logic)

    def transform(self, source_TC: TestCase, new_pred_list=None) -> TestCase:
        """
        (Γ, q) => (Γ', q') 其中所有谓词统一重命名
        """
        if new_pred_list is None:
            new_pred_list = ['Pre1', 'Pre2', 'Pre3', 'Pre4', 'Pre5', 'Pre6', 'Pre7', 'Pre8', 'Pre9', 'Pre10']

        follow_TC = copy.deepcopy(source_TC)
        parser = LogicParser()

        # 提取谓词常量
        all_predicates = set()
        for formula in source_TC.premises_logic + [source_TC.conclusion_logic]:
            try:
                expr = parser.parse(formula)
                predicates = self._extract_predicates(expr)
                all_predicates.update(predicates)
            except:
                pass  
        
        # 构建映射
        pred_mapping = {}
        sorted_predicates = sorted(list(all_predicates)) 
        for i, pred in enumerate(sorted_predicates):
            if i < len(new_pred_list):
                pred_mapping[pred] = new_pred_list[i]
            else:
                pred_mapping[pred] = f'Pred{i}'
        
        
        transformer = self._PredicateRenamer(pred_mapping)
        
        # 处理前提
        # 步骤4: 处理前提
        new_premises_logic = []
        new_premises_text = []
        for idx, (p_logic, p_text) in enumerate(zip(source_TC.premises_logic, source_TC.premises_text)):
            try:
                expr = parser.parse(p_logic)
                preds = self._extract_predicates(expr)
                if len(preds) > 0:
                    new_expr = transformer.transform(expr)
                    new_premises_logic.append(str(new_expr))
                    new_premises_text.append(f"[Changed_{idx}] {p_text}")
                else:
                    new_premises_logic.append(p_logic)
                    new_premises_text.append(p_text)
            except Exception as e:
                new_premises_logic.append(p_logic)
                new_premises_text.append(p_text)

        
        # 处理结论
        try:
            expr = parser.parse(source_TC.conclusion_logic)
            if len(self._extract_predicates(expr)) > 0:
                new_expr = transformer.transform(expr)
                new_conclusion_logic = str(new_expr)
                new_conclusion_text = f"[Changed_conclusion] {source_TC.conclusion_text}"
            else:
                new_conclusion_logic = source_TC.conclusion_logic
                new_conclusion_text = source_TC.conclusion_text
        except Exception as e:
            new_conclusion_logic = source_TC.conclusion_logic
            new_conclusion_text

        follow_TC.premises_logic = new_premises_logic
        follow_TC.premises_text = new_premises_text 
        follow_TC.conclusion_logic = new_conclusion_logic
        follow_TC.conclusion_text = new_conclusion_text
        follow_TC.metadata['mapping'] = pred_mapping

       
        return follow_TC
    
if __name__ == "__main__":
    print("=" * 80)
    print("测试 MRS2")
    print("=" * 80)

    # MRS2测试：前提和结论中的常量统一变换
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

    # 实例化 MR-S2
    mr2 = MRS2()

    # 检查适用性
    print(f"\n是否适用 MRS2: {mr2.check_applicability(mock_case)}")

    # 执行 MR-S2 变换
    new2 = mr2.transform(mock_case)
    
    print("\nMRS2变异后的结果:")
    print("  前提:")
    for i, p in enumerate(new2.premises_logic, 1):
        print(f"    {i}. {p}")
    print(f"  结论: {new2.conclusion_logic}")
    print(f"\n常量映射: {new2.metadata.get('mapping', {})}")
    print("=" * 80)
