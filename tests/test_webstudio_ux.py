"""Web Studio UX batch: run progress (runner callback + /api/progress),
workers default, and the Workflow 3 single-format redesign."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import lgmt.webapp as webapp
from lgmt.core.runner import run_inference
from lgmt.models.base import LLMClient


class _Flaky(LLMClient):
    INV_PER_FAIL = 4

    def __init__(self, fail_invocations):
        self.seen = 0
        self.fail_invocations = fail_invocations

    def generate(self, prompt_data, model=None, **kwargs):
        self.seen += 1
        if self.seen <= self.fail_invocations:
            raise ConnectionError("boom")
        return json.dumps({"label": "True"})


# --------------------------------------------------------------------- #
# progress callback in the runner
# --------------------------------------------------------------------- #
def test_progress_callback_counts_every_group(demo_mgs_sample, tmp_path):
    calls = []
    run_inference(
        demo_mgs_sample[:6],
        _Flaky(fail_invocations=2 * _Flaky.INV_PER_FAIL),
        "prog",
        prompting="zero_direct",
        result_save_path=str(tmp_path / "r.jsonl"),
        max_workers=2,
        quiet=True,
        progress_callback=lambda done, total: calls.append((done, total)),
    )
    assert [c[0] for c in calls] == list(range(1, 7))  # monotonic, every group
    assert all(c[1] == 6 for c in calls)
    assert calls[-1] == (6, 6)  # failures included


def test_progress_callback_optional(demo_mgs_sample, tmp_path):
    # no callback: unchanged behavior
    run_inference(
        demo_mgs_sample[:2],
        _Flaky(0),
        "ok",
        prompting="zero_direct",
        result_save_path=str(tmp_path / "r.jsonl"),
        max_workers=1,
        quiet=True,
    )


# --------------------------------------------------------------------- #
# webapp progress registry + /api/progress endpoint
# --------------------------------------------------------------------- #
def test_progress_registry_and_endpoint(tmp_path):
    results = tmp_path / "results.jsonl"
    results.write_text(
        '{"is_valid": false}\n{"is_valid": true}\n{"is_valid": false}\n',
        encoding="utf-8",
    )
    webapp._begin_progress("benchmark", 10, str(results))
    webapp._progress_callback("benchmark")(4, 10)
    snap = webapp._read_progress("benchmark")
    assert snap["completed"] == 4 and snap["total"] == 10
    assert snap["failed"] == 2  # counted live from the results file
    assert snap["done"] is False
    webapp._finish_progress("benchmark", 2)
    snap = webapp._read_progress("benchmark")
    assert snap["done"] is True
    # unknown tab: inert zeros
    assert webapp._read_progress("nope") == {
        "completed": 0, "total": 0, "failed": 0, "done": False,
    }


def test_api_progress_endpoint_live(tmp_path):
    handler = webapp._StudioHandler
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        results = tmp_path / "results.jsonl"
        results.write_text('{"is_valid": false}\n', encoding="utf-8")
        webapp._begin_progress("demo", 40, str(results))
        webapp._progress_callback("demo")(7, 40)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/progress?tab=demo", timeout=5
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["completed"] == 7
        assert payload["total"] == 40
        assert payload["failed"] == 1
        assert payload["done"] is False
    finally:
        server.shutdown()
        server.server_close()
        webapp.PROGRESS.clear()


# --------------------------------------------------------------------- #
# Task 1 + Task 3: page structure
# --------------------------------------------------------------------- #
def _page() -> str:
    return webapp._render_studio_page()


def test_workers_default_is_32():
    assert 'id="b-workers" value="32"' in _page()


def test_workflow3_single_format_redesign():
    page = _page()
    # spec sentence is featured
    assert "One test case = a few premise lines + one conclusion." in page
    # main form fields present
    assert 'id="qf-premises"' in page and 'id="qf-conclusion"' in page
    # advanced batch JSONL fold present with template placeholder
    assert "Advanced: batch JSONL" in page
    assert 'id="c-cases"' in page
    assert "premises_text" in page
    # unstructured mode fully removed from the UI
    assert "sub-btn-unstructured" not in page
    assert "c-unstructured" not in page
    assert "Unstructured Paragraph" not in page
    assert "unstructured_en" not in page and "unstructured_zh" not in page
    assert "switchCustomMode" not in page
    # prompting still defaults to zero_direct
    assert '<select id="c-prompting">' in page
    idx = page.index('id="c-prompting"')
    segment = page[idx : idx + 400]
    assert 'value="zero_direct" selected' in segment


# --------------------------------------------------------------------- #
# Workflow 3 end-to-end through the backend entry point
# --------------------------------------------------------------------- #
def test_form_mode_fol_payload_end_to_end():
    """What the main form sends for an offline-ready (FOL) example."""
    fol_jsonl = (
        '{"premises_logic": ["all x.(Bird(x) -> Fly(x))", "Bird(tweety)"], '
        '"conclusion_logic": "Fly(tweety)", '
        '"premises_text": ["All birds can fly.", "Tweety is a bird."], '
        '"conclusion_text": "Tweety can fly.", "metadata": {"label": "True"}}'
    )
    state = webapp.execute_custom_workflow(
        api_key="",
        base_url="",
        model="",
        cases_jsonl=fol_jsonl,
        categories=["E", "S", "P", "C"],
        prompting="zero_direct",
        realize=False,
        use_mock=True,
        mock_persona="consistent",
    )
    assert "Custom run completed" in state["summary"]
    assert state["metrics"]["total"] >= 1
    assert state["metrics"]["mvr"] == 0.0  # consistent persona


def test_form_mode_nl_payload_requires_real_model():
    nl_jsonl = (
        '{"premises_text": ["All dogs are mammals.", "Rex is a dog."], '
        '"conclusion_text": "Rex is a mammal.", "metadata": {"label": "True"}}'
    )
    with pytest.raises(ValueError, match="real LLM API key"):
        webapp.execute_custom_workflow(
            api_key="",
            base_url="",
            model="",
            cases_jsonl=nl_jsonl,
            categories=["E"],
            prompting="zero_direct",
            realize=False,
            use_mock=True,
        )


def test_advanced_jsonl_batch_mode_end_to_end():
    batch = "\n".join(
        [
            '{"premises_logic": ["P(a)"], "conclusion_logic": "Q(a)", '
            '"premises_text": ["P(a)."], "conclusion_text": "Q(a).", '
            '"metadata": {"label": "True"}}',
            '{"premises_logic": ["R(b)"], "conclusion_logic": "S(b)", '
            '"premises_text": ["R(b)."], "conclusion_text": "S(b).", '
            '"metadata": {"label": "False"}}',
        ]
    )
    state = webapp.execute_custom_workflow(
        api_key="",
        base_url="",
        model="",
        cases_jsonl=batch,
        categories=["E", "C"],
        prompting="zero_direct",
        realize=False,
        use_mock=True,
    )
    assert state["metrics"]["total"] == 2
