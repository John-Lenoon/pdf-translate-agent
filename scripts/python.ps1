$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sitePackages = Join-Path $repositoryRoot ".venv\Lib\site-packages"
$sourceRoot = Join-Path $repositoryRoot "python"

if (-not (Test-Path -LiteralPath $sitePackages)) {
    throw "Project dependencies are missing. Run: uv sync --extra dev"
}

$venvConfig = Join-Path $repositoryRoot ".venv\pyvenv.cfg"
$homeLine = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $homeLine) {
    throw "The virtual environment does not identify its base Python. Run: uv sync --extra dev"
}
$managedPython = Join-Path (($homeLine -split '=', 2)[1].Trim()) "python.exe"
if (-not (Test-Path -LiteralPath $managedPython)) {
    throw "The Python runtime used by .venv no longer exists. Run: uv sync --extra dev"
}

$env:PYTHONPATH = "$sitePackages$([IO.Path]::PathSeparator)$sourceRoot"
& $managedPython @args
exit $LASTEXITCODE
