import json
import os
import re
from nltk.sem.logic import LogicParser

class FormulaNormalizer:
    def __init__(self):
        pass

    def _expand_xor(self, formula: str) -> str:
        """
        Recursively expand 'A ⊕ B' to '((-A & B) | (A & -B))'.
        Handles nested parentheses and quantifiers using index-based scanning.
        """
        xor_index = formula.find("⊕")
        if xor_index == -1:
            return formula

        length = len(formula)
        
        # --- Left Scan for A ---
        left_balance = 0
        start_index = 0
        
        # Connectors that mark the boundary of an operand
        # Note: Unary operators (-, ¬) bind to the operand, so they don't stop the scan.
        connectors = ["&", "|", "->", "<->", ".", "∧", "∨", "→", "↔", "⟷", "⊕"]
        
        for i in range(xor_index - 1, -1, -1):
            char = formula[i]
            
            # Handle parenthesis balance
            if char == ')':
                left_balance += 1
            elif char == '(':
                left_balance -= 1
                if left_balance < 0:
                    # Found an unbalanced opening bracket, which means we hit the start of the enclosing group
                    start_index = i + 1
                    break
            
            # Check for connectors when balance is zero
            if left_balance == 0:
                # Check for multi-character connectors like ->, <->
                # We need to look ahead (which is 'back' in the string) or just check substring
                # Easier to check substring ending at i
                # Note: connectors in list are logic operators.
                
                # Check 3-char connectors
                if i >= 2 and formula[i-2:i+1] in connectors:
                    start_index = i + 1
                    break
                # Check 2-char connectors
                if i >= 1 and formula[i-1:i+1] in connectors:
                    start_index = i + 1
                    break
                # Check 1-char connectors
                if char in connectors:
                    start_index = i + 1
                    break
                
                # Special case: quantifier space boundary? 
                # "all x. P(x) ⊕ Q(x)" -> dot is caught above.
                
            if i == 0:
                start_index = 0
        
        # Extract A
        operand_a = formula[start_index:xor_index].strip()
        
        # --- Right Scan for B ---
        right_balance = 0
        end_index = length
        
        for i in range(xor_index + 1, length):
            char = formula[i]
            
            # Handle parenthesis balance
            if char == '(':
                right_balance += 1
            elif char == ')':
                right_balance -= 1
                if right_balance < 0:
                    # Found an unbalanced closing bracket
                    end_index = i
                    break
            
            # Check for connectors when balance is zero
            if right_balance == 0:
                # Check substrings starting at i
                # Check 3-char connectors
                if i + 3 <= length and formula[i:i+3] in connectors:
                    end_index = i
                    break
                # Check 2-char connectors
                if i + 2 <= length and formula[i:i+2] in connectors:
                    end_index = i
                    break
                # Check 1-char connectors
                if char in connectors:
                    end_index = i
                    break
                    
        # Extract B
        operand_b = formula[xor_index + 1:end_index].strip()
        
        # Construct new formula
        # A ⊕ B -> ((-A & B) | (A & -B))
        # Note: We wrap operands in parens if they are complex? 
        # The user example: Human(x) ⊕ ... -> -Human(x). 
        # Safest to wrap A and B in parens if they are not atomic, but let's stick to the user's requested format logic.
        # User output example: ((-Human(x) & (Robot(x) & AI(x))) | (Human(x) & -(Robot(x) & AI(x))))
        # It seems A and B are used directly.
        
        expanded = f"((-({operand_a}) & ({operand_b})) | (({operand_a}) & -({operand_b})))"
        
        new_formula = formula[:start_index] + expanded + formula[end_index:]
        
        # Recursive call to handle other XORs
        return self._expand_xor(new_formula)

    def _normalize(self, formula: str) -> str:
        """
        Normalize logic formula string.
        """
        # 0. Expand XOR first (recursive)
        result = self._expand_xor(formula)

        # 1. Replace Unicode symbols
        result = result.replace("↔", "<->")
        result = result.replace("⟷", "<->")
        result = result.replace("→", "->")
        result = result.replace("¬", "-")
        result = result.replace("∨", "|")
        result = result.replace("∧", "&")

        # 2. Handle quantifiers - ensure they have space
        result = result.replace("∀", "all ")
        result = result.replace("∃", "exists ")

        # 3. Add dot after quantifier variable if missing
        # Match pattern: all x or exists x (where x is variable)
        def ensure_dot(match):
            quantifier = match.group(1)  # all or exists
            variable = match.group(2)    # variable name
            return f"{quantifier} {variable}."

        # Find all quantifiers followed by variable without dot
        result = re.sub(r"\b(all|exists)\s+([a-zA-Z])(?![\.])", ensure_dot, result)

        return result

    def normalize_specific_fields(self, data: dict, target_fields=None) -> dict:
        """
        Only process formulas in specific fields
        """
        if target_fields is None:
            target_fields = ["premises_logic", "conclusion_logic"]
        
        # Symbols that trigger normalization
        # Added ⊕ (XOR) to the list
        trigger_symbols = ["↔", "→", "¬", "∨", "∧", "∀", "∃", "⟷", "⊕"]

        for field in target_fields:
            if field in data:
                val = data[field]
                if isinstance(val, str):
                    if any(symbol in val for symbol in trigger_symbols):
                        data[field] = self._normalize(val)
                elif isinstance(val, list):
                    new_list = []
                    for item in val:
                        if isinstance(item, str):
                            if any(symbol in item for symbol in trigger_symbols):
                                new_list.append(self._normalize(item))
                            else:
                                new_list.append(item)
                        else:
                            new_list.append(item)
                    data[field] = new_list
        return data


def process_proverqa_files(input_dir=None, output_path=None, failure_path=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if input_dir is None:
        input_dir = base_dir
    if output_path is None:
        output_path = os.path.join(base_dir, "proverqa_source_test_case.jsonl")
    if failure_path is None:
        failure_path = os.path.join(base_dir, "proverqa_parse_failures.jsonl")
    input_files = [
        "easy.json",
        "medium.json",
        "hard.json"
    ]
    input_paths = [os.path.join(input_dir, name) for name in input_files]

    normalizer = FormulaNormalizer()
    parser = LogicParser()
    
    failed_examples_info = []
    valid_count = 0
    total_items = 0
    load_failed_count = 0

    label_map = {
        "A": "True",
        "B": "False",
        "C": "Uncertain"
    }

    print(f"Processing ProverQA files to {output_path}...")

    with open(output_path, "w", encoding="utf-8") as f_out:
        for process_path in input_paths:
            filename = os.path.basename(process_path)
            if not os.path.exists(process_path):
                print(f"File not found: {process_path}")
                continue
            
            print(f"Reading {process_path}...")
            try:
                with open(process_path, "r", encoding="utf-8") as f_in:
                    raw_data = json.load(f_in)
                    
                for item in raw_data:
                    total_items += 1
                    try:
                        # Extract basic info
                        original_id = item.get("id")
                        answer_code = item.get("answer")
                        label = label_map.get(answer_code, "Unknown")
                        
                        # Extract premises and conclusion
                        nl2fol = item.get("nl2fol", {})
                        premises_text = list(nl2fol.keys())
                        premises_logic = list(nl2fol.values())
                        
                        conclusion_logic = item.get("conclusion_fol", "")
                        
                        # Extract conclusion text from question
                        question = item.get("question", "")
                        conclusion_text = question
                        if "uncertain? " in question:
                            conclusion_text = question.split("uncertain? ")[-1].strip()
                        elif "false? " in question: # Fallback if pattern varies
                             conclusion_text = question.split("false? ")[-1].strip()
                        elif "true? " in question: # Fallback if pattern varies
                             conclusion_text = question.split("true? ")[-1].strip()

                        # Preprocessing: Replace '-' and '.' with '_' in LOGIC fields only
                        # As per user instruction in previous turn: "replace - and . with _ in logic fields"
                        # We apply this before normalization.
                        
                        # Clean premises logic
                        cleaned_premises_logic = []
                        original_premises_logic = [] # Store for logging
                        for p in premises_logic:
                            original_premises_logic.append(p)
                            cleaned_p = p.replace("-", "_").replace(".", "_")
                            cleaned_premises_logic.append(cleaned_p)
                        
                        # Clean conclusion logic
                        original_conclusion_logic = conclusion_logic
                        cleaned_conclusion_logic = conclusion_logic.replace("-", "_").replace(".", "_")

                        # Construct intermediate data object for normalization
                        data_to_normalize = {
                            "premises_logic": cleaned_premises_logic,
                            "conclusion_logic": cleaned_conclusion_logic
                        }

                        # Normalize formulas
                        data_normalized = normalizer.normalize_specific_fields(data_to_normalize)
                        final_premises_logic = data_normalized["premises_logic"]
                        final_conclusion_logic = data_normalized["conclusion_logic"]
                        
                        # Validate formulas
                        example_success = True
                        current_failures = []
                        
                        # Validate Premises
                        for i, formula in enumerate(final_premises_logic):
                            try:
                                # Check for unicode remnants
                                if any(s in formula for s in ["∀", "∃", "→", "∧", "∨", "¬", "↔"]):
                                    raise ValueError("Contains Unicode symbols")
                                parser.parse(formula)
                            except Exception as e:
                                example_success = False
                                orig_f = original_premises_logic[i] if i < len(original_premises_logic) else "N/A"
                                current_failures.append({
                                    'type': 'premises',
                                    'index': i,
                                    'formula': formula,
                                    'formula_original': orig_f,
                                    'error': str(e).strip(" \n^")
                                })
                        
                        # Validate Conclusion
                        try:
                            if any(s in final_conclusion_logic for s in ["∀", "∃", "→", "∧", "∨", "¬", "↔"]):
                                raise ValueError("Contains Unicode symbols")
                            parser.parse(final_conclusion_logic)
                        except Exception as e:
                            example_success = False
                            current_failures.append({
                                'type': 'conclusion',
                                'formula': final_conclusion_logic,
                                'formula_original': original_conclusion_logic,
                                'error': str(e).strip(" \n^")
                            })

                        if example_success:
                            # Construct Output Object
                            output_obj = {
                                "premises_logic": final_premises_logic,
                                "conclusion_logic": final_conclusion_logic,
                                "premises_text": premises_text,
                                "conclusion_text": conclusion_text,
                                "metadata": {
                                    "label": label,
                                    "num_premises": len(final_premises_logic),
                                    "data_source": "ProverQA",
                                    "example_id": original_id,
                                    "original_file": filename
                                }
                            }
                            f_out.write(json.dumps(output_obj, ensure_ascii=False) + "\n")
                            valid_count += 1
                        else:
                            failed_examples_info.append({
                                'example_id': original_id,
                                'original_file': filename,
                                'failures': current_failures[0] # Log first failure
                            })
                            
                    except Exception as e:
                        print(f"Error processing item {item.get('id', 'unknown')} in {filename}: {e}")
                        load_failed_count += 1
            except Exception as e:
                print(f"Error reading file {process_path}: {e}")
                load_failed_count += 1

    # Save failures
    with open(failure_path, "w", encoding="utf-8") as f:
        for failure in failed_examples_info:
            f.write(json.dumps(failure, ensure_ascii=False) + "\n")

    print(f"\nProcessing Complete.")
    print(f"Total test cases found: {total_items}")
    print(f"Converted successfully: {valid_count}")
    print(f"Parse/Validation failed: {len(failed_examples_info)}")
    print(f"Load/Process failed: {load_failed_count}")
    print(f"Output file: {output_path}")
    print(f"Failure log: {failure_path}")

if __name__ == "__main__":
    process_proverqa_files()
