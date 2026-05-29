# ============================================================
# FY2027 Budget Justification - XML File Downloader
# Downloads 39 XML files across:
#   02_Procurement         (18 files)
#   03_RDT_and_E           (19 files)
#   09_Military_Health_System (2 files)
# ============================================================

$BaseUrl = "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/budget_justification/pdfs"
$BaseDir = "$PSScriptRoot"

# ── Folder paths ─────────────────────────────────────────────
$Dirs = @{
    "PROC_V1"  = "$BaseDir\02_Procurement\Vol1"
    "PROC_V2"  = "$BaseDir\02_Procurement\Vol2"
    "RDTE_V1"  = "$BaseDir\03_RDT_and_E\Vol1"
    "RDTE_V2"  = "$BaseDir\03_RDT_and_E\Vol2"
    "RDTE_V3"  = "$BaseDir\03_RDT_and_E\Vol3"
    "RDTE_V4"  = "$BaseDir\03_RDT_and_E\Vol4"
    "RDTE_V5"  = "$BaseDir\03_RDT_and_E\Vol5"
    "MHS"      = "$BaseDir\09_Military_Health_System"
}

foreach ($d in $Dirs.Values) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

$Files = [System.Collections.Generic.List[hashtable]]::new()

# ── Procurement Vol 1 (17 files) ─────────────────────────────
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PB_2027_PDW_VOL_1.xml";           L="PB_2027_PDW_VOL_1.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_CBDP_PB_2027.xml";           L="PROC_CBDP_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_CYBERCOM_PB_2027.xml";       L="PROC_CYBERCOM_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DCSA_PB_2027.xml";           L="PROC_DCSA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DHRA_PB_2027.xml";           L="PROC_DHRA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DISA_PB_2027.xml";           L="PROC_DISA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DLA_PB_2027.xml";            L="PROC_DLA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DMACT_PB_2027.xml";          L="PROC_DMACT_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DODEA_PB_2027.xml";          L="PROC_DODEA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DPAA_PB_2027.xml";           L="PROC_DPAA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DPAP_PB_2027.xml";           L="PROC_DPAP_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_OSC_PB_2027.xml";            L="PROC_OSC_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_DTRA_PB_2027.xml";           L="PROC_DTRA_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_OSD_PB_2027.xml";            L="PROC_OSD_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_SOCOM_PB_2027.xml";          L="PROC_SOCOM_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_TJS_PB_2027.xml";            L="PROC_TJS_PB_2027.xml" })
$Files.Add(@{ F="PROC_V1"; R="02_Procurement/PROC_WHS_PB_2027.xml";            L="PROC_WHS_PB_2027.xml" })

# ── Procurement Vol 2 (1 file) ────────────────────────────────
$Files.Add(@{ F="PROC_V2"; R="02_Procurement/PROC_MDA_VOL2B_PB_2027.xml";     L="PROC_MDA_VOL2B_PB_2027.xml" })

# ── RDT&E Vol 1 (1 file) ─────────────────────────────────────
$Files.Add(@{ F="RDTE_V1"; R="03_RDT_and_E/RDTE_Vol1_DARPA_MasterJustificationBook_PB_2027.xml"; L="RDTE_Vol1_DARPA_MasterJustificationBook_PB_2027.xml" })

# ── RDT&E Vol 2 (1 file) ─────────────────────────────────────
$Files.Add(@{ F="RDTE_V2"; R="03_RDT_and_E/RDTE_Vol2_MDA_RDTE_PB27_Justification_Book.xml";     L="RDTE_Vol2_MDA_RDTE_PB27_Justification_Book.xml" })

# ── RDT&E Vol 3 (2 files) ────────────────────────────────────
$Files.Add(@{ F="RDTE_V3"; R="03_RDT_and_E/RDTE_CHIPS_PB_2027.xml";           L="RDTE_CHIPS_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V3"; R="03_RDT_and_E/RDTE_OSW_PB_2027.xml";             L="RDTE_OSW_PB_2027.xml" })

# ── RDT&E Vol 4 (1 file) ─────────────────────────────────────
$Files.Add(@{ F="RDTE_V4"; R="03_RDT_and_E/RDTE_CBDP_PB_2027.xml";            L="RDTE_CBDP_PB_2027.xml" })

# ── RDT&E Vol 5 (14 files) ───────────────────────────────────
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/PB_2027_RDTE_VOL_5.xml";           L="PB_2027_RDTE_VOL_5.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_CYBERCOM_PB_2027.xml";        L="RDTE_CYBERCOM_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DCAA_PB_2027.xml";            L="RDTE_DCAA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DCMA_PB_2027.xml";            L="RDTE_DCMA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DCSA_PB_2027.xml";            L="RDTE_DCSA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DHRA_PB_2027.xml";            L="RDTE_DHRA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DISA_PB_2027.xml";            L="RDTE_DISA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DLA_PB_2027.xml";             L="RDTE_DLA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DSCA_PB_2027.xml";            L="RDTE_DSCA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DTIC_PB_2027.xml";            L="RDTE_DTIC_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_DTRA_PB_2027.xml";            L="RDTE_DTRA_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_OTE_PB_2027.xml";             L="RDTE_OTE_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_SOCOM_PB_2027.xml";           L="RDTE_SOCOM_PB_2027.xml" })
$Files.Add(@{ F="RDTE_V5"; R="03_RDT_and_E/RDTE_TJS_PB_2027.xml";             L="RDTE_TJS_PB_2027.xml" })

# ── Military Health System (2 files) ─────────────────────────
$Files.Add(@{ F="MHS"; R="09_Military_Health_System/MHS_PB27_J-Book-Vol1-COMP_PSCP.xml"; L="MHS_PB27_J-Book-Vol1-COMP_PSCP.xml" })
$Files.Add(@{ F="MHS"; R="09_Military_Health_System/MHS_PB27_J-Book-Vol2-SMR.xml";        L="MHS_PB27_J-Book-Vol2-SMR.xml" })

# ── Download loop ─────────────────────────────────────────────
$Total   = $Files.Count
$Success = 0
$Failed  = @()

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FY2027 XML Downloader  ($Total files)" -ForegroundColor Cyan
Write-Host "  Procurement: 18  |  RDT&E: 19  |  MHS: 2" -ForegroundColor Cyan
Write-Host "  Note: Vol 1 Procurement (~22 MB) and RDT&E Vol 5 (~40 MB)" -ForegroundColor Cyan
Write-Host "        are large combined files and may take a moment." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $Total; $i++) {
    $Entry    = $Files[$i]
    $DestPath = Join-Path $Dirs[$Entry.F] $Entry.L
    $Url      = "$BaseUrl/$($Entry.R)"

    $Pct = [int](($i / $Total) * 100)
    Write-Progress -Activity "Downloading XML files" -Status "($($i+1)/$Total) $($Entry.L)" -PercentComplete $Pct

    try {
        Invoke-WebRequest -Uri $Url -OutFile $DestPath -UseBasicParsing -ErrorAction Stop
        $Size = [math]::Round((Get-Item $DestPath).Length / 1MB, 2)
        $Success++
        Write-Host "  [OK] $($Entry.L)  ($Size MB)" -ForegroundColor Green
    }
    catch {
        $Failed += $Entry.L
        Write-Host "  [FAIL] $($Entry.L)  --  $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Progress -Activity "Downloading XML files" -Completed

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Done.  $Success / $Total files downloaded successfully." -ForegroundColor Cyan
if ($Failed.Count -gt 0) {
    Write-Host "  Failed ($($Failed.Count)):" -ForegroundColor Yellow
    $Failed | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Files saved to: $BaseDir" -ForegroundColor White
Write-Host ""
