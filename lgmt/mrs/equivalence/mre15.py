"""
MR-E1.5: Alpha-Renaming (Stream-based Implementation)
"""
import operator
from functools import reduce
import sys
import os

# 路径适配

# 1. NLTK 核心组件导入
from nltk.sem.logic import (
    Expression, 
    BinaryExpression, 
    IndividualVariableExpression, 
    Variable,
    QuantifiedExpression,
    ApplicationExpression,
    FunctionVariableExpression,
    LambdaExpression,
    ConstantExpression,
    NegatedExpression,
    EqualityExpression
)

# 2. 自定义基类导入
from lgmt.mrs.equivalence.equivalence_utils import MetamorphicTransform, LogicTransformer, LogicChecker

from lgmt.core.structure import TestCase

# =============================================================================
# 辅助函数：全局扫描用 (用于生成不冲突的新名字)
# =============================================================================
def get_vars_final(e) -> list:
    """提取所有变量和常量，用于初始化全局保留名单"""
    if isinstance(e, (QuantifiedExpression, LambdaExpression)):
        return [(e.variable, 'Binder')] + get_vars_final(e.term)
    elif isinstance(e, FunctionVariableExpression):
        return []
    elif isinstance(e, IndividualVariableExpression):
        return [(e.variable, 'Argument')] 
    elif isinstance(e, ConstantExpression):
        return [(e.variable, 'Argument')]
    else:
        # 对于 Application 和 Binary 等，递归收集
        return e.visit(get_vars_final, lambda parts: reduce(operator.add, parts, []))

# =============================================================================
# 主类实现
# =============================================================================
class MRE15(MetamorphicTransform):
    def __init__(self):
        super().__init__(
            index="MR-E1.5", 
            name="Alpha-Renaming",
            transformer=self._Transformer(),
            logic_checker=self._LogicChecker()
        )

    class _Transformer(LogicTransformer):
        """
        [Scope-aware Transformer]
        策略：
        1. 收集整个表达式的自由变量 (Free Variables)，这些名字是绝对不能被 Binder 重用的。
        2. 维护一个 forbidden_names 集合，初始包含所有自由变量。
        3. 遍历时，每遇到一个量词 (Binder x)：
           - 如果 x 在 forbidden_names 中：
             - 生成新名字 z (保证不冲突)。
             - Alpha-convert x -> z。
             - 将 z 加入 forbidden_names。
           - 否则：
             - 将 x 加入 forbidden_names (防止后续量词重用造成 shadowing 或 conflict)。
        """
        def __init__(self, original_expr: Expression = None):
            self.index = 1
            self._global_reserved = set()
            self.forbidden_names = set()
            
            if original_expr:
                self._scan_reserved(original_expr)

        def _scan_reserved(self, expr):
            """预扫描：记录公式原有的所有名字，防止生成的新名字 z1 撞车"""
            all_vars = get_vars_final(expr)
            self._global_reserved.update({var.name for var, role in all_vars})

        def _get_new_var(self) -> Variable:
            """生成全局唯一变量名 (bv1, bv2...)"""
            while True:
                name = f'bv{self.index}'
                # 新名字既不能是全局原本就有的，也不能是当前 forbidden 的
                if name not in self._global_reserved and name not in self.forbidden_names:
                    self._global_reserved.add(name)
                    return Variable(name)
                self.index += 1

        def transform(self, expr: Expression) -> Expression:
            """入口方法"""
            # 1. 如果没初始化过全局名单，先扫描
            if not self._global_reserved:
                self._scan_reserved(expr)
            
            # 2. 初始化 forbidden_names 为所有自由变量
            # free() 方法返回 set of Variables
            self.forbidden_names = {v.name for v in expr.free()}
            
            # 3. 启动遍历
            return self.visit(expr)

        def visit(self, expr):
            """
            核心分发器 (Dispatcher)
            """
            method_name = f"visit_{expr.__class__.__name__}"
            if hasattr(self, method_name):
                return getattr(self, method_name)(expr)
            
            # 通用回退逻辑
            return expr.visit(self.visit, lambda parts: expr.__class__(*parts))

        def visit_QuantifiedExpression(self, expr):
            var_name = expr.variable.name
            
            # 检查冲突：如果变量名已被禁止 (是自由变量，或已被前序量词使用)
            if var_name in self.forbidden_names:
                new_var = self._get_new_var()
                # Alpha-convert
                expr = expr.alpha_convert(new_var)
                # 记录新名字已被使用
                self.forbidden_names.add(new_var.name)
            else:
                # 记录该名字已被使用
                self.forbidden_names.add(var_name)
            
            # 递归处理 term
            new_term = self.visit(expr.term)
            
            return expr.__class__(expr.variable, new_term)

        def visit_ExistsExpression(self, expr):
            return self.visit_QuantifiedExpression(expr)

        def visit_AllExpression(self, expr):
            return self.visit_QuantifiedExpression(expr)


        def visit_LambdaExpression(self, expr):
            # Lambda 处理逻辑同量词
            return self.visit_QuantifiedExpression(expr)

        def visit_IndividualVariableExpression(self, expr):
            return expr

        def visit_ConstantExpression(self, expr):
            return expr

        def visit_FunctionVariableExpression(self, expr):
            return expr
            
        def visit_AbstractVariableExpression(self, expr):
            return expr


        # 为具体的 Binary 类型提供支持 (虽然上面的 fallback 应该能处理)
        # 只要 AndExpression(left, right) 构造函数存在即可

    class _LogicChecker(LogicChecker):
        """逻辑检查器：沿用之前的逻辑"""
        def check(self, expr: Expression) -> bool:
            ordered_vars = get_vars_final(expr)
            seen = set()
            for var_obj, role in ordered_vars:
                name = var_obj.name
                if role == 'Argument':
                    seen.add(name)
                elif role == 'Binder':
                    if name in seen:
                        return True
            return False

    def source_templates(self) -> list[str]:
        return ["all y.G(x,y) & all x.F(x)"]

# =============================================================================
# 测试代码
# =============================================================================
if __name__ == "__main__":
    mr = MRE15()
    test_case=TestCase(
            premises_text=['(all x. A(y)) & (exists y. B)'],
            conclusion_text='ok',
            premises_logic=['(all x. A(y)) & (exists y. B)'],
            conclusion_logic='ok',
            metadata=['']
        )
    follow_TC=mr.transform(test_case)
    print(follow_TC)
