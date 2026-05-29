# ============================================================
# FY2027 Budget Justification - Missing Files Mop-Up Script
# Downloads the 29 files that were missed in the first run:
#   - 3 individual files from O&M / DWCF
#   - All 26 Defense Health Program files
# ============================================================

$BaseUrl = "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/budget_justification/pdfs"
$BaseDir = "$PSScriptRoot"

$Dirs = @{
    "OM1P1" = "$BaseDir\01_Operation_and_Maintenance\Vol1_Part1"
    "OM1P2" = "$BaseDir\01_Operation_and_Maintenance\Vol1_Part2"
    "DWCF"  = "$BaseDir\06_Defense_Working_Capital_Fund"
    "DHP"   = "$BaseDir\09_Defense_Health_Program"
}

foreach ($d in $Dirs.Values) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

$Files = [System.Collections.Generic.List[hashtable]]::new()

# ── 3 straggler files from earlier sections ───────────────────
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/1-TJS_OP-5.json";  L="1-TJS_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/CAAF_OP-5.json";   L="CAAF_OP-5.json" })
$Files.Add(@{ F="DWCF";  R="06_Defense_Working_Capital_Fund/DeCA_PB27_J-Book.json";           L="DeCA_PB27_J-Book.json" })

# ── Defense Health Program (26 files) ─────────────────────────
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/01-DHP_Vol_I_and_II_Cover_PB26.json";               L="01-DHP_Vol_I_and_II_Cover_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/02-DHP_Vol_I_and_II_Table_of_Contents_PB26.json";   L="02-DHP_Vol_I_and_II_Table_of_Contents_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/03-Vol_I_Sec_1-PBA-19_Introductory_Statement_DHP%20PB26.json"; L="03-Vol_I_Sec_1-PBA-19_Introductory_Statement_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/04-Vol_I_Sec_2-O-1_Operation_and_Maintenance_Funding_DHP_PB26.json"; L="04-Vol_I_Sec_2-O-1_Operation_and_Maintenance_Funding_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/05-Vol_I_Sec-3-OP-32A_Summary_of_Price_and_Program_Growth_DHP_PB26.json"; L="05-Vol_I_Sec-3-OP-32A_Summary_of_Price_and_Program_Growth_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/06-Vol_I_Sec_4-PB-31R_Personnel_Summary_DHP_PB26.json"; L="06-Vol_I_Sec_4-PB-31R_Personnel_Summary_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/07-Vol_I_Sec_5-PB-31Q_PB26.json";                   L="07-Vol_I_Sec_5-PB-31Q_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/08-Vol_I_Sec_6-PB-31D_Summary_of_Funding_Increases_and_Decreases_DHP_PB26.json"; L="08-Vol_I_Sec_6-PB-31D_Summary_of_Funding_Increases_and_Decreases_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/09-Vol_I_Sec_7A-OP-5_In-House_Care_DHP_PB26.json";  L="09-Vol_I_Sec_7A-OP-5_In-House_Care_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/00-DHP_Vol_III_PB26.json";                           L="10-Vol_I_Sec_7B-OP-5_Private_Sector_Care_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/11-Vol_I_Sec_7C-OP-5_Consolidated_Health_Support_DHP_PB26.json"; L="11-Vol_I_Sec_7C-OP-5_Consolidated_Health_Support_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/12-Vol_I_Sec_7D-OP-5_Information_Management_DHP_PB26.json"; L="12-Vol_I_Sec_7D-OP-5_Information_Management_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/13-Vol_I_Sec_7E-OP-5_Management_Activities_DHP_PB26.json"; L="13-Vol_I_Sec_7E-OP-5_Management_Activities_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/14-Vol_I_Sec_7F-OP-5_Education_and_Training_DHP_PB26.json"; L="14-Vol_I_Sec_7F-OP-5_Education_and_Training_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/15-Vol_I_Sec_7G-OP-5_Base_Operations_and_Communications_DHP_PB26.json"; L="15-Vol_I_Sec_7G-OP-5_Base_Operations_and_Communications_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/16-Vol_I_Sec_7H-OP-5_Facilities_Sustainment_Restoration_and_Modernization_DHP_PB26.json"; L="16-Vol_I_Sec_7H-OP-5_Facilities_Sustainment_Restoration_and_Modernization_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/17-Vol_I_Sec_8-PB-11_Cost_of_Medical_Activities_DHP_PB26.json"; L="17-Vol_I_Sec_8-PB-11_Cost_of_Medical_Activities_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/18-Vol_I_Sec_9-PB-11A_Personnel_Summary_DHP_PB26.json"; L="18-Vol_I_Sec_9-PB-11A_Personnel_Summary_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/19-Vol_I_Sec_10-PB-11B_Medical_Workload_Data_DHP_PB26.json"; L="19-Vol_I_Sec_10-PB-11B_Medical_Workload_Data_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/20-Vol_II_Sec_1-PB-15_Advisory_and_Assistance_Services_DHP_PB26.json"; L="20-Vol_II_Sec_1-PB-15_Advisory_and_Assistance_Services_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/21-Vol_II_Sec_2-PB-28_Summary_of_Funds_Obligated_for_Environmental_Projects_DHP_PB26.json"; L="21-Vol_II_Sec_2-PB-28_Summary_of_Funds_Obligated_for_Environmental_Projects_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/22-Vol_II_Sec_3-PB-22_Major_DoD_Headquarters_Activities_DHP_PB26.json"; L="22-Vol_II_Sec_3-PB-22_Major_DoD_Headquarters_Activities_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/23-Vol_II_Sec_4-P-1_Procurement_Program_DHP_PB26.json"; L="23-Vol_II_Sec_4-P-1_Procurement_Program_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/24-Vol_II_Sec_5-P-40_Procurement_Budget_Item_Justification_DHP_PB26.json"; L="24-Vol_II_Sec_5-P-40_Procurement_Budget_Item_Justification_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/25-Vol_II_Sec_6-R-1_Research%20Development_Test_and_Evaluation_Programs_DHP%20PB26.json"; L="25-Vol_II_Sec_6-R-1_RDTE_Programs_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/26-Vol_II_Sec_7-RDTE_Budget_Item_Justification_DHP_PB26.json"; L="26-Vol_II_Sec_7-RDTE_Budget_Item_Justification_DHP_PB26.json" })

# ── Download loop ─────────────────────────────────────────────
$Total   = $Files.Count
$Success = 0
$Failed  = @()

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FY2027 Mop-Up: $Total missing files to download" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $Total; $i++) {
    $Entry    = $Files[$i]
    $DestPath = Join-Path $Dirs[$Entry.F] $Entry.L
    $Url      = "$BaseUrl/$($Entry.R)"

    $Pct = [int](($i / $Total) * 100)
    Write-Progress -Activity "Downloading missing files" -Status "($($i+1)/$Total) $($Entry.L)" -PercentComplete $Pct

    try {
        Invoke-WebRequest -Uri $Url -OutFile $DestPath -UseBasicParsing -ErrorAction Stop
        $Success++
        Write-Host "  [OK] $($Entry.L)" -ForegroundColor Green
    }
    catch {
        $Failed += $Entry.L
        Write-Host "  [FAIL] $($Entry.L)  --  $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Progress -Activity "Downloading missing files" -Completed

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Done.  $Success / $Total files downloaded successfully." -ForegroundColor Cyan
if ($Failed.Count -gt 0) {
    Write-Host "  Failed ($($Failed.Count)):" -ForegroundColor Yellow
    $Failed | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
