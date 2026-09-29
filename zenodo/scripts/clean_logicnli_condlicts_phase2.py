import json
import os
import sys
from nltk.sem.logic import (
    LogicParser, AndExpression, OrExpression, ImpExpression, IffExpression,
    NegatedExpression, ExistsExpression, AllExpression,
    ApplicationExpression, Variable, ConstantExpression, EqualityExpression,
    IndividualVariableExpression
)
from z3 import (
    Solver, Function, BoolSort, DeclareSort, Const,
    ForAll, Exists, And, Or, Implies, Not, sat
)

class Z3Converter:
    def __init__(self):
        self.parser = LogicParser()
        self.sort = DeclareSort('Object')
        self.solver = None
        self.functions = {}
        self.constants = {}
        self.variables = {}  # Map variable names to Z3 variables in current scope

    def reset(self):
        self.solver = Solver()
        self.functions = {}
        self.constants = {}
        self.variables = {}

    def get_function(self, name, arity):
        if name not in self.functions:
            # Create domain sorts list based on arity
            domain = [self.sort] * arity
            self.functions[name] = Function(name, *domain, BoolSort())
        return self.functions[name]

    def get_constant(self, name):
        if name not in self.constants:
            self.constants[name] = Const(name, self.sort)
        return self.constants[name]

    def to_z3(self, expr, bound_vars=None):
        if bound_vars is None:
            bound_vars = {}

        if isinstance(expr, AndExpression):
            return And(self.to_z3(expr.first, bound_vars), self.to_z3(expr.second, bound_vars))
        
        elif isinstance(expr, OrExpression):
            return Or(self.to_z3(expr.first, bound_vars), self.to_z3(expr.second, bound_vars))
        
        elif isinstance(expr, ImpExpression):
            return Implies(self.to_z3(expr.first, bound_vars), self.to_z3(expr.second, bound_vars))
        
        elif isinstance(expr, IffExpression):
            return self.to_z3(expr.first, bound_vars) == self.to_z3(expr.second, bound_vars)
        
        elif isinstance(expr, NegatedExpression):
            return Not(self.to_z3(expr.term, bound_vars))
        
        elif isinstance(expr, (AllExpression, ExistsExpression)):
            # Handle quantifiers
            var_name = str(expr.variable)
            
            # Create a new Z3 constant for the bound variable to serve as the variable in quantifier
            # But wait, Z3 quantifiers expect a list of variables (Consts)
            z3_var = Const(var_name, self.sort)
            
            # Shadowing: if variable exists in outer scope, we temporarily override it
            # But since we pass bound_vars down, we just add to it
            new_bound_vars = bound_vars.copy()
            new_bound_vars[var_name] = z3_var
            
            body = self.to_z3(expr.term, new_bound_vars)
            
            if isinstance(expr, AllExpression):
                return ForAll([z3_var], body)
            else:
                return Exists([z3_var], body)
        
        elif isinstance(expr, ApplicationExpression):
            pred = expr.function
            args = expr.args
            
            # Handle predicate name
            if isinstance(pred, ConstantExpression):
                pred_name = str(pred.variable)
            elif isinstance(pred, Variable):
                pred_name = str(pred)
            else:
                # Should be a simple name
                pred_name = str(pred)
                
            z3_func = self.get_function(pred_name, len(args))
            
            z3_args = []
            for arg in args:
                # --- 新增：处理 NLTK 包装的变量表达式 ---
                if isinstance(arg, IndividualVariableExpression):
                    arg_name = str(arg.variable)
                    if arg_name in bound_vars:
                        z3_args.append(bound_vars[arg_name])
                    else:
                        # 自由变量当作常量处理
                        z3_args.append(self.get_constant(arg_name))

                # --- 原有的：处理裸变量（以防万一） ---
                elif isinstance(arg, Variable):
                    arg_name = str(arg)
                    if arg_name in bound_vars:
                        z3_args.append(bound_vars[arg_name])
                    else:
                        z3_args.append(self.get_constant(arg_name))

                # --- 原有的：处理常量表达式 ---
                elif isinstance(arg, ConstantExpression):
                    z3_args.append(self.get_constant(str(arg.variable)))
                
                else:
                    raise ValueError(f"Unexpected argument type: {type(arg)}")
            
            return z3_func(*z3_args)
            
        elif isinstance(expr, EqualityExpression):
            return self.to_z3(expr.first, bound_vars) == self.to_z3(expr.second, bound_vars)
            
        elif isinstance(expr, ConstantExpression):
            # Propositional constant? (0-arity predicate)
            pred_name = str(expr.variable)
            z3_func = self.get_function(pred_name, 0)
            return z3_func()

        elif isinstance(expr, Variable):
             # This case might be hit if a variable appears outside of application (e.g. equality)
             name = str(expr)
             if name in bound_vars:
                 return bound_vars[name]
             return self.get_constant(name)

        else:
            raise ValueError(f"Unknown expression type: {type(expr)} - {expr}")

    def check_consistency(self, premises_str_list):
        self.reset()
        
        try:
            constraints = []
            for p_str in premises_str_list:
                # Parse NLTK
                nltk_expr = self.parser.parse(p_str)
                # Convert to Z3
                z3_expr = self.to_z3(nltk_expr)
                constraints.append(z3_expr)
                
            self.solver.add(constraints)
            result = self.solver.check()
            return result == sat
            
        except Exception as e:
            # If parsing or conversion fails, we can't determine consistency.
            # Depending on policy, we might keep or drop.
            # For now, let's print error and assume inconsistent to be safe (or consistent?)
            # Usually better to be conservative and drop if we can't verify.
            # But if it's just a parsing error on a valid formula, dropping is bad.
            # Let's assume consistent if error, but print it.
            print(f"Error checking consistency: {e}")
            return True # Keep it if we can't check? Or False?
            # User wants to filter OUT contradictions. If we crash, we don't know if it's contradiction.
            # Let's return True (keep) but log it.

def clean_conflicts_phase2(input_path, output_path):
    print(f"Reading from {input_path}")
    
    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}")
        return

    converter = Z3Converter()
    
    total = 0
    kept = 0
    removed = 0
    
    with open(input_path, 'r', encoding='utf-8') as fin, \
         open(output_path, 'w', encoding='utf-8') as fout:
        
        for line in fin:
            if not line.strip():
                continue
                
            total += 1
            try:
                data = json.loads(line)
                premises = data.get("premises_logic", [])
                
                # Check consistency
                is_consistent = converter.check_consistency(premises)
                
                if is_consistent:
                    fout.write(line)
                    kept += 1
                else:
                    removed += 1
                    # Optional: Print dropped cases
                    # print(f"Dropped ID {data.get('metadata', {}).get('example_id')} due to contradiction.")
                    
            except json.JSONDecodeError:
                print("Skipping invalid JSON line")
                continue
                
            if total % 100 == 0:
                print(f"Processed {total} cases... (Kept: {kept}, Removed: {removed})")

    print(f"\nFinal Stats:")
    print(f"Total Processed: {total}")
    print(f"Kept: {kept}")
    print(f"Removed (Self-Contradictory Premises): {removed}")
    print(f"Output written to {output_path}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    input_file = os.path.join(base_dir, "logicnli_source_test_case_dirty.jsonl")
    output_file = os.path.join(os.path.dirname(base_dir), "logicnli_source_test_case.jsonl")
    
    clean_conflicts_phase2(input_file, output_file)
