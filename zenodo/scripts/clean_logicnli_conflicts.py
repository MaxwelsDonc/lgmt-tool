'''
Clean the LogicNLI files to filter out the conflicts premises.
'''
import json
import re
import os

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_proof(proof_str):
    if not proof_str or proof_str == "none":
        return set(), set()
    
    # Extract facts: "fact <digits>"
    facts = set(re.findall(r'fact\s+(\d+)', proof_str))
    # Extract rules: "-->(\d+)"
    # Note: LogicNLI proofs typically look like "[[fact 0-->1]-->2]"
    # So we look for numbers preceded by "-->"
    # Also handle cases where there might be spaces? usually not in this dataset.
    rules = set(re.findall(r'-->(\d+)', proof_str))
    
    return facts, rules

def update_proof(proof_str, fact_map, rule_map):
    if not proof_str or proof_str == "none":
        return "none"
    
    # Replace facts: "fact X" -> "fact Y"
    # We use a callback to ensure we match the whole number
    def replace_fact(match):
        old_id = match.group(1)
        if old_id in fact_map:
            return f"fact {fact_map[old_id]}"
        # If not in map, it means it was deleted! This shouldn't happen for kept statements.
        # But if it does, we have a problem. 
        # For now assume logic is correct and it won't happen.
        return match.group(0)
    
    new_proof = re.sub(r'fact\s+(\d+)', replace_fact, proof_str)
    
    # Replace rules: "-->X" -> "-->Y"
    def replace_rule(match):
        old_id = match.group(1)
        if old_id in rule_map:
            return f"-->{rule_map[old_id]}"
        return match.group(0)
        
    new_proof = re.sub(r'-->(\d+)', replace_rule, new_proof)
    
    return new_proof

def clean_dataset(lang_path, logic_path, out_lang_path, out_logic_path):
    print(f"Loading {lang_path} and {logic_path}...")
    lang_data = load_json(lang_path)
    logic_data = load_json(logic_path)
    
    # We will output list of objects for jsonl
    clean_lang_list = []
    clean_logic_list = []
    
    # Sort IDs to be deterministic
    example_ids = sorted(lang_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
    
    total_sc_removed = 0
    total_facts_removed = 0
    total_rules_removed = 0
    
    for ex_id in example_ids:
        ex_lang = lang_data[ex_id]
        ex_logic = logic_data[ex_id]
        
        # --- 1. Identify Conflicts ---
        labels = ex_lang.get("labels", [])
        logic_stmts = ex_logic.get("statements", {})
        
        # Convert logic_stmts keys to int for easier handling if needed, but they match list indices
        # Check if logic_stmts is dict or list. Based on previous check it's likely a dict with string keys "0", "1"...
        
        sc_indices = []
        keep_indices = []
        
        for i, label in enumerate(labels):
            if label == "self_contradiction":
                sc_indices.append(str(i))
            else:
                keep_indices.append(str(i))
        
        if not sc_indices:
            # No cleaning needed for this example, just pass through (but normalize to new format)
            # Wait, we still need to output consistent format.
            # And we need to make sure we don't drop anything accidentally.
            pass

        # Collect dependencies
        conflict_facts = set()
        conflict_rules = set()
        
        for idx in sc_indices:
            # Get proof string
            # logic_stmts[idx] is [subj, pred, pol, proof]
            if idx in logic_stmts:
                proof = logic_stmts[idx][3]
                f, r = parse_proof(proof)
                conflict_facts.update(f)
                conflict_rules.update(r)
                
        keep_facts = set()
        keep_rules = set()
        
        for idx in keep_indices:
            if idx in logic_stmts:
                proof = logic_stmts[idx][3]
                f, r = parse_proof(proof)
                keep_facts.update(f)
                keep_rules.update(r)
                
        # Determine what to delete
        facts_to_delete = conflict_facts - keep_facts
        rules_to_delete = conflict_rules - keep_rules
        
        total_sc_removed += len(sc_indices)
        total_facts_removed += len(facts_to_delete)
        total_rules_removed += len(rules_to_delete)
        
        # --- 2. Re-index Facts ---
        old_facts_logic = ex_logic.get("facts", {}) # Dict "0": ...
        old_facts_text = ex_lang.get("facts", []) # List
        
        new_facts_logic = {}
        new_facts_text = []
        fact_map = {} # old_str_id -> new_str_id
        
        sorted_fact_ids = sorted(old_facts_logic.keys(), key=lambda x: int(x))
        
        new_f_idx = 0
        for fid in sorted_fact_ids:
            if fid in facts_to_delete:
                continue
            
            # Keep
            fact_map[fid] = str(new_f_idx)
            
            # Update logic entry
            entry = old_facts_logic[fid] # [subj, pred, pol, "fact X"]
            # Update the "fact X" part
            new_entry = entry[:]
            if len(new_entry) >= 4:
                new_entry[3] = f"fact {new_f_idx}"
            
            new_facts_logic[str(new_f_idx)] = new_entry
            
            # Update text entry
            # fid is string index "0", matches list index 0
            fid_int = int(fid)
            if fid_int < len(old_facts_text):
                new_facts_text.append(old_facts_text[fid_int])
            
            new_f_idx += 1
            
        # --- 3. Re-index Rules ---
        old_rules_logic = ex_logic.get("rules", {})
        old_rules_text = ex_lang.get("rules", [])
        
        new_rules_logic = {}
        new_rules_text = []
        rule_map = {}
        
        sorted_rule_ids = sorted(old_rules_logic.keys(), key=lambda x: int(x))
        
        new_r_idx = 0
        for rid in sorted_rule_ids:
            if rid in rules_to_delete:
                continue
                
            rule_map[rid] = str(new_r_idx)
            
            # Logic entry (nested structure) - usually doesn't contain ID reference to itself
            # But we might need to update references INSIDE rules? 
            # LogicNLI rules usually refer to facts by structure, not ID.
            # But wait, does a rule refer to another rule? No, rules are templates.
            # Does a rule refer to a fact ID? 
            # Looking at "1": {"p": {"fact": [...]...}
            # The facts inside rules are [subj, pred, pol], not IDs.
            # So rules are safe from internal updates?
            # Let's verify.
            new_rules_logic[str(new_r_idx)] = old_rules_logic[rid]
            
            rid_int = int(rid)
            if rid_int < len(old_rules_text):
                new_rules_text.append(old_rules_text[rid_int])
                
            new_r_idx += 1
            
        # --- 4. Process Statements ---
        new_stmts_text = []
        new_labels = []
        new_stmts_logic = {}
        
        # We iterate original indices 0..N
        # If index not in sc_indices, keep.
        
        new_s_idx = 0
        for i in range(len(labels)):
            s_idx_str = str(i)
            if s_idx_str in sc_indices:
                continue
            
            # Text & Label
            new_stmts_text.append(ex_lang["statements"][i])
            new_labels.append(ex_lang["labels"][i])
            
            # Logic
            if s_idx_str in logic_stmts:
                old_stmt = logic_stmts[s_idx_str] # [subj, pred, pol, proof]
                proof = old_stmt[3]
                new_proof = update_proof(proof, fact_map, rule_map)
                
                new_stmt = old_stmt[:]
                new_stmt[3] = new_proof
                
                new_stmts_logic[str(new_s_idx)] = new_stmt
            
            new_s_idx += 1
            
        # --- Construct Output Objects ---
        clean_lang_obj = {
            "id": ex_id,
            "facts": new_facts_text,
            "rules": new_rules_text,
            "statements": new_stmts_text,
            "labels": new_labels
        }
        
        clean_logic_obj = {
            "id": ex_id,
            "facts": new_facts_logic,
            "rules": new_rules_logic,
            "statements": new_stmts_logic
        }
        
        clean_lang_list.append(clean_lang_obj)
        clean_logic_list.append(clean_logic_obj)

    print(f"Total SC Removed: {total_sc_removed}")
    print(f"Total Facts Removed: {total_facts_removed}")
    print(f"Total Rules Removed: {total_rules_removed}")
    
    # Write JSONL
    print(f"Writing to {out_lang_path}...")
    with open(out_lang_path, 'w', encoding='utf-8') as f:
        for obj in clean_lang_list:
            f.write(json.dumps(obj) + "\n")
            
    print(f"Writing to {out_logic_path}...")
    with open(out_logic_path, 'w', encoding='utf-8') as f:
        for obj in clean_logic_list:
            f.write(json.dumps(obj) + "\n")

if __name__ == "__main__":
    # Base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    datasets_to_process = [
        (
            "dev_language.json", 
            "dev_logic.json", 
            "dev_language_clean.jsonl", 
            "dev_logic_clean.jsonl"
        ),
        (
            "test_language.json", 
            "test_logic.json", 
            "test_language_clean.jsonl", 
            "test_logic_clean.jsonl"
        ),
        (
            "train_language.json", 
            "train_logic.json", 
            "train_language_clean.jsonl", 
            "train_logic_clean.jsonl"
        )
    ]
    
    original_dir = os.path.join(base_dir, "original")
    clean_dir = os.path.join(base_dir, "clean_version")
    
    for lang_in, logic_in, lang_out, logic_out in datasets_to_process:
        input_lang_path = os.path.join(original_dir, lang_in)
        input_logic_path = os.path.join(original_dir, logic_in)
        
        output_lang_path = os.path.join(clean_dir, lang_out)
        output_logic_path = os.path.join(clean_dir, logic_out)
        
        print(f"\nProcessing {lang_in} and {logic_in}...")
        if os.path.exists(input_lang_path) and os.path.exists(input_logic_path):
            clean_dataset(input_lang_path, input_logic_path, output_lang_path, output_logic_path)
        else:
            print(f"Skipping {lang_in}/{logic_in}: Input files not found in {original_dir}")
