param(
    [Parameter(Mandatory=$true)][ValidatePattern('^COM[0-9]+$')][string]$Port,
    [switch]$SkipBackup,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$manifest = Get-Content -Raw -LiteralPath artifacts/firmware-manifest.json | ConvertFrom-Json
foreach ($entry in $manifest.images.PSObject.Properties) {
    $imagePath = Join-Path 'artifacts/firmware' $entry.Name
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $imagePath).Hash.ToLower() -ne $entry.Value) { throw "Image hash mismatch: $imagePath" }
}
foreach ($entry in $manifest.sources.PSObject.Properties) {
    $sourcePath=Join-Path 'firmware/aikvm' $entry.Name
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash.ToLower() -ne $entry.Value) { throw "Source changed since this image was built: $sourcePath. Rebuild before flashing." }
}
$esptool = '.tools/arduino-data/packages/esp32/tools/esptool_py/5.1.0/esptool.exe'
if (!(Test-Path -LiteralPath $esptool)) { throw 'Run scripts/Install-Toolchain.ps1 first' }
if ($CheckOnly) { Write-Host 'All image hashes verified. Check-only: no device opened or flash written.'; return }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = "artifacts/flash-$stamp.log"
# Explicit chip selection rejects an incompatible MCU before any flash write.
& $esptool --chip esp32s3 --port $Port --before no-reset --after no-reset read-mac 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE) { throw 'Cannot identify ESP32-S3. Check BOOT/RESET, COM port and data cable.' }
if (!$SkipBackup) {
    $backup = "artifacts/device-backup-$stamp.bin"
    & $esptool --chip esp32s3 --port $Port --before no-reset --after no-reset read-flash 0 0x800000 $backup 2>&1 | Tee-Object -FilePath $logPath -Append
    if ($LASTEXITCODE) { throw 'Backup failed; firmware has not been written.' }
    Get-FileHash -Algorithm SHA256 -LiteralPath $backup | Format-List | Out-File -FilePath "$backup.sha256.txt"
}
# The merged image includes bootloader, partition table and application. This is
# a full 8MB bench image and replaces previous flash contents; backup is default.
& $esptool --chip esp32s3 --port $Port --before no-reset --after hard-reset write-flash 0 artifacts/firmware/aikvm.ino.merged.bin 2>&1 | Tee-Object -FilePath $logPath -Append
if ($LASTEXITCODE) { throw "Flash failed; inspect $logPath. Recover with BOOT held during USB connection." }
Write-Host 'Upload finished. Reconnect USB, rerun doctor for the runtime COM port, then run info and bench.'
Write-Host "Flash log: $logPath"
