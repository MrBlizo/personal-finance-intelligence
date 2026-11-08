<#
.SYNOPSIS
    Installs the Store package layout (dist\msix\layout) on this PC for a
    test run, or removes it again.

.DESCRIPTION
    The .msix file is unsigned (the Microsoft Store signs it after
    certification), so Windows only accepts it for testing as a "loose"
    registration, which requires Developer Mode:
    Settings > System > For developers > Developer Mode = On.

    The test package is installed side by side with the normal PFI; it has
    its own private data folder, so your real data is not touched.

.EXAMPLE
    test-msix.bat            (install / update the test package)
    test-msix.bat -Remove    (uninstall the test package and its data)
#>
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$manifest = Join-Path $Root "dist\msix\layout\AppxManifest.xml"
$name = ([xml](Get-Content $manifest -Raw -ErrorAction SilentlyContinue)).Package.Identity.Name

if ($Remove) {
    Get-AppxPackage -Name $name | Remove-AppxPackage
    Write-Host "Removed $name." -ForegroundColor Green
    exit 0
}
if (-not (Test-Path $manifest)) {
    Write-Host "dist\msix\layout was not found. Run build.bat first." -ForegroundColor Red; exit 1
}
$dev = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" -ErrorAction SilentlyContinue
if (-not $dev -or $dev.AllowDevelopmentWithoutDevLicense -ne 1) {
    Write-Host "Developer Mode is off. Turn it on in Settings > System > For developers, then run test-msix.bat again." -ForegroundColor Yellow
    Start-Process "ms-settings:developers"
    exit 1
}
Add-AppxPackage -Register $manifest -ForceUpdateFromAnyVersion
Write-Host "Installed $name. Start 'Personal Finance Intelligence' from the Start menu (the packaged test version)." -ForegroundColor Green
