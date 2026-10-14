"""P1: repeated Web Studio benchmark runs accumulate into a mutual
leaderboard (aggregates only, capped history)."""
import json

import lgmt.webapp as webapp


class _StubClient:
    """Stands in for OpenAICompatClient (its constructor makes no calls)."""

    def __init__(self, api_key=None, base_url=None, models_map=None):
        self.api_key = api_key
        self.base_url = base_url


def _fake_run_inference(mgs, client, model_name, prompting="zero_cot",
                        result_save_path="", max_workers=1, quiet=True):
    """Writes plausible results without any network."""
    labels = {"model-a": "True", "model-b": "False"}
    label = labels.get(model_name, "True")
    with open(result_save_path, "w", encoding="utf-8") as f:
        for mg in mgs:
            f.write(json.dumps({
                "mg_id": mg.metadata.get("mg_id"),
                "mr_index": mg.metadata.get("mr_index", ""),
                "model": model_name,
                "prompting": prompting,
                "ground_truth": "True",
                "source_response": {"response_label": "True", "is_correct": True},
                "followup_response": {"response_label": label, "is_correct": label == "True"},
                "is_consistent": label == "True",
                "is_valid": True,
            }, ensure_ascii=False) + "\n")


def test_benchmark_history_builds_mutual_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "OpenAICompatClient", _StubClient)
    monkeypatch.setattr(webapp, "run_inference", _fake_run_inference)
    monkeypatch.setattr(webapp, "_new_run_dir", lambda: str(tmp_path))
    webapp.RUNS_BY_TAB.pop("benchmark", None)
    webapp._BENCH_HISTORY.clear()

    state_a = webapp.execute_benchmark_workflow(
        api_key="sk-test", base_url="https://example.test/v1",
        model="model-a", dataset="demo_40", prompting="zero_cot",
    )
    state_b = webapp.execute_benchmark_workflow(
        api_key="sk-test", base_url="https://example.test/v1",
        model="model-b", dataset="demo_40", prompting="zero_cot",
    )

    # second render must include both models on the leaderboard
    # (demo_40 caliber: reference board + mutual extra runs merged)
    assert "model-a" in state_b["body_html"]
    assert "model-b" in state_b["body_html"]
    # model-a (MVR 0) ranks above model-b (MVR 100%)
    assert state_b["body_html"].index("model-a") < state_b["body_html"].index("model-b")
    # the standalone HTML report carries the same mutual board
    report_html = open(state_b["report"], encoding="utf-8").read()
    assert "model-a" in report_html and "model-b" in report_html

    # history holds aggregates only and is capped
    hist = webapp._BENCH_HISTORY[("demo_40", "zero_cot")]
    assert all(set(h) == {"model", "metrics"} for h in hist)
    assert len(hist) <= webapp._BENCH_HISTORY_MAX


def test_benchmark_history_isolated_per_prompting(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "OpenAICompatClient", _StubClient)
    monkeypatch.setattr(webapp, "run_inference", _fake_run_inference)
    monkeypatch.setattr(webapp, "_new_run_dir", lambda: str(tmp_path))
    webapp.RUNS_BY_TAB.pop("benchmark", None)
    webapp._BENCH_HISTORY.clear()

    webapp.execute_benchmark_workflow(
        api_key="sk-test", base_url="https://example.test/v1",
        model="model-a", dataset="demo_40", prompting="zero_cot",
    )
    webapp.execute_benchmark_workflow(
        api_key="sk-test", base_url="https://example.test/v1",
        model="model-b", dataset="demo_40", prompting="few_cot",
    )
    # different prompting = different caliber bucket: no cross-ranking
    assert "model-a" not in webapp.RUNS_BY_TAB["benchmark"]["body_html"]
