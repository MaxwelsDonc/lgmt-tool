from lgmt.prompts.llm_infer import (
    SYS_FEW_SHOT_COT,
    SYS_FEW_SHOT_DIRECT,
    SYS_ZERO_SHOT_COT,
    SYS_ZERO_SHOT_DIRECT,
    USER_PROMPT_TEMPLATE,
)
from lgmt.prompts.logic2nl import SYSTEM_PROMPT as LOGIC2NL_SYSTEM_PROMPT
from lgmt.prompts.logic2nl import get_logic2NL_prompt
from lgmt.prompts.fol2nl_validate import get_FOL2NL_validate_prompt

__all__ = [
    "SYS_ZERO_SHOT_DIRECT",
    "SYS_ZERO_SHOT_COT",
    "SYS_FEW_SHOT_DIRECT",
    "SYS_FEW_SHOT_COT",
    "USER_PROMPT_TEMPLATE",
    "LOGIC2NL_SYSTEM_PROMPT",
    "get_logic2NL_prompt",
    "get_FOL2NL_validate_prompt",
]
