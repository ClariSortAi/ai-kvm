$ErrorActionPreference='Stop'
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name,PNPDeviceID | Format-Table -AutoSize
Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in @('Camera','Image','Ports') } | Select-Object Class,FriendlyName,Status | Format-Table -AutoSize
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } | Select-Object InterfaceAlias,IPAddress | Format-Table -AutoSize
Get-NetConnectionProfile | Select-Object InterfaceAlias,NetworkCategory,IPv4Connectivity | Format-Table -AutoSize
