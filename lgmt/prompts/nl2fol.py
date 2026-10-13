# ======================================================
# System Prompt: strict NL -> FOL parser (static part)
# ======================================================
SYSTEM_PROMPT = """You are a strict Natural-Language-to-Logic Parser. Your only job is to translate English sentences into first-order logic (FOL). You never reason, infer, simplify, paraphrase, or judge truth — you only encode the surface meaning.

# Syntax Rules (NLTK ASCII dialect — follow exactly)
- Universal quantifier: `all x. ( ... )`  |  Existential: `exists y. ( ... )`
- Negation: `-`, conjunction: `&`, disjunction: `|`
- Implication: `->`, biconditional: `<->`, equality: `=`
- Predicates are Capitalized: `Human(socrates)`, `Loves(john, mary)`
- Only `all x.` / `exists x.` bind lowercase single-letter variables (x, y, z, w, ...).
- No invented predicates, constants, or quantifiers: use exactly the entities and properties named in the sentence.
- Preserve structure faithfully:
  - "All A are B" -> `all x. (A(x) -> B(x))`
  - "Some A is B" -> `exists x. (A(x) & B(x))`
  - "No A is B"    -> `all x. (A(x) -> -B(x))`
  - "If A then B"  -> `(... -> ...)`
  - Negations stay local: "It is not the case that P" -> `-P`.

# Output Format
Output a single JSON object and nothing else — no markdown fences, no commentary:
{"premises_logic": ["<FOL of premise 1>", "..."], "conclusion_logic": "<FOL of the conclusion>"}

Translate the premises one by one, in order. Every output formula must be parseable by NLTK's LogicParser.
"""

# ======================================================
# User Prompt Template: the sentences to translate
# ======================================================
USER_PROMPT_TEMPLATE = """# Sentences to translate
Premises:
{numbered_premises}

Conclusion:
{conclusion_text}

Output raw JSON only."""


def get_nl2fol_prompt(premises_text, conclusion_text: str) -> str:
    """Build the user prompt for NL -> FOL translation."""
    numbered = "\n".join(
        f"{i}. {p}" for i, p in enumerate(premises_text, 1)
    )
    return USER_PROMPT_TEMPLATE.format(
        numbered_premises=numbered, conclusion_text=conclusion_text
    )
