param(
    [Parameter(Mandatory=$true)][string]$ControllerIP,
    [ValidateRange(1024,65535)][int]$Port=8787,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python=& '.venv/Scripts/python.exe' -c "import ctypes; b=ctypes.create_unicode_buffer(32768); ctypes.windll.kernel32.GetModuleFileNameW(None,b,len(b)); print(b.value)"
if ($LASTEXITCODE) { throw 'Cannot resolve the actual Python process executable' }
$address=Get-NetIPAddress -AddressFamily IPv4 -IPAddress $ControllerIP
$connection=Get-NetConnectionProfile -InterfaceIndex $address.InterfaceIndex
$category=$connection.NetworkCategory.ToString()
if ($category -eq 'DomainAuthenticated') { $category='Domain' }
$name="AIKVM-Paired-TLS-$ControllerIP-$Port"
if ($CheckOnly) {
    [PSCustomObject]@{ Rule=$name; Program=$python; Interface=$address.InterfaceAlias; LocalAddress=$ControllerIP; Profile=$category; RemoteAddress='LocalSubnet'; TcpPort=$Port }
    return
}
if (!(Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $name -DisplayName "AI KVM paired TLS $ControllerIP port $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -LocalAddress $ControllerIP -InterfaceAlias $address.InterfaceAlias -Program $python -Profile $category -RemoteAddress LocalSubnet | Out-Null
}
Write-Host "TCP $Port at $ControllerIP on $($address.InterfaceAlias) allowed for $python from the local subnet, profile $category."
Write-Host "Remove with: Remove-NetFirewallRule -Name '$name'"
