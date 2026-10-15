"""Module 1: dynamic custom-MR registration with Z3 verification, and
Module 2: input sniffing heuristics."""
import json

import pytest

import lgmt.mrs as mrs
import lgmt.webapp as webapp
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


# --------------------------------------------------------------------- #
# Fix 2: continuous progress across the synthesis + inference phases
# --------------------------------------------------------------------- #
def test_parse_progress_callback_ticks_per_record():
    ticks = []
    payload = "\n".join(
        [
            '{"premises_logic": ["P(a)"], "conclusion_logic": "Q(a)"}',
            '{"premises_logic": ["R(b)"], "conclusion_logic": "S(b)"}',
            '{"premises_logic": ["T(c)"], "conclusion_logic": "U(c)"}',
        ]
    )
    cases = parse_and_normalize_cases(payload, progress_callback=lambda t: ticks.append(t))
    assert len(cases) == 3
    assert len(ticks) == 3  # one tick per processed record


def test_custom_run_progress_is_continuous(monkeypatch, tmp_path):
    """One bar, one total: phase-1 (synthesis) steps flow into phase-2."""
    monkeypatch.setattr("lgmt.webapp._new_run_dir", lambda: str(tmp_path))
    fol = "\n".join(
        [
            '{"premises_logic": ["P(a)"], "conclusion_logic": "Q(a)", '
            '"premises_text": ["P(a)."], "conclusion_text": "Q(a)."}',
            '{"premises_logic": ["R(b)"], "conclusion_logic": "S(b)", '
            '"premises_text": ["R(b)."], "conclusion_text": "S(b)."}',
        ]
    )
    webapp.PROGRESS.clear()
    webapp.execute_custom_workflow(
        api_key="", base_url="", model="",
        cases_jsonl=fol, categories=["E", "C"],
        prompting="zero_direct", realize=False, use_mock=True,
    )
    snap = webapp.PROGRESS["custom"]
    # 2 synthesis steps + 2 MG inference steps on the same counter
    assert snap["total"] == 4
    assert snap["completed"] == 4
    assert snap["done"] is True


# --------------------------------------------------------------------- #
# Fix 3: custom-tab run history -> mutual leaderboard on the same caliber
# --------------------------------------------------------------------- #
def test_custom_tab_history_mutual_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr("lgmt.webapp._new_run_dir", lambda: str(tmp_path))
    webapp.RUNS_BY_TAB.pop("custom", None)
    webapp._RUN_HISTORY.clear()
    fol = (
        '{"premises_logic": ["P(a)"], "conclusion_logic": "Q(a)", '
        '"premises_text": ["P(a)."], "conclusion_text": "Q(a)."}'
    )

    def run(persona):
        return webapp.execute_custom_workflow(
            api_key="", base_url="", model="",
            cases_jsonl=fol, categories=["E", "C"],
            prompting="zero_direct", realize=False,
            use_mock=True, mock_persona=persona,
        )

    run("consistent")
    state2 = run("flawed")
    # both models ranked on the second render (custom data -> mutual board)
    assert "mock-consistent" in state2["body_html"]
    assert "mock-flawed" in state2["body_html"]
    assert "mutual comparison" in state2["body_html"]
    # consistent (MVR 0) ranks above flawed
    assert state2["body_html"].index("mock-consistent") < state2["body_html"].index("mock-flawed")

    # a different input is a different caliber bucket: no cross-ranking
    other = (
        '{"premises_logic": ["X(y)"], "conclusion_logic": "Z(y)", '
        '"premises_text": ["X(y)."], "conclusion_text": "Z(y)."}'
    )
    state3 = webapp.execute_custom_workflow(
        api_key="", base_url="", model="",
        cases_jsonl=other, categories=["E", "C"],
        prompting="zero_direct", realize=False, use_mock=True,
    )
    assert "mock-consistent" not in state3["body_html"]


# --------------------------------------------------------------------- #
# Fix 1: Load Example button fills structured JSONL
# --------------------------------------------------------------------- #
def test_load_example_button_fills_jsonl():
    page = _render_studio_page()
    assert 'onclick="loadJsonlPreset(\'EX_PRESET_JSONL\')"' in page
