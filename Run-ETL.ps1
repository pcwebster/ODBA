# =============================================================================
# ODBA — Open Defense Budget Analytics
# Run-ETL.ps1  |  FY2027 Budget ETL Launcher
# =============================================================================

$ScriptDir  = $PSScriptRoot
$ETLScript  = Join-Path $ScriptDir "etl_budget.py"
$OutputDir  = Join-Path $ScriptDir "output"
$OutputFile = Join-Path $OutputDir "fact_budget_line_items.parquet"

function Pause-And-Exit {
    Write-Host ""
    Write-Host "  Press any key to close this window..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ODBA  FY2027 Budget ETL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check Python ──────────────────────────────────────────────────────
Write-Host "  [1/3] Checking for Python 3..." -ForegroundColor White

$PythonCmd = $null

foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ("$ver" -match "Python 3") {
            $PythonCmd = $candidate
            Write-Host "        Found: $ver  (using '$candidate')" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $PythonCmd) {
    Write-Host ""
    Write-Host "  [ERROR] Python 3 not found on this machine." -ForegroundColor Red
    Write-Host ""
    Write-Host "  To install Python:" -ForegroundColor Yellow
    Write-Host "    1. Go to  https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "    2. Download the latest Python 3.x installer" -ForegroundColor Yellow
    Write-Host "    3. Run the installer -- check 'Add Python to PATH'" -ForegroundColor Yellow
    Write-Host "    4. Re-open PowerShell and run this script again" -ForegroundColor Yellow
    Pause-And-Exit
    return
}

# ── Step 2: Install required packages ────────────────────────────────────────
Write-Host ""
Write-Host "  [2/3] Installing required Python packages (pandas, pyarrow)..." -ForegroundColor White

foreach ($pkg in @("pandas", "pyarrow")) {
    Write-Host "        Checking $pkg..." -ForegroundColor Gray
    & $PythonCmd -m pip install $pkg --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        [WARN] pip returned an error for $pkg" -ForegroundColor Yellow
    } else {
        Write-Host "        [OK] $pkg" -ForegroundColor Green
    }
}

# ── Step 3: Run ETL ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  [3/3] Running ETL script..." -ForegroundColor White
Write-Host "        (This may take a minute for large XML files)" -ForegroundColor Gray
Write-Host ""

$StopWatch = [System.Diagnostics.Stopwatch]::StartNew()

Set-Location $ScriptDir
& $PythonCmd $ETLScript
$ExitCode = $LASTEXITCODE

$StopWatch.Stop()
$Elapsed = [math]::Round($StopWatch.Elapsed.TotalSeconds, 1)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

if ($ExitCode -eq 0 -and (Test-Path $OutputFile)) {
    $FileSizeMB = [math]::Round((Get-Item $OutputFile).Length / 1MB, 2)
    Write-Host "  SUCCESS  ($Elapsed seconds)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Output file:" -ForegroundColor White
    Write-Host "    $OutputFile" -ForegroundColor Green
    Write-Host "    Size: $FileSizeMB MB" -ForegroundColor Green
} elseif ($ExitCode -ne 0) {
    Write-Host "  FAILED  (exit code $ExitCode)" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Common causes:" -ForegroundColor Yellow
    Write-Host "    - No XML/JSON files downloaded yet (run the downloader scripts first)" -ForegroundColor Yellow
    Write-Host "    - A file is corrupted or partially downloaded" -ForegroundColor Yellow
} else {
    Write-Host "  COMPLETED -- but output file not found." -ForegroundColor Yellow
    Write-Host "  Check the 'output' folder: $OutputDir" -ForegroundColor Yellow
}

Write-Host "============================================================" -ForegroundColor Cyan

Pause-And-Exit
