"""Compatibility shim: the Z3 FOL checker now lives in the package so the
tool itself can use it (custom-MR verification)."""
from lgmt.utils.z3check import *  # noqa: F401,F403
from lgmt.utils.z3check import (  # noqa: F401
    FOLContext,
    TranslationError,
    _Parser,
    _conjoin,
    _tokenize,
    check_equivalence,
)
