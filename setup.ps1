# LGMT one-command setup (Windows PowerShell).
# Usage:  .\setup.ps1 [-Dev] [-Demo]
param(
    [switch]$Dev,
    [switch]$Demo
)
$ErrorActionPreference = "Stop"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) { throw "python not found; please install Python >= 3.10." }

$ok = & $py.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python >= 3.10 required (found $(& $py.Source --version))." }

if (-not (Test-Path .venv)) { & $py.Source -m venv .venv }
. .\.venv\Scripts\Activate.ps1

python -m pip install -q --upgrade pip
python -m pip install -q -e .
if ($Dev) { python -m pip install -q -e ".[dev]" }

if ($Demo) {
    lgmt demo
    Write-Host "Report written to demo_output\report.html"
} else {
    Write-Host "Done. Try: lgmt demo   (offline, no API key needed)"
}
