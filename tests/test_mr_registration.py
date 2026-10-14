"""MR auto-registration: a class dropped into a lgmt.mrs subpackage is
picked up without editing __init__.py."""
import importlib
import sys
from pathlib import Path

import lgmt.mrs
from lgmt.core.structure import MetamorphicRelation, TestCase


class _TempMR(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-T9"
        self.name = "Temp Registration Probe"

    def check_applicability_logic(self, fol: str) -> bool:
        return True

    def source_templates(self):
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        return True

    def transform(self, source_case: TestCase) -> TestCase:
        return source_case


MODULE_SRC = '''
from lgmt.core.structure import MetamorphicRelation, TestCase


class MRT9(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-T9"
        self.name = "Temp Registration Probe"

    def check_applicability_logic(self, fol: str) -> bool:
        return True

    def source_templates(self):
        return []

    def check_applicability(self, test_case: TestCase) -> bool:
        return True

    def transform(self, source_case: TestCase) -> TestCase:
        return source_case
'''

PKG_DIR = Path(lgmt.mrs.__file__).resolve().parent / "premise"
MODULE_PATH = PKG_DIR / "mrt9_probe.py"


def test_automatic_registration_of_new_mr():
    assert len(lgmt.mrs.ALL_MRS) == 20
    assert "MRT9" not in lgmt.mrs.MR_CLASS_REGISTRY

    MODULE_PATH.write_text(MODULE_SRC, encoding="utf-8")
    try:
        importlib.invalidate_caches()
        importlib.import_module("lgmt.mrs.premise.mrt9_probe")
        reloaded = importlib.reload(lgmt.mrs)

        assert "MRT9" in reloaded.MR_CLASS_REGISTRY
        assert any(mr.index == "MR-T9" for mr in reloaded.ALL_MRS)
        assert len(reloaded.ALL_MRS) == 21
        # canonical 20 keep their stable leading order
        assert [mr.index for mr in reloaded.ALL_MRS[:20]] == [
            mr.index for mr in lgmt.mrs.ALL_MRS[:20]
        ]
        assert reloaded.get_mr("MR-T9").name == "Temp Registration Probe"
    finally:
        MODULE_PATH.unlink(missing_ok=True)
        for pyc in (PKG_DIR / "__pycache__").glob("mrt9_probe*.pyc"):
            pyc.unlink(missing_ok=True)
        sys.modules.pop("lgmt.mrs.premise.mrt9_probe", None)
        importlib.reload(lgmt.mrs)
        assert len(lgmt.mrs.ALL_MRS) == 20
