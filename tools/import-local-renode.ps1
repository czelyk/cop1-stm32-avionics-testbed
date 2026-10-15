# Non-destructive local import of the later Renode implementation into the prepared
# engineering portfolio. DOES NOT perform git operations. Read before running.
param(
  [string]$Workspace = (Join-Path $env:USERPROFILE 'Documents\Codex\2026-10-13\iac-2027-konu-arastirmasi\automation'),
  [string]$Destination = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) {
  throw "Research workspace not found: $Workspace. Pass -Workspace with the correct existing folder."
}
$Destination = [System.IO.Path]::GetFullPath($Destination)
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { throw "Destination does not exist: $Destination" }

# Require an *unambiguous* source directory containing both firmware and campaign runner.
$candidates = @(Get-ChildItem -LiteralPath $Workspace -File -Recurse -Filter 'stm32_firmware.c' -ErrorAction Stop |
  Where-Object { $_.FullName -notmatch '[\\/](runtime|build|\.git)[\\/]' } |
  Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'coupled_renode.py') })
if ($candidates.Count -ne 1) {
  Write-Host "Found $($candidates.Count) Renode source candidates:"
  foreach ($c in $candidates) { Write-Host "  $($c.DirectoryName)" }
  throw 'Expected exactly one verified Renode research root. Resolve duplicates or pass a narrower -Workspace directory.'
}
$Source = $candidates[0].DirectoryName
Write-Host "Verified source directory: $Source"
Write-Host "Public portfolio destination: $Destination"

# Strictly allowlisted text/source files only. Avoid raw evidence, binaries,
# private prediction campaigns, runtime bundles and research manuscript files.
$files = @(
  @('stm32_firmware.c','firmware/stm32f4/stm32_firmware.c'),
  @('stm32_startup.c','firmware/stm32f4/stm32_startup.c'),
  @('pool_adapter.c','firmware/stm32f4/pool_adapter.c'),
  @('stm32.ld','firmware/stm32f4/stm32.ld'),
  @('build_firmware.py','firmware/stm32f4/build_firmware.py'),
  @('stm32_profile.repl','simulation/renode/stm32_profile.repl'),
  @('renode_driver.py','simulation/renode/renode_driver.py'),
  @('screen_renode.py','tests/renode/screen_renode.py'),
  @('coupled_renode.py','tests/renode/coupled_renode.py'),
  @('renode_v3_controls.py','tests/renode/renode_v3_controls.py'),
  @('audit_and_report.py','tests/renode/audit_and_report.py'),
  @('CTC1-RENODE-STM32-RESULTS.md','docs/renode-validation.md'),
  @('RENODE-VERIFIED-RESULTS.json','results/renode-verified-results.json'),
  @('renode_case_results.csv','results/renode-case-results.csv'),
  @('native_tm_verification.json','results/renode-tm-verification.json')
)
$copied = 0; $same = 0; $missing = @(); $skipped = @()
foreach ($pair in $files) {
  $inName=$pair[0];$outName=$pair[1];$inFile=Join-Path $Source $inName
  $outFile=Join-Path $Destination $outName
  if (-not (Test-Path -LiteralPath $inFile -PathType Leaf)) { $missing += $inName; continue }
  $raw = Get-Content -LiteralPath $inFile -Raw -ErrorAction Stop
  # Prevent accidental inclusion of high-risk credentials and author-specific paths.
  if ($raw -match 'ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}|sk-[A-Za-z0-9_-]{20}|AKIA[A-Z0-9]{16}|-----BEGIN .*PRIVATE KEY-----') {
    $skipped += "POSSIBLE SECRET: $inName"; continue
  }
  if ($raw -match '[A-Za-z]:[\\/](Users|Program Files|Windows)[\\/]|[/]home[/][^/\\]+[/]') {
    $skipped += "ABSOLUTE LOCAL PATH (manual portability fix needed): $inName"; continue
  }
  if (Test-Path -LiteralPath $outFile) {
    $inHash=(Get-FileHash -LiteralPath $inFile -Algorithm SHA256).Hash
    $outHash=(Get-FileHash -LiteralPath $outFile -Algorithm SHA256).Hash
    if ($inHash -eq $outHash) { $same++;continue }
    $skipped += "EXISTING DIFFERENT FILE: $outName";continue
  }
  New-Item -ItemType Directory -Path (Split-Path -Parent $outFile) -Force | Out-Null
  Copy-Item -LiteralPath $inFile -Destination $outFile -ErrorAction Stop
  $copied++
}
Write-Host "\nImported: $copied; already identical: $same"
if ($missing.Count) { Write-Warning ('Missing allowed files: ' + ($missing -join ', ')) }
if ($skipped.Count) { Write-Warning ('Skipped (NOT imported): ' + ($skipped -join '; ')) }
Write-Host 'No files were removed or overwritten, and no Git operations were performed.'
Write-Host 'IMPORTANT: Inspect copied source, dependency references, licensing, and reproducibility before publishing.'
