import json
import os
import re
from nltk.sem.logic import LogicParser

class LogicNLIConverter:
    def __init__(self):
        self.logic_parser = LogicParser()
        self.stats = {
            "total_cases": 0,
            "success_count": 0,
            "failure_count": 0
        }

    def _normalize(self, formula: str) -> str:
        # Standardize symbols
        formula = formula.replace("↔", "<->").replace("⟷", "<->")
        formula = formula.replace("→", "->")
        formula = formula.replace("¬", "-")
        formula = formula.replace("∨", "|")
        formula = formula.replace("∧", "&")
        formula = formula.replace("⊕", "⊕") # Ensure we catch it if we need to expand
        formula = formula.replace("∀", "all ")
        formula = formula.replace("∃", "exists ")
        
        # Add space after quantifiers if missing (e.g., "all xP(x)")
        formula = re.sub(r'(all|exists)\s+(\w+)(?!\.)', r'\1 \2.', formula)
        
        # Expand XOR if present
        if "⊕" in formula:
            formula = self._expand_xor(formula)

        return formula

    def _expand_xor(self, formula: str) -> str:
        # Recursively expand 'A ⊕ B' to '((-A & B) | (A & -B))'.
        xor_index = formula.find("⊕")
        if xor_index == -1:
            return formula

        length = len(formula)
        
        # --- Left Scan for A ---
        left_balance = 0
        start_index = 0
        connectors = ["&", "|", "->", "<->", ".", "∧", "∨", "→", "↔", "⟷", "⊕"]
        
        for i in range(xor_index - 1, -1, -1):
            char = formula[i]
            if char == ')':
                left_balance += 1
            elif char == '(':
                left_balance -= 1
                if left_balance < 0:
                    start_index = i + 1
                    break
            
            if left_balance == 0:
                if i >= 2 and formula[i-2:i+1] in connectors:
                    start_index = i + 1
                    break
                if i >= 1 and formula[i-1:i+1] in connectors:
                    start_index = i + 1
                    break
                if char in connectors:
                    start_index = i + 1
                    break
            if i == 0:
                start_index = 0
        
        operand_a = formula[start_index:xor_index].strip()
        
        # --- Right Scan for B ---
        right_balance = 0
        end_index = length
        
        for i in range(xor_index + 1, length):
            char = formula[i]
            if char == '(':
                right_balance += 1
            elif char == ')':
                right_balance -= 1
                if right_balance < 0:
                    end_index = i
                    break
            
            if right_balance == 0:
                if i + 3 <= length and formula[i:i+3] in connectors:
                    end_index = i
                    break
                if i + 2 <= length and formula[i:i+2] in connectors:
                    end_index = i
                    break
                if char in connectors:
                    end_index = i
                    break
                    
        operand_b = formula[xor_index + 1:end_index].strip()
        
        expanded = f"((-({operand_a}) & ({operand_b})) | (({operand_a}) & -({operand_b})))"
        
        # Replace the first occurrence of A ⊕ B with the expanded version
        prefix = formula[:start_index]
        suffix = formula[end_index:]
        new_formula = prefix + expanded + suffix
        
        # Recursively expand remaining XORs
        return self._expand_xor(new_formula)

    def _format_predicate(self, pred_name):
        # Capitalize first letter to match standard FOL convention (e.g. Blue, Serious)
        # Also replace hyphens with underscores for parser compatibility
        return pred_name.capitalize().replace("-", "_")

    def _construct_atom(self, entity, pred, pol, variable_override=None):
        # Construct Predicate(Entity) or -Predicate(Entity)
        # variable_override: if provided, use this instead of entity (for quantifiers)
        
        pred_clean = self._format_predicate(pred)
        subject = variable_override if variable_override else entity
        
        atom = f"{pred_clean}({subject})"
        if pol == "-":
            return f"-{atom}"
        return atom

    def _process_condition_group(self, group_info, var_name="x", force_var=False):
        # group_info: {"fact": [[subj, pred, pol], ...], "conj": "and"/"or"}
        # force_var: if True, treat all "all"/"exist" subjects as var_name
        
        facts = group_info.get("fact", [])
        conj = group_info.get("conj", "none")
        
        operator = "&" if conj == "and" else "|"
        # If "none", implies single fact (or implicit AND/OR? logic.json usually has single fact for 'none')
        if conj == "none":
            operator = "&" # Default fallback, though usually list has 1 item
            
        formulas = []
        quantifiers_found = set()
        
        for f in facts:
            subj, pred, pol = f[0], f[1], f[2]
            
            if subj in ["all", "exist"]:
                quantifiers_found.add(subj)
                atom = self._construct_atom(subj, pred, pol, variable_override=var_name)
            else:
                atom = self._construct_atom(subj, pred, pol)
            formulas.append(atom)
            
        if not formulas:
            return "", quantifiers_found
            
        if len(formulas) > 1:
            # Join with operator
            # (A & B)
            combined = f"({f' {operator} '.join(formulas)})"
        else:
            combined = formulas[0]
            
        return combined, quantifiers_found

    def _construct_rule(self, rule_info):
        # rule_info: {"p": ..., "q": ..., "type": "imp"}
        p_info = rule_info.get("p", {})
        q_info = rule_info.get("q", {})
        
        # Analyze p to determine scope
        # We peek at p's facts to see if "all" is present
        p_facts = p_info.get("fact", [])
        p_has_all = any(f[0] == "all" for f in p_facts)
        p_has_exist = any(f[0] == "exist" for f in p_facts)
        
        # Determine operator based on type
        rule_type = rule_info.get("type", "imp")
        arrow = "<->" if rule_type == "equ" else "->"
                
        if p_has_all:
            # --- 修复 NameError：先获取 Q 的量词状态 ---
            q_facts = q_info.get("fact", [])
            q_has_all = any(f[0] == "all" for f in q_facts)
            q_has_exist = any(f[0] == "exist" for f in q_facts)
            
            # 1. 判断结论 Q 是否是常量
            # - 如果 Q 是常量 (Abbott)，则 P 的量词是"集合级"的 -> Split Scope
            # - 如果 Q 也是泛化的 (all/exist)，则 P 的量词是"个体级"的 -> Shared Scope
            q_is_constant = not (q_has_all or q_has_exist)

            if q_is_constant:
                # --- 模式 A: 拆分作用域 (Split Scope) ---
                # Case: "If everyone is P, then [Constant] is Q"
                # Logic: (all x. P) -> Constant
                
                p_str, _ = self._process_condition_group(p_info, var_name="x", force_var=True)
                p_full = f"(all x. {p_str})"
                
                # Q 是常量
                q_str, _ = self._process_condition_group(q_info)
                q_full = q_str
                
                formula = f"{p_full} {arrow} {q_full}"
                
            else:
                # --- 模式 B: 共享作用域 (Shared Scope) ---
                # Case: "All Ps are Qs"
                # Logic: all x. (P(x) -> Q(x))
                
                p_str, _ = self._process_condition_group(p_info, var_name="x", force_var=True)
                q_str, _ = self._process_condition_group(q_info, var_name="x", force_var=True)
                
                formula = f"all x. ({p_str} {arrow} {q_str})"
            
        elif p_has_exist:
            # Local Scope 'x' in P
            p_str, _ = self._process_condition_group(p_info, var_name="x", force_var=True)
            # Wrap P
            p_full = f"(exists x. {p_str})"
            
            q_facts = q_info.get("fact", [])
            q_has_quant = any(f[0] in ["all", "exist"] for f in q_facts)
            
            if q_has_quant:
                q_str, q_quants = self._process_condition_group(q_info, var_name="y", force_var=True)
                # Heuristic: if Q has 'all', wrap all y. If 'exist', wrap exists y.
                # Assuming simple single quantifier in Q
                if "all" in q_quants:
                    q_full = f"(all y. {q_str})"
                else:
                    q_full = f"(exists y. {q_str})"
            else:
                q_str, _ = self._process_condition_group(q_info)
                q_full = q_str
                
            formula = f"{p_full} {arrow} {q_full}"
            
        else:
            # No quantifiers in P (Propositional / Constants)
            p_str, _ = self._process_condition_group(p_info)
            
            # Check Q
            q_facts = q_info.get("fact", [])
            q_has_quant = any(f[0] in ["all", "exist"] for f in q_facts)
            
            if q_has_quant:
                q_str, q_quants = self._process_condition_group(q_info, var_name="y", force_var=True)
                if "all" in q_quants:
                    q_full = f"(all y. {q_str})"
                else:
                    q_full = f"(exists y. {q_str})"
            else:
                q_str, _ = self._process_condition_group(q_info)
                q_full = q_str
            
            formula = f"{p_str} {arrow} {q_full}"
            
        return formula

    def _parse_statement(self, text, known_entities, known_preds):
        # Text: "Entity is [not] Predicate."
        # Clean text
        text = text.strip().rstrip('.')
        
        # Regex for standard pattern
        match = re.match(r"^(.+) is (not )?(.+)$", text)
        if match:
            entity = match.group(1).strip()
            is_neg = match.group(2) is not None
            pred_phrase = match.group(3).strip()
            
            final_pred = None
            if pred_phrase in known_preds:
                final_pred = pred_phrase
            elif pred_phrase.replace("-", "").isalpha() and " " not in pred_phrase:
                # Heuristic: LogicNLI predicates are single words or hyphenated words. 
                # If regex matched "X is Y", assume Y is predicate if it's a simple word.
                final_pred = pred_phrase
            else:
                # Try splitting? "a student"? No, LogicNLI is simple adj.
                pass
            
            if final_pred:
                atom = self._construct_atom(entity, final_pred, "-" if is_neg else "+")
                return atom
                
        # Fallback if regex fails or complex sentence
        return f"ParseError({text})"

    def validate_formula(self, formula):
        try:
            self.logic_parser.parse(formula)
            return True, None
        except Exception as e:
            return False, str(e)

    def convert_files(self, lang_path, logic_path, output_path, failure_path, split="test"):
        print(f"Writing output to {output_path}")
        
        if not os.path.exists(lang_path) or not os.path.exists(logic_path):
            print(f"Error: Input files not found:\n  {lang_path}\n  {logic_path}")
            return

        with open(output_path, 'w', encoding='utf-8') as out_f, \
             open(failure_path, 'w', encoding='utf-8') as fail_f:
            
            print(f"Processing data from {lang_path}...")
            self.process_split(lang_path, logic_path, out_f, fail_f, split=split)
        
        print("Conversion Stats:", self.stats)

    def process_split(self, lang_path, logic_path, out_f, fail_f, split="test"):
        # Load JSONL data
        lang_data = {}
        with open(lang_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    lang_data[item['id']] = item
                    
        logic_data = {}
        with open(logic_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    logic_data[item['id']] = item
            
        # Sort IDs to maintain order
        sorted_ids = sorted(lang_data.keys(), key=lambda k: int(k) if k.isdigit() else k)
        
        for ex_id in sorted_ids:
            ex_lang = lang_data[ex_id]
            ex_logic = logic_data.get(ex_id)
            if not ex_logic:
                continue
            
            # --- Facts ---
            facts_logic_map = ex_logic.get("facts", {})
            facts_text_list = ex_lang.get("facts", [])
            
            converted_facts = []
            all_entities = set()
            all_preds = set()
            
            # Pre-scan facts for entity/predicate discovery
            for fid, f_info in facts_logic_map.items():
                 all_entities.add(f_info[0])
                 all_preds.add(f_info[1])

            sorted_fact_ids = sorted(facts_logic_map.keys(), key=lambda k: int(k) if k.isdigit() else k)
            for fid in sorted_fact_ids:
                f_info = facts_logic_map[fid]
                entity, pred, pol = f_info[0], f_info[1], f_info[2]
                formula = self._construct_atom(entity, pred, pol)
                converted_facts.append(formula)
            
            # --- Rules ---
            rules_logic_map = ex_logic.get("rules", {})
            rules_text_list = ex_lang.get("rules", [])
            
            converted_rules = []
            sorted_rule_ids = sorted(rules_logic_map.keys(), key=lambda k: int(k) if k.isdigit() else k)
            for rid in sorted_rule_ids:
                r_info = rules_logic_map[rid]
                rule_formula = self._construct_rule(r_info)
                converted_rules.append(rule_formula)
            
            premises_logic = converted_facts + converted_rules
            premises_text = facts_text_list + rules_text_list
            
            # Normalize all premises
            final_premises_logic = [self._normalize(p) for p in premises_logic]
            
            # --- Statements ---
            statements = ex_lang.get("statements", [])
            labels = ex_lang.get("labels", [])
            
            for i, (stmt_text, label) in enumerate(zip(statements, labels)):
                if label == "self_contradiction":
                    continue
                    
                self.stats["total_cases"] += 1
                stmt_logic = self._parse_statement(stmt_text, all_entities, all_preds)
                stmt_logic = self._normalize(stmt_logic)
                
                # Validation
                failures = []
                
                # Check premises
                for idx, p in enumerate(final_premises_logic):
                    is_valid, err = self.validate_formula(p)
                    if not is_valid:
                        failures.append({
                            "type": "premise",
                            "index": idx,
                            "formula": p,
                            "error": err
                        })
                
                # Check conclusion
                is_valid_conc, err_conc = self.validate_formula(stmt_logic)
                if not is_valid_conc:
                    failures.append({
                        "type": "conclusion",
                        "formula": stmt_logic,
                        "error": err_conc
                    })
                
                if failures:
                    self.stats["failure_count"] += 1
                    fail_entry = {
                        "example_id": f"{split}_{ex_id}_{i}",
                        "failures": failures
                    }
                    fail_f.write(json.dumps(fail_entry) + "\n")
                    continue
                
                self.stats["success_count"] += 1
                
                label_map = {
                    "entailment": "True",
                    "contradiction": "False",
                    "self_contradiction": "False",
                    "neutral": "Uncertain"
                }
                final_label = label_map.get(label, "Uncertain")
                
                out_obj = {
                    "premises_logic": final_premises_logic,
                    "conclusion_logic": stmt_logic,
                    "premises_text": premises_text,
                    "conclusion_text": stmt_text,
                    "metadata": {
                        "label": final_label,
                        "num_premises": len(final_premises_logic),
                        "data_source": "LogicNLI",
                        "example_id": f"{split}_{ex_id}_{i}"
                    }
                }
                out_f.write(json.dumps(out_obj) + "\n")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_case_dir = os.path.join(os.path.dirname(base_dir), "test_case_from_clean_version")
    os.makedirs(test_case_dir, exist_ok=True)
    
    # Output files (Unified)
    output_path = os.path.join(test_case_dir, "logicnli_source_test_case_dirty.jsonl")
    failure_path = os.path.join(test_case_dir, "logicnli_parse_failures_dirty.jsonl")
    
    datasets = ["dev", "test", "train"]
    
    converter = LogicNLIConverter()
    
    print(f"Writing unified output to:\n  {output_path}\n  {failure_path}")
    
    with open(output_path, 'w', encoding='utf-8') as out_f, \
         open(failure_path, 'w', encoding='utf-8') as fail_f:
        
        for split in datasets:
            # Input files
            lang_path = os.path.join(base_dir, f"{split}_language_clean.jsonl")
            logic_path = os.path.join(base_dir, f"{split}_logic_clean.jsonl")
            
            if not os.path.exists(lang_path) or not os.path.exists(logic_path):
                print(f"Skipping {split}: Input files not found.")
                continue

            print(f"\nProcessing {split} set...")
            converter.process_split(lang_path, logic_path, out_f, fail_f, split=split)
            
    print("\nFinal Conversion Stats:", converter.stats)
