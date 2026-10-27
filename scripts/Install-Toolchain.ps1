$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cli = '.tools\arduino\arduino-cli.exe'
if (!(Test-Path -LiteralPath $cli)) {
    New-Item -ItemType Directory -Force -Path '.tools' | Out-Null
    Invoke-WebRequest 'https://downloads.arduino.cc/arduino-cli/arduino-cli_1.3.1_Windows_64bit.zip' -OutFile '.tools\arduino-cli.zip'
    Expand-Archive -LiteralPath '.tools\arduino-cli.zip' -DestinationPath '.tools\arduino' -Force
}
& $cli core update-index --config-file arduino-cli.yaml
if ($LASTEXITCODE) { throw 'Arduino index download failed' }
& $cli core install esp32:esp32@3.3.2 --config-file arduino-cli.yaml
if ($LASTEXITCODE) { throw 'ESP32 toolchain installation failed' }
& $cli lib install ArduinoJson@7.4.2 --config-file arduino-cli.yaml
if ($LASTEXITCODE) { throw 'ArduinoJson installation failed' }
