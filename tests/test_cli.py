"""CLI smoke tests: help for every subcommand and an offline demo run."""
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
    "subcommand", ["build-mgs", "run", "report", "audit", "demo"]
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
    assert '"is_consistent"' in lines[0]

    html = report_file.read_text(encoding="utf-8")
    assert "Metrics Summary" in html
    assert "Per-Group Results" in html

    captured = capsys.readouterr().out
    assert "MVR" in captured and "HDR" in captured


def test_demo_consistent_persona_has_no_violations(tmp_path):
    out_dir = tmp_path / "demo_consistent"
    rc = main(["demo", "--output", str(out_dir), "--persona", "consistent", "--quiet"])
    assert rc == 0
    content = (out_dir / "results.jsonl").read_text(encoding="utf-8")
    assert '"is_consistent": false' not in content
