# Move-AIDelivery.ps1
# AI-Delivery Router for Steven Powell.
# Pick a file from one model's box and copy it into another model's box.
# Copies only -- never moves, never deletes, never overwrites silently.
# Every copy is written to the destination box's transfer-log.txt.
#
# Boxes are discovered automatically: any folder under
#   C:\Users\ntadmin\AI-Delivery\Inbox\<MODEL>
#   C:\Users\ntadmin\AI-Delivery\Outbox\<MODEL>
# counts as a box. New models appear on their own when their folders exist.
#
# Usage:  powershell -ExecutionPolicy Bypass -File Move-AIDelivery.ps1
# Test:   add -BasePath <folder> and -TestAnswers "1,1,2" to drive it
#         non-interactively against a simulated tree.

param(
    [string]$BasePath = "C:\Users\ntadmin\AI-Delivery",
    [string]$TestAnswers = ""
)

$ErrorActionPreference = "Stop"

# --- input helper: interactive prompt, or answers from -TestAnswers --------
$script:answerQueue = @()
if ($TestAnswers -ne "") {
    $script:answerQueue = $TestAnswers -split "," | ForEach-Object { $_.Trim() }
}
function Read-Choice([string]$Prompt) {
    if ($script:answerQueue.Count -gt 0) {
        $a = $script:answerQueue[0]
        $script:answerQueue = $script:answerQueue[1..($script:answerQueue.Count - 1)]
        Write-Host "$Prompt $a   [test answer]"
        return $a
    }
    return Read-Host $Prompt
}

function Show-Menu([string]$Title, [string[]]$Items) {
    Write-Host ""
    Write-Host $Title
    for ($i = 0; $i -lt $Items.Count; $i++) {
        Write-Host ("  {0}. {1}" -f ($i + 1), $Items[$i])
    }
    while ($true) {
        $raw = Read-Choice "Enter a number (or q to quit)"
        if ($raw -eq "q") { return -1 }
        $n = 0
        if ([int]::TryParse($raw, [ref]$n) -and $n -ge 1 -and $n -le $Items.Count) {
            return $n - 1
        }
        Write-Host "That is not on the list. Try again."
    }
}

# --- discover boxes ---------------------------------------------------------
if (-not (Test-Path $BasePath)) {
    Write-Host "AI-Delivery base folder not found: $BasePath"
    exit 1
}
$boxes = @()
foreach ($kind in @("Inbox", "Outbox")) {
    $kindPath = Join-Path $BasePath $kind
    if (Test-Path $kindPath) {
        foreach ($modelDir in (Get-ChildItem $kindPath -Directory | Sort-Object Name)) {
            $boxes += [pscustomobject]@{
                Label = "$kind\$($modelDir.Name)"
                Path  = $modelDir.FullName
            }
        }
    }
}
if ($boxes.Count -lt 2) {
    Write-Host "Need at least two boxes to route between. Found $($boxes.Count) under $BasePath."
    exit 1
}

# --- 1. source box ----------------------------------------------------------
$srcIdx = Show-Menu "Route FROM which box?" ($boxes | ForEach-Object { $_.Label })
if ($srcIdx -lt 0) { Write-Host "Quit. Nothing copied."; exit 0 }
$src = $boxes[$srcIdx]

# --- 2. file ----------------------------------------------------------------
$skipNames = @("transfer-log.txt", "README-MUSE.md", "repo-url.txt")
$files = Get-ChildItem $src.Path -File |
    Where-Object { $skipNames -notcontains $_.Name } |
    Sort-Object LastWriteTime -Descending
if ($files.Count -eq 0) {
    Write-Host "$($src.Label) has no routable files in it."
    exit 0
}
$fileLabels = $files | ForEach-Object {
    "{0}  ({1:N0} KB, {2})" -f $_.Name, ($_.Length / 1KB), $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm")
}
$fileIdx = Show-Menu "Which file from $($src.Label)?" $fileLabels
if ($fileIdx -lt 0) { Write-Host "Quit. Nothing copied."; exit 0 }
$file = $files[$fileIdx]

# --- 3. destination box -----------------------------------------------------
$destBoxes = $boxes | Where-Object { $_.Path -ne $src.Path }
$destIdx = Show-Menu "Route TO which box?" ($destBoxes | ForEach-Object { $_.Label })
if ($destIdx -lt 0) { Write-Host "Quit. Nothing copied."; exit 0 }
$dest = $destBoxes[$destIdx]

# --- 4. copy ----------------------------------------------------------------
$destFile = Join-Path $dest.Path $file.Name
if (Test-Path $destFile) {
    $existing = Get-Item $destFile
    $sameSize = $existing.Length -eq $file.Length
    $sameHash = $false
    if ($sameSize) {
        $sameHash = (Get-FileHash $destFile).Hash -eq (Get-FileHash $file.FullName).Hash
    }
    if ($sameHash) {
        Write-Host "Already there, byte-identical: $($dest.Label)\$($file.Name). Nothing to do."
        exit 0
    }
    Write-Host "A different file with this name is already in $($dest.Label):"
    Write-Host ("  there: {0:N0} bytes, {1}" -f $existing.Length, $existing.LastWriteTime)
    Write-Host ("  this : {0:N0} bytes, {1}" -f $file.Length, $file.LastWriteTime)
    $ans = Read-Choice "Type OVERWRITE to replace it, anything else to cancel"
    if ($ans -ne "OVERWRITE") { Write-Host "Cancelled. Nothing copied."; exit 0 }
}

Copy-Item $file.FullName $destFile -Force

# verify the copy byte-for-byte
$okHash = (Get-FileHash $destFile).Hash -eq (Get-FileHash $file.FullName).Hash
if (-not $okHash) {
    Write-Host "WARNING: copy verification failed -- hashes differ. Source left untouched."
    exit 1
}

# --- 5. log -----------------------------------------------------------------
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$line = "$stamp $($file.Name) routed $($src.Label) -> $($dest.Label)"
$logPath = Join-Path $dest.Path "transfer-log.txt"
Add-Content -Path $logPath -Value $line -Encoding UTF8

Write-Host ""
Write-Host "Done: $($file.Name)"
Write-Host "  from $($src.Label) to $($dest.Label), verified byte-identical, logged."
Write-Host "  The original is still in $($src.Label). Nothing was deleted."
