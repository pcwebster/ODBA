# ============================================================
# FY2027 Budget Justification - JSON File Downloader
# Comptroller of the Department of War
# ============================================================
# Run this script to download all 83 JSON files from:
# https://comptroller.war.gov/Budget-Materials/FY2027BudgetJustification/
#
# Files will be saved into the folder structure:
#   FY2027_Budget_JSON\
#     01_Operation_and_Maintenance\
#       Vol1_Part1\   (35 files)
#       Vol1_Part2\   (8 files)
#       Vol2\         (11 files)
#     06_Defense_Working_Capital_Fund\  (3 files)
#     09_Defense_Health_Program\        (26 files)
# ============================================================

$BaseUrl = "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/budget_justification/pdfs"
$BaseDir = "$PSScriptRoot"

# ── Folder paths ────────────────────────────────────────────
$Dirs = @{
    "OM1P1" = "$BaseDir\01_Operation_and_Maintenance\Vol1_Part1"
    "OM1P2" = "$BaseDir\01_Operation_and_Maintenance\Vol1_Part2"
    "OM2"   = "$BaseDir\01_Operation_and_Maintenance\Vol2"
    "DWCF"  = "$BaseDir\06_Defense_Working_Capital_Fund"
    "DHP"   = "$BaseDir\09_Defense_Health_Program"
}

# Ensure folders exist
foreach ($d in $Dirs.Values) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ── File list (hashtables avoid PowerShell array-flattening) ─
$Files = [System.Collections.Generic.List[hashtable]]::new()

# ── O&M Vol 1 Part 1 (35 files) ──────────────────────────────
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/OM_Volume1_Part1.json";       L="OM_Volume1_Part1.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/Overview_Exhibit.json";        L="Overview_Exhibit.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/Summary_by_Agency.json";       L="Summary_by_Agency.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/O-1_Summary.json";             L="O-1_Summary.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/OP-32A_Summary.json";          L="OP-32A_Summary.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/CMP_OP-5.json";               L="CMP_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DAU_OP-5.json";               L="DAU_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCAA_Cyber_OP-5.json";        L="DCAA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCAA_OP-5.json";              L="DCAA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCMA_Cyber_OP-5.json";        L="DCMA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCMA_OP-5.json";              L="DCMA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCSA_Cyber_OP-5.json";        L="DCSA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DCSA_OP-5.json";              L="DCSA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DHRA_Cyber_OP-5.json";        L="DHRA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DHRA_OP-5.json";              L="DHRA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DISA_Cyber_OP-5.json";        L="DISA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DISA_OP-5.json";              L="DISA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DLA_OP-5.json";               L="DLA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DLSA_OP-5.json";              L="DLSA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DoWDE_OP-5.json";             L="DoWDE_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DPAA_OP-5.json";              L="DPAA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DSCA_OP-5.json";              L="DSCA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DTRA_Cyber_OP-5.json";        L="DTRA_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DTRA_OP-5.json";              L="DTRA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DTSA_OP-5.json";              L="DTSA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/DWIA_OP-5.json";              L="DWIA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/MDA_OP-5.json";               L="MDA_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/OLDCC_OP-5.json";             L="OLDCC_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/OSW_OP-5.json";               L="OSW_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/OSW_Cyber_OP-5.json";         L="OSW_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/PSYOP_OP-5.json";             L="PSYOP_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/SOCOM_OP-5.json";             L="SOCOM_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/1-TJS_OP-5.json";             L="1-TJS_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/USCYBERCOM_OP-5.json";        L="USCYBERCOM_OP-5.json" })
$Files.Add(@{ F="OM1P1"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_1/WHS_OP-5.json";               L="WHS_OP-5.json" })

# ── O&M Vol 1 Part 2 (8 files) ───────────────────────────────
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/OM_Volume1_Part_2.json";      L="OM_Volume1_Part_2.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/CAAF_OP-5.json";             L="CAAF_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/CTR_OP-5.json";              L="CTR_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/DAWDA_OP-5.json";            L="DAWDA_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/OHDACA_OP-5.json";           L="OHDACA_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/OIG_OP-5.json";              L="OIG_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/OIG_Cyber_OP-5.json";        L="OIG_Cyber_OP-5.json" })
$Files.Add(@{ F="OM1P2"; R="01_Operation_and_Maintenance/O_M_VOL_1_PART_2/SISC_OP-5.json";             L="SISC_OP-5.json" })

# ── O&M Vol 2 (11 files) ─────────────────────────────────────
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/Volume_2.json";                        L="Volume_2.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/ENV-30.json";                          L="ENV-30.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/OP-8.json";                            L="OP-8.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/OP-31.json";                           L="OP-31.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/OP-34.json";                           L="OP-34.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/PB-15.json";                           L="PB-15.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/PB-24.json";                           L="PB-24.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/PB-28.json";                           L="PB-28.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/PB-31Q.json";                          L="PB-31Q.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/PB-61.json";                           L="PB-61.json" })
$Files.Add(@{ F="OM2"; R="01_Operation_and_Maintenance/O_M_VOL_2/Service_Support.json";                 L="Service_Support.json" })

# ── Defense Working Capital Fund (3 files) ────────────────────
$Files.Add(@{ F="DWCF"; R="06_Defense_Working_Capital_Fund/DoW_Revolving_Funds_J-Book_FY2027.json";     L="DoW_Revolving_Funds_J-Book_FY2027.json" })
$Files.Add(@{ F="DWCF"; R="06_Defense_Working_Capital_Fund/DeCA_PB27_J-Book.json";                      L="DeCA_PB27_J-Book.json" })
$Files.Add(@{ F="DWCF"; R="06_Defense_Working_Capital_Fund/PB_2027_DWWCF_Operating_and_Capital_Bgt_Est.json"; L="PB_2027_DWWCF_Operating_and_Capital_Bgt_Est.json" })

# ── Defense Health Program (26 files) ─────────────────────────
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/01-DHP_Vol_I_and_II_Cover_PB26.json";               L="01-DHP_Vol_I_and_II_Cover_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/02-DHP_Vol_I_and_II_Table_of_Contents_PB26.json";   L="02-DHP_Vol_I_and_II_Table_of_Contents_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/03-Vol_I_Sec_1-PBA-19_Introductory_Statement_DHP PB26.json"; L="03-Vol_I_Sec_1-PBA-19_Introductory_Statement_DHP_PB26.json" })
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
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/25-Vol_II_Sec_6-R-1_Research Development_Test_and_Evaluation_Programs_DHP PB26.json"; L="25-Vol_II_Sec_6-R-1_RDTE_Programs_DHP_PB26.json" })
$Files.Add(@{ F="DHP"; R="09_Defense_Health_Program/26-Vol_II_Sec_7-RDTE_Budget_Item_Justification_DHP_PB26.json"; L="26-Vol_II_Sec_7-RDTE_Budget_Item_Justification_DHP_PB26.json" })

# ── Download loop ────────────────────────────────────────────
$Total   = $Files.Count
$Success = 0
$Failed  = @()

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FY2027 Budget Justification JSON Downloader" -ForegroundColor Cyan
Write-Host "  Total files: $Total" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $Total; $i++) {
    $Entry    = $Files[$i]
    $DestPath = Join-Path $Dirs[$Entry.F] $Entry.L
    $Url      = "$BaseUrl/$($Entry.R)"

    $Pct = [int](($i / $Total) * 100)
    Write-Progress -Activity "Downloading JSON files" -Status "($($i+1)/$Total) $($Entry.L)" -PercentComplete $Pct

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

Write-Progress -Activity "Downloading JSON files" -Completed

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
