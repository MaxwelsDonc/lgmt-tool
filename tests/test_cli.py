"""CLI smoke tests: help for every subcommand, list-mrs, shorthand aliases, and offline demo."""
import json
import os
import subprocess
import sys

import pytest

from lgmt.cli import main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_main_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize(
    "subcommand", ["build-mgs", "run", "report", "audit", "demo", "list-mrs", "web"]
)
def test_subcommand_help(subcommand):
    with pytest.raises(SystemExit) as exc:
        main([subcommand, "--help"])
    assert exc.value.code == 0


def test_python_dash_m_help():
    result = subprocess.run(
        [sys.executable, "-m", "lgmt", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "build-mgs" in result.stdout
    assert "Three Common Workflows" in result.stdout


def test_list_mrs_command(capsys):
    rc = main(["list-mrs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Total registered MRs: 20" in out
    assert "MR-E1.1" in out and "MR-C3" in out


def test_demo_end_to_end_offline(tmp_path, capsys):
    out_dir = tmp_path / "demo_output"
    rc = main(["demo", "--output", str(out_dir), "--quiet"])
    assert rc == 0

    results_file = out_dir / "results.jsonl"
    report_file = out_dir / "report.html"
    assert results_file.exists() and results_file.stat().st_size > 0
    assert report_file.exists() and report_file.stat().st_size > 0

    lines = results_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 40  # bundled demo set
    first_rec = json.loads(lines[0])
    assert "is_consistent" in first_rec
    # F1 verification: FOL logic is persisted directly in results.jsonl
    assert first_rec["source_input"].get("premises_logic")
    assert first_rec["followup_input"].get("premises_logic")

    html = report_file.read_text(encoding="utf-8")
    assert "Metrics Summary" in html
    assert "Per-Group Results" in html
    # F4 verification: default demo uses zero_cot, so no prompting mismatch note
    assert "note: reference used zero_cot" not in html

    captured = capsys.readouterr().out
    assert "MVR" in captured and "HDR" in captured


def test_run_with_demo_shorthand_and_report_without_mgs(tmp_path):
    res_file = tmp_path / "res.jsonl"
    rep_file = tmp_path / "rep.html"
    rc1 = main(["run", "--mgs", "demo", "--mock", "flawed", "--output", str(res_file)])
    assert rc1 == 0
    rc2 = main(["report", "--results", str(res_file), "--output", str(rep_file)])
    assert rc2 == 0
    html = rep_file.read_text(encoding="utf-8")
    # Even without --mgs, the report has full FOL logic arrays in #lgmt-data
    assert '"pl": [' in html or '"pl":[' in html


def test_demo_consistent_persona_has_no_violations(tmp_path):
    out_dir = tmp_path / "demo_consistent"
    rc = main(["demo", "--output", str(out_dir), "--persona", "consistent", "--quiet"])
    assert rc == 0
    content = (out_dir / "results.jsonl").read_text(encoding="utf-8")
    assert '"is_consistent": false' not in content
