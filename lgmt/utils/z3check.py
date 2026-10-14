"""Z3-based equivalence checking for NLTK-style FOL formulas.

Translates the ASCII first-order-logic dialect used by LGMT (``all x.``,
``exists x.``, ``-``, ``&``, ``|``, ``->``, ``<->``, ``=``, predicates,
propositional atoms, and the logical constants ``1``/``0``) into z3py.

All individual symbols that are not bound by an explicit quantifier are
treated as universally quantified constants. This makes equivalence checks
robust under the symbol renamings performed by MR-S1/MR-E1.5: if the
universally closed bi-implication is valid, the formulas are equivalent
under any interpretation of those symbols.
"""
import re

import z3

__all__ = ["TranslationError", "FOLContext", "check_equivalence", "check_entailment_equivalence"]


class TranslationError(Exception):
    """Raised when a formula cannot be translated to z3."""


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+")
_SINGLE_CHAR_OPS = set("&|-()=,.")


def _tokenize(text: str):
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if text.startswith("<->", i):
            tokens.append("<->")
            i += 3
            continue
        if text.startswith("->", i):
            tokens.append("->")
            i += 2
            continue
        if c in _SINGLE_CHAR_OPS:
            tokens.append(c)
            i += 1
            continue
        m = _TOKEN_RE.match(text, i)
        if not m:
            raise TranslationError(f"unexpected character {c!r} in formula {text!r}")
        tokens.append(m.group(0))
        i = m.end()
    return tokens


class FOLContext:
    """Parses FOL formulas into z3 expressions with shared symbol tables.

    Constants get an uninterpreted sort; predicates become uninterpreted
    functions (or Booleans for arity 0). Reuse one context per equivalence
    query so that both sides share symbols.
    """

    def __init__(self):
        self.sort = z3.DeclareSort("S")
        self.consts: dict[str, z3.ExprRef] = {}
        self.preds: dict[tuple, z3.ExprRef] = {}

    # ------------------------------------------------------------------ #
    def _const(self, name: str) -> z3.ExprRef:
        if name not in self.consts:
            self.consts[name] = z3.Const(name, self.sort)
        return self.consts[name]

    def _pred(self, name: str, arity: int) -> z3.ExprRef:
        key = (name, arity)
        if key not in self.preds:
            if arity == 0:
                self.preds[key] = z3.Bool(name)
            else:
                self.preds[key] = z3.Function(
                    name, *([self.sort] * arity), z3.BoolSort()
                )
        return self.preds[key]

    # ------------------------------------------------------------------ #
    def parse(self, text: str) -> z3.ExprRef:
        parser = _Parser(_tokenize(text), self)
        expr = parser.parse_iff()
        if parser.peek() is not None:
            raise TranslationError(
                f"trailing tokens {parser.toks[parser.pos:]!r} in formula {text!r}"
            )
        return expr

    def close_universal(self, expr: z3.ExprRef) -> z3.ExprRef:
        """Universally quantify every individual constant seen so far."""
        if not self.consts:
            return expr
        return z3.ForAll(list(self.consts.values()), expr)


class _Parser:
    """Recursive-descent parser matching NLTK's operator precedence:

    ``-`` > ``&`` > ``|`` > ``->`` > ``<->`` (all binary ops left-assoc;
    quantifier bodies extend right up to the ``->`` boundary).
    """

    def __init__(self, tokens, ctx: FOLContext):
        self.toks = tokens
        self.pos = 0
        self.ctx = ctx

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def pop(self) -> str:
        t = self.peek()
        if t is None:
            raise TranslationError("unexpected end of formula")
        self.pos += 1
        return t

    # ------------------------------------------------------------------ #
    def parse_iff(self):
        left = self.parse_imp()
        while self.peek() == "<->":
            self.pop()
            left = left == self.parse_imp()
        return left

    def parse_imp(self):
        left = self.parse_or()
        while self.peek() == "->":
            self.pop()
            left = z3.Implies(left, self.parse_or())
        return left

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == "|":
            self.pop()
            left = z3.Or(left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_unary()
        while self.peek() == "&":
            self.pop()
            left = z3.And(left, self.parse_unary())
        return left

    def parse_unary(self):
        t = self.peek()
        if t == "-":
            self.pop()
            return z3.Not(self.parse_unary())
        if t in ("all", "exists"):
            self.pop()
            vars_ = []
            while (
                self.peek() is not None
                and self.peek() not in ("all", "exists")
                and _IDENT_RE.match(self.peek())
            ):
                vars_.append(self.pop())
            if not vars_ or self.peek() != ".":
                raise TranslationError("expected quantified variables and '.'")
            self.pop()
            body = self.parse_unary()  # quantifier body stops before &/|/->
            zvars = [self.ctx._const(v) for v in vars_]
            return (
                z3.ForAll(zvars, body) if t == "all" else z3.Exists(zvars, body)
            )
        return self.parse_atom()

    def parse_atom(self):
        t = self.pop()
        if t == "(":
            expr = self.parse_iff()
            if self.pop() != ")":
                raise TranslationError("expected ')' ")
            return expr
        if t == "1":
            return z3.BoolVal(True)
        if t == "0":
            return z3.BoolVal(False)
        if not _IDENT_RE.match(t):
            raise TranslationError(f"expected identifier, got {t!r}")
        nxt = self.peek()
        if nxt == "(":  # predicate application
            self.pop()
            args = []
            if self.peek() != ")":
                args.append(self._term())
                while self.peek() == ",":
                    self.pop()
                    args.append(self._term())
            if self.pop() != ")":
                raise TranslationError("expected ')' after predicate arguments")
            return self.ctx._pred(t, len(args))(*args)
        if nxt == "=":  # equality between individuals
            self.pop()
            return self.ctx._const(t) == self._term()
        return self.ctx._pred(t, 0)  # bare propositional atom

    def _term(self):
        t = self.pop()
        if not _IDENT_RE.match(t):
            raise TranslationError(f"expected term identifier, got {t!r}")
        return self.ctx._const(t)


def _conjoin(exprs):
    if not exprs:
        return z3.BoolVal(True)
    if len(exprs) == 1:
        return exprs[0]
    return z3.And(*exprs)


def check_equivalence(
    source_formulas,
    followup_formulas,
    timeout_ms: int = 5000,
) -> str:
    """Check that two premise sets are logically equivalent.

    Args:
        source_formulas: list of FOL formula strings (premise set or
            single conclusion).
        followup_formulas: same for the transformed side.

    Returns:
        ``"equivalent"``, ``"not_equivalent"``, ``"unknown"`` (z3 timeout /
        incompleteness), or ``"untranslatable"``.
    """
    ctx = FOLContext()
    try:
        src = _conjoin([ctx.parse(t) for t in source_formulas])
        fol = _conjoin([ctx.parse(t) for t in followup_formulas])
    except TranslationError:
        return "untranslatable"
    src = ctx.close_universal(src)
    fol = ctx.close_universal(fol)
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(src != fol)
    result = solver.check()
    if result == z3.unsat:
        return "equivalent"
    if result == z3.sat:
        return "not_equivalent"
    return "unknown"


def check_entailment_equivalence(
    src_premises,
    src_conclusion,
    fol_premises,
    fol_conclusion,
    timeout_ms: int = 5000,
) -> str:
    """Check ``(∧ Γ_src → q_src) ↔ (∧ Γ_fol → q_fol)`` validity.

    Same return contract as :func:`check_equivalence`
    (``"equivalent"`` / ``"not_equivalent"`` / ``"unknown"`` /
    ``"untranslatable"``).
    """
    ctx = FOLContext()
    try:
        src = z3.Implies(_conjoin([ctx.parse(t) for t in src_premises]), ctx.parse(src_conclusion))
        fol = z3.Implies(_conjoin([ctx.parse(t) for t in fol_premises]), ctx.parse(fol_conclusion))
    except TranslationError:
        return "untranslatable"
    src = ctx.close_universal(src)
    fol = ctx.close_universal(fol)
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(src != fol)
    result = solver.check()
    if result == z3.unsat:
        return "equivalent"
    if result == z3.sat:
        return "not_equivalent"
    return "unknown"
