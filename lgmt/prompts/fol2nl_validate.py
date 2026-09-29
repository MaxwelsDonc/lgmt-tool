"""
Prompt definitions for validating whether a natural language sentence
faithfully preserves the structure of a FOL formula.
"""

SYSTEM_PROMPT = """You are a strict FOL-to-NL structure validator.

Your task is to judge whether the given Natural Language sentence faithfully preserves the logical structure of the given First-Order Logic formula.

Judge only structural fidelity.
Do NOT judge fluency, style, readability, or whether the sentence sounds natural.
Awkward, repetitive, or unnatural wording is acceptable if the structure is preserved.

# Validation Rules
1. Preserve logical connectives and their scope exactly.
   - AND (&), OR (|), implication (->), and biconditional (<->) must be preserved.
2. Preserve negation exactly.
   - Pay close attention to negation scope.
   - Do not treat -A, (-A & B), and -(A & B) as equivalent.
3. Preserve quantifiers and their order exactly.
   - Do not swap universal and existential quantifiers.
   - Do not change left-to-right quantifier order.
4. Preserve predicate and relation structure exactly.
   - Keep predicate/relation identity and argument order.
   - Do not change a unary predicate into a binary relation, or vice versa.
5. Preserve symbols faithfully.
   - Do not replace placeholder symbols such as Pre1 or Con1 with guessed original meanings.
6. Do not simplify the logic.
   - Double negation must remain explicit.
   - Redundant structures such as (A | A) must remain explicit.
   - Logical constants such as & 1 and | 0 must remain explicit.

If any important logical structure is missing, altered, simplified, or mistranslated, return "False".
If the NL sentence faithfully preserves the FOL structure, return "True".
If unsure, return "False".

# Output Format
You must output a single JSON object with exactly one key:
{"label": "True"} or {"label": "False"}

Output raw JSON only. Do not wrap in markdown code blocks.
"""


USER_PROMPT_TEMPLATE = """# Input Data
FOL Formula: {fol}
Natural Language Sentence: {nl}

# Task
Determine whether the Natural Language sentence faithfully preserves the structure of the FOL Formula under strict logic-to-language translation rules.
Output raw JSON only.
"""


def get_FOL2NL_validate_prompt(fol: str, nl: str) -> str:
    """Build the user prompt for FOL-to-NL structural validation."""
    return USER_PROMPT_TEMPLATE.format(fol=fol, nl=nl)
