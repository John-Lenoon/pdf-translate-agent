$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sitePackages = Join-Path $repositoryRoot ".venv\Lib\site-packages"
$sourceRoot = Join-Path $repositoryRoot "python"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $sitePackages) -or -not (Test-Path -LiteralPath $venvPython)) {
    throw "Project dependencies are missing. Run: uv sync --extra dev"
}

$env:PYTHONPATH = "$sitePackages$([IO.Path]::PathSeparator)$sourceRoot"
& $venvPython @args
exit $LASTEXITCODE
