param(
    [switch]$SkipChecks,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonScript = Join-Path $projectRoot "scripts\python.ps1"
$webDirectory = Join-Path $projectRoot "apps\web"

function Assert-Path {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw $Message
    }
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $windowCommand = "`$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process -FilePath "powershell.exe" `
        -WorkingDirectory $WorkingDirectory `
        -ArgumentList @(
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-Command", $windowCommand
        ) | Out-Null
}

function Test-PortAvailable {
    param([int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Select-Port {
    param([int]$RequestedPort, [string]$Label)

    for ($candidate = $RequestedPort; $candidate -lt ($RequestedPort + 20); $candidate++) {
        if (Test-PortAvailable $candidate) {
            if ($candidate -ne $RequestedPort) {
                Write-Warning "$Label port $RequestedPort is unavailable; using $candidate instead."
            }
            return $candidate
        }
    }
    throw "No available $Label port found in range $RequestedPort-$($RequestedPort + 19)."
}

if (-not $SkipChecks) {
    Assert-Path (Join-Path $projectRoot ".venv\pyvenv.cfg") "Python environment is missing. Run: uv sync --extra dev"
    $ApiPort = Select-Port $ApiPort "FastAPI"
    $WebPort = Select-Port $WebPort "Next.js"
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        throw "pnpm was not found in PATH. Install pnpm or activate your Node.js environment."
    }

    $localNextExecutable = Join-Path $webDirectory "node_modules\.bin\next.cmd"
    $rootNextExecutable = Join-Path $projectRoot "node_modules\.bin\next.CMD"
    if (-not (Test-Path -LiteralPath $localNextExecutable) -and -not (Test-Path -LiteralPath $rootNextExecutable)) {
        Write-Host "Frontend dependencies are missing; installing them now..."
        & pnpm --dir apps/web install
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend dependency installation failed (exit code $LASTEXITCODE). Run: pnpm --dir apps/web install"
        }
        if (-not (Test-Path -LiteralPath $localNextExecutable) -and -not (Test-Path -LiteralPath $rootNextExecutable)) {
            throw "Frontend installation completed but Next.js was not found. Run: pnpm --dir apps/web install"
        }
    }
}

$apiCommand = "& '$pythonScript' -m uvicorn apps.api.main:app --reload --port $ApiPort"
$runnerCommand = "& '$pythonScript' -m translator.runner"
$nextExecutable = Join-Path $webDirectory "node_modules\.bin\next.cmd"
if (-not (Test-Path -LiteralPath $nextExecutable)) {
    $nextExecutable = Join-Path $projectRoot "node_modules\.bin\next.CMD"
}
$webCommand = "`$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:$ApiPort'; & '$nextExecutable' dev --port $WebPort"

Start-ServiceWindow "PDF Translator - FastAPI" $projectRoot $apiCommand
Start-ServiceWindow "PDF Translator - Runner" $projectRoot $runnerCommand
Start-ServiceWindow "PDF Translator - Next.js" $webDirectory $webCommand

Write-Host "FastAPI: http://127.0.0.1:$ApiPort"
Write-Host "Next.js: http://localhost:$WebPort"
Write-Host "Three service windows started. Close those windows to stop the services."
