# =============================================================================
# ODBA -- Open Defense Budget Analytics
# Run-Query.ps1  |  Budget Report Launcher
# =============================================================================

$ScriptDir   = $PSScriptRoot
$QueryScript = Join-Path $ScriptDir "query_budget.py"
$OutputFile  = Join-Path $ScriptDir "output\ODBA_FY2027_Budget_Report.xlsx"

function Pause-And-Exit {
    Write-Host ""
    Write-Host "  Press any key to close this window..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ODBA  FY2027 Budget Report Generator" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Find Python ───────────────────────────────────────────────────────
Write-Host "  [1/3] Checking for Python 3..." -ForegroundColor White
$PythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ("$ver" -match "Python 3") {
            $PythonCmd = $candidate
            Write-Host "        Found: $ver" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $PythonCmd) {
    Write-Host "  [ERROR] Python 3 not found. Run Run-ETL.ps1 first for install instructions." -ForegroundColor Red
    Pause-And-Exit
    return
}

# ── Step 2: Install packages ──────────────────────────────────────────────────
Write-Host ""
Write-Host "  [2/3] Installing required packages (duckdb, openpyxl)..." -ForegroundColor White
foreach ($pkg in @("duckdb", "openpyxl")) {
    & $PythonCmd -m pip install $pkg --quiet 2>&1 | Out-Null
    Write-Host "        [OK] $pkg" -ForegroundColor Green
}

# ── Step 3: Generate report ───────────────────────────────────────────────────
Write-Host ""
Write-Host "  [3/3] Generating report..." -ForegroundColor White
Write-Host ""

Set-Location $ScriptDir
& $PythonCmd $QueryScript
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

if ($ExitCode -eq 0 -and (Test-Path $OutputFile)) {
    $SizeKB = [math]::Round((Get-Item $OutputFile).Length / 1KB, 0)
    Write-Host "  SUCCESS" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Report saved to:" -ForegroundColor White
    Write-Host "    $OutputFile  ($SizeKB KB)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Opening report in Excel..." -ForegroundColor White
    Start-Process $OutputFile
} elseif ($ExitCode -ne 0) {
    Write-Host "  FAILED  (see errors above)" -ForegroundColor Red
    Write-Host "  Make sure you have run Run-ETL.ps1 first." -ForegroundColor Yellow
} else {
    Write-Host "  COMPLETED -- but report file not found." -ForegroundColor Yellow
}

Write-Host "============================================================" -ForegroundColor Cyan

Pause-And-Exit
