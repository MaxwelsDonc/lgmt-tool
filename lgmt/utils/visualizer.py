from nltk.sem.logic import (
    Expression, 
    ApplicationExpression, 
    AbstractVariableExpression, 
    QuantifiedExpression, 
    ImpExpression, 
    IffExpression, 
    NegatedExpression,  
    AndExpression,      
    OrExpression,
    VariableExpression
)

def print_ast(expr: Expression, prefix="", is_last=True):
    """
    在控制台打印漂亮的 ASCII 树结构
    """
    # 1. 确定当前节点的显示的符号
    # 获取类名，去掉 "Expression" 后缀
    node_name = expr.__class__.__name__.replace("Expression", "")
    symbol = ""
    
    # 根据类型获取符号，方便阅读
    if isinstance(expr, AbstractVariableExpression): # 变量 x
        symbol = str(expr)
    elif isinstance(expr, ApplicationExpression): # 谓词 Man(x)
        symbol = str(expr)
    elif isinstance(expr, ImpExpression): symbol = "→"
    elif isinstance(expr, IffExpression): symbol = "↔"
    elif isinstance(expr, AndExpression): symbol = "∧"
    elif isinstance(expr, OrExpression):  symbol = "∨"
    elif isinstance(expr, NegatedExpression): symbol = "¬"
    elif isinstance(expr, QuantifiedExpression): 
        # 需要检查是否是 AllExpression 还是 ExistsExpression
        if expr.__class__.__name__ == 'AllExpression':
            symbol = f"∀{expr.variable}"
        elif expr.__class__.__name__ == 'ExistsExpression':
            symbol = f"∃{expr.variable}"
        else:
            symbol = f"Q{expr.variable}"
    
    display_str = f"{node_name} [{symbol}]" if symbol else node_name

    # 2. 打印当前节点
    connector = "└── " if is_last else "├── "
    print(prefix + connector + display_str)

    # 3. 准备子节点列表
    children = []
    if isinstance(expr, (AndExpression, OrExpression, ImpExpression, IffExpression)): 
        # 这些都是 BinaryExpression 的子类
        children = [expr.first, expr.second]
    elif isinstance(expr, NegatedExpression): 
        children = [expr.term]
    elif isinstance(expr, QuantifiedExpression):
        children = [expr.term]
    elif isinstance(expr, ApplicationExpression):
        # 展开谓词的参数
        children = list(expr.args)

    # 4. 递归打印子节点
    prefix += "    " if is_last else "│   "
    for i, child in enumerate(children):
        print_ast(child, prefix, i == len(children) - 1)

# === 测试代码 ===
if __name__ == "__main__":
    from nltk.sem.logic import LogicParser
    p = LogicParser()
    
    print("--- 正在测试 AST 可视化 ---")
    # 测试一个包含否定、量词、或门的复杂公式
    # NLTK 输入格式: -Man(x) 表示 Not Man(x)
    formulas = [
        "(exists x.-Quaint(x) -> (Dynamic(Con6) & -Warm_hearted(Con1)))",
    ]
    
    for formula in formulas:
        print(f"\n=== Input Formula: {formula} ===")
        try:
            expr = p.parse(formula)
            print_ast(expr)
        except Exception as e:
            print(f"Error: {e}")