# ======================================================
# System prompt: rules, role, and output format (static part)
# ======================================================
# SYSTEM_PROMPT = """You are a strict Logic-to-Language Translator. Convert the Transformed Logic Formula into Natural Language while preserving all structural, redundant, and logical characteristics.

# # Translation Rules
# 1. **Respect the structure**
#    - If you encounter `(-A | B)`, translate it as "Either it is not the case that A, or B".
#    - Translate `(-A | -B)` as "Either A is false or B is false"..
#    - Keep the quantifier order strictly left-to-right (e.g., `all x. exists y.`). Do not swap their positions.
#    - If a predicate repeats (e.g., `A | A`), output "Either A is true or A is true".
#    - If a tautology exists (e.g., `A | -A`), output "Either A is true or A is not true".
#    - If you encounter `& True` (or `& 1`), translate it as "...and it is logically true".
#    - If you encounter `| False` (or `| 0`), translate it as "...or it is logically false".

# 2. **Respect the symbol**
#    - Strictly use the predicates, relations, and symbols from the **Transformed Logic Formula**.
#    - Format `P(x)` as "x has property P", Format `- P(x)` as "x do not have property P".

#    - Format `R(x, y)` as "x bears relation R to y".
#    - Do NOT map symbols back to original meanings.

# # Output Format
# You must output a single JSON object containing the translation.
# Example: {"translation": "..."}
# """
SYSTEM_PROMPT = """You are a strict Logic-to-Language Translator. Your goal is to produce a structurally faithful translation of First-Order Logic into Natural Language, preserving all logical characteristics without simplification.

# Translation Rules
1. **Logical Connectives (Scope by Structure)**
   - **AND (&)**: Use "both A and B". If A is a complex sub-formula, use a comma: "both A, and B".
   - **OR (|)**: Use "either A or B".
   - **Biconditional (<->)**: Use "A if and only if B". (Use a comma before 'if' if A is complex).
   - **Negation (-)**: Always use the prefix "it is not the case that". 
     *Rule*: For `-A & B`, translate as "both it is not the case that A, and B" to ensure the negation scope is localized.

2. **Conditional Symbol Handling**
   - **Standard Word** (e.g., `Bitter(x)`, `Jadiel`): Use natural phrasing. 
     Example: `Bitter(Jadiel)` -> "Jadiel is Bitter"; `-Bitter(Jadiel)` -> "it is not the case that Jadiel is Bitter".
   - **Abstract/Placeholder** (e.g., `Pre1(x)`, `Con1`): Use formal phrasing. 
     Example: `Pre1(x)` -> "x has property Pre1"; `-Pre1(x)` -> "it is not the case that x has property Pre1".
   - **Relations**: `R(x, y)` -> "x bears relation R to y".

3. **Quantifiers & Variables**
   - Keep the order strictly left-to-right.
   - `all x.` -> "For all x, "
   - `exists x.` -> "There exists at least one x, such that "
   - **NO Pronouns**: Always repeat the variable (x, y) or entity name. Never use "it", "he", or "they".

4. **No Simplification**
   - **Double Negation (--A)**: Translate as "it is not the case that it is not the case that A".
   - **Redundancy (A | A)**: Translate as "either A is true or A is true".
   - **Constants**: `& 1` -> "...and it is logically true"; `| 0` -> "...or it is logically false".

# Examples for Reference
- FOL: --Orange(Stanley) -> {"translation": "it is not the case that it is not the case that Stanley is Orange."}
- FOL: (-Pre4(x) & Pre1(x)) -> {"translation": "both it is not the case that x has property Pre4, and x has property Pre1."}
- FOL: all x. (Bitter(x) -> -Dull(x)) -> {"translation": "For all x, if x is Bitter, then it is not the case that x is Dull."}
- FOL: (P(Con1) <-> (Q(Con2) | 0)) -> {"translation": "Con1 has property P if and only if, either Con2 has property Q or it is logically false."}

# Output Format
Output a single JSON object containing the translation.
"""
# ======================================================
# User prompt template: dynamic data part
# ======================================================
USER_PROMPT_TEMPLATE = """# Input Data
Original Formula (Context Only): {original_fol}
Original Sentence (Context Only): {original_nl}
**Transformed Logic Formula (TARGET): {transformed_fol}**

# Task
Provide the Natural Language translation of the **Transformed Logic Formula** strictly following the system rules and **Output raw JSON only** (no markdown formatting like ```json).
"""

def get_logic2NL_prompt(original_fol:str,transformed_fol:str,original_nl:str):
    return USER_PROMPT_TEMPLATE.format(original_fol=original_fol,transformed_fol=transformed_fol,original_nl=original_nl)
