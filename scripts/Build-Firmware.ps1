$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$fqbn = 'esp32:esp32:XIAO_ESP32S3:USBMode=default,CDCOnBoot=cdc'
& '.tools\arduino\arduino-cli.exe' compile --config-file arduino-cli.yaml --fqbn $fqbn --build-path artifacts/build --output-dir artifacts/firmware firmware/aikvm 2>&1 | Tee-Object -FilePath artifacts/build.log
if ($LASTEXITCODE) { throw 'Firmware compile failed. See artifacts/build.log' }
$images = Get-ChildItem -LiteralPath artifacts/firmware -Filter '*.bin'
$hashes = @{}
foreach ($image in $images) { $hashes[$image.Name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $image.FullName).Hash.ToLower() }
$sources = @{}
Get-ChildItem -LiteralPath firmware/aikvm -File | ForEach-Object { $sources[$_.Name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower() }
@{ built_utc = [DateTime]::UtcNow.ToString('o'); board = 'Seeed XIAO ESP32S3'; fqbn = $fqbn; arduino_cli = '1.3.1'; esp32_core = '3.3.2'; arduino_json = '7.4.2'; firmware_version = '0.2.1'; images = $hashes; sources = $sources; hardware_tested = $false } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 artifacts/firmware-manifest.json
Write-Host 'Firmware built and hashed. No hardware execution is implied.'
