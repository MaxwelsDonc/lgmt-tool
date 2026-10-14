"""Module 1: dynamic custom-MR registration with Z3 verification, and
Module 2: input sniffing heuristics."""
import json

import pytest

import lgmt.mrs as mrs
from lgmt.core.builder import parse_and_normalize_cases
from lgmt.webapp import LISTING1_CUSTOM_MR_TEMPLATE, _render_studio_page


# --------------------------------------------------------------------- #
# registration + Z3 verification
# --------------------------------------------------------------------- #
@pytest.fixture()
def clean_registries():
    """Snapshot and restore the MR registries around each test."""
    snap_all = list(mrs.ALL_MRS)
    snap_cls = dict(mrs.MR_CLASS_REGISTRY)
    snap_idx = dict(mrs.MR_INDEX_REGISTRY)
    yield
    mrs.ALL_MRS[:] = snap_all
    mrs.MR_CLASS_REGISTRY.clear()
    mrs.MR_CLASS_REGISTRY.update(snap_cls)
    mrs.MR_INDEX_REGISTRY.clear()
    mrs.MR_INDEX_REGISTRY.update(snap_idx)


def test_listing1_template_registers_with_z3(clean_registries):
    results = mrs.load_mr_from_source(LISTING1_CUSTOM_MR_TEMPLATE)
    assert len(results) == 1
    r = results[0]
    assert r["index"] == "MR-CX"
    assert r["verified_count"] == r["tested"] == 5
    # visible through the normal registries
    assert len(mrs.ALL_MRS) == 21
    assert mrs.get_mr("MR-CX").name == "Double Negation (Custom)"


def test_non_equivalent_mr_rejected(clean_registries):
    bad = LISTING1_CUSTOM_MR_TEMPLATE.replace(
        "NegatedExpression(NegatedExpression(ast))", "NegatedExpression(ast)"
    ).replace('self.index = "MR-CX"', 'self.index = "MR-CB"')
    with pytest.raises(ValueError, match="Z3"):
        mrs.load_mr_from_source(bad)
    assert len(mrs.ALL_MRS) == 20  # nothing registered


def test_non_mr_code_rejected(clean_registries):
    with pytest.raises(ValueError, match="No MetamorphicRelation subclass"):
        mrs.load_mr_from_source("x = 1\n")


def test_register_mr_class_validates_shape(clean_registries):
    from lgmt.core.structure import MetamorphicRelation

    class NoIndex(MetamorphicRelation):
        def __init__(self):
            self.name = "x"

        def check_applicability_logic(self, fol):
            return True

        def source_templates(self):
            return []

        def check_applicability(self, tc):
            return True

        def transform(self, tc):
            return tc

    with pytest.raises(ValueError, match="index"):
        mrs.register_mr_class(NoIndex, verify_z3=False)


def test_load_from_examples_file(clean_registries):
    with open("examples/custom_mr_example.py", encoding="utf-8") as f:
        results = mrs.load_mr_from_source(f.read())
    assert results[0]["index"] == "MR-CX"
    assert results[0]["verified_count"] == 5


# --------------------------------------------------------------------- #
# input sniffing (Module 2)
# --------------------------------------------------------------------- #
def _fol_translator(premises_text, conclusion_text):
    return {
        "premises_logic": [f"Pred{i}(x)" for i, _ in enumerate(premises_text)],
        "conclusion_logic": "Concl(x)",
    }


def _fake_extractor(raw_text):
    return {
        "premises_text": ["Extracted premise one.", "Extracted premise two."],
        "conclusion_text": "Extracted conclusion.",
    }


def test_sniff_plain_fol_block_backfills_text():
    cases = parse_and_normalize_cases(
        "all x.(Man(x) -> Mortal(x))\nMan(socrates)\nMortal(socrates)"
    )
    assert len(cases) == 1
    assert cases[0].premises_logic == ["all x.(Man(x) -> Mortal(x))", "Man(socrates)"]
    assert cases[0].conclusion_logic == "Mortal(socrates)"
    # text backfilled from formulas
    assert cases[0].premises_text == cases[0].premises_logic


def test_sniff_nl_paragraph_with_arrow_goes_to_extractor():
    # NL text that happens to contain "->" must NOT be treated as FOL
    text = "If the server is down -> the sync fails.\nThe server is down."
    cases = parse_and_normalize_cases(
        text, translator=_fol_translator, extractor=_fake_extractor
    )
    assert len(cases) == 1
    assert cases[0].premises_logic == ["Pred0(x)", "Pred1(x)"]
    assert cases[0].premises_text[0] == "Extracted premise one."


def test_sniff_nl_paragraph_with_therefore_goes_to_extractor():
    text = (
        "All managers have a private office. Alice has a private office. "
        "Therefore: Alice is a manager."
    )
    cases = parse_and_normalize_cases(
        text, translator=_fol_translator, extractor=_fake_extractor
    )
    assert len(cases) == 1
    assert cases[0].conclusion_logic == "Concl(x)"


def test_sniff_mixed_fol_and_nl_blocks():
    text = (
        "P(a)\nQ(a)\n\nR(b)\n\n"
        "Every bird can fly. Tweety is a bird. Therefore Tweety can fly."
    )
    cases = parse_and_normalize_cases(
        text, translator=_fol_translator, extractor=_fake_extractor
    )
    assert len(cases) == 3
    # the two single-line FOL blocks became conclusion-only? No: a single
    # line cannot form premises+conclusion, so blocks of >=2 FOL lines are
    # FOL cases; "P(a)\nQ(a)" is one, "R(b)" alone is treated as NL
    fol_case = cases[0]
    assert fol_case.premises_logic == ["P(a)"] and fol_case.conclusion_logic == "Q(a)"
    assert cases[1].conclusion_logic == "Concl(x)"  # "R(b)" alone -> extractor
    assert cases[2].conclusion_logic == "Concl(x)"  # NL paragraph -> extractor


def test_sniff_jsonl_missing_fields_reports_line():
    good = '{"premises_logic": ["P(a)"], "conclusion_logic": "Q(a)"}'
    bad = good + '\n{"premises_text": ["only text"]}'
    with pytest.raises(ValueError, match="line 2"):
        parse_and_normalize_cases(bad)


def test_sniff_jsonl_branch_with_translator():
    payload = json.dumps(
        {
            "premises_text": ["All dogs are mammals.", "Rex is a dog."],
            "conclusion_text": "Rex is a mammal.",
            "metadata": {"label": "True"},
        }
    )
    cases = parse_and_normalize_cases(payload, translator=_fol_translator)
    assert len(cases) == 1
    assert cases[0].premises_logic == ["Pred0(x)", "Pred1(x)"]
    assert cases[0].metadata["label"] == "True"


def test_sniff_empty_input():
    with pytest.raises(ValueError, match="no test cases"):
        parse_and_normalize_cases("   \n  ")


# --------------------------------------------------------------------- #
# /api/register-mr endpoint
# --------------------------------------------------------------------- #
def test_api_register_mr_roundtrip(clean_registries):
    import threading
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), webapp_handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        def post(path, payload):
            req = urllib_request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            import urllib.error
            import urllib.request as _u
            try:
                with _u.urlopen(req, timeout=30) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())

        status, body = post("/api/register-mr", {"code": LISTING1_CUSTOM_MR_TEMPLATE})
        assert status == 200
        assert body["registered"][0]["verified_count"] == 5
        assert "trust" in body["trust_notice"].lower()

        status, body = post("/api/register-mr", {"code": "x = 1"})
        assert status == 400 and "error" in body
    finally:
        server.shutdown()
        server.server_close()


def webapp_handler():
    import lgmt.webapp as w

    return w._StudioHandler


def urllib_request(url, data, headers):
    import urllib.request as _u

    return _u.Request(url, data=data, headers=headers)
