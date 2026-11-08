<#
.SYNOPSIS
    Downloads the NuGet packages for the WinUI 3 project and generates
    desktop\PFI\Packages.g.props / Packages.g.targets.

.DESCRIPTION
    Windows App SDK 2.x is split into several component packages. This
    script resolves the full dependency tree of Microsoft.WindowsAppSDK and
    Microsoft.Windows.CppWinRT from nuget.org (lowest applicable version for
    each dependency, like NuGet), extracts every package to desktop\packages
    and writes MSBuild imports for their native build files. Versions are
    pinned in desktop\packages.lock.json on first run, so later builds are
    reproducible; delete that file to update to the newest Windows App SDK.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\restore-desktop.ps1
#>
[CmdletBinding()]
param(
    [string]$WindowsAppSdkMajor = "2",
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = Split-Path -Parent $PSScriptRoot
$Desktop = Join-Path $Root "desktop"
$PkgDir = Join-Path $Desktop "packages"
$Lock = Join-Path $Desktop "packages.lock.json"
$Feed = "https://api.nuget.org/v3-flatcontainer"
New-Item -ItemType Directory -Force -Path $PkgDir | Out-Null

function Get-Json([string]$Url) {
    try { return Invoke-RestMethod -Uri $Url -UseBasicParsing }
    catch {
        throw "Could not download $Url ($($_.Exception.Message)). Check your internet connection or proxy, then run the build again."
    }
}

function Get-LatestStable([string]$Id, [string]$Major) {
    $versions = (Get-Json "$Feed/$($Id.ToLower())/index.json").versions |
        Where-Object { $_ -notmatch "-" }
    if ($Major) { $versions = $versions | Where-Object { $_ -like "$Major.*" } }
    if (-not $versions) { throw "No stable version of $Id found on nuget.org." }
    return ($versions | Sort-Object { [version]$_ } | Select-Object -Last 1)
}

function Get-MinVersion([string]$Range) {
    $r = $Range.Trim().TrimStart("[", "(").TrimEnd("]", ")")
    return ($r.Split(",")[0]).Trim()
}

function Get-Nuspec([string]$Id, [string]$Version) {
    $lid = $Id.ToLower()
    $url = "$Feed/$lid/$($Version.ToLower())/$lid.nuspec"
    try { return [xml](Invoke-WebRequest -Uri $url -UseBasicParsing).Content }
    catch { throw "Could not download $url ($($_.Exception.Message))." }
}

function Get-NativeDependencies([xml]$Nuspec) {
    $deps = $Nuspec.package.metadata.dependencies
    if (-not $deps) { return @() }
    $groups = @($deps.group)
    if ($groups.Count -gt 0 -and $groups[0]) {
        $g = $groups | Where-Object { $_.targetFramework -like "native*" } | Select-Object -First 1
        if (-not $g) { $g = $groups | Where-Object { -not $_.targetFramework } | Select-Object -First 1 }
        if (-not $g) { return @() }
        return @($g.dependency | Where-Object { $_ })
    }
    return @($deps.dependency | Where-Object { $_ })
}

# ---------------------------------------------------------------- resolve
if ((Test-Path $Lock) -and -not $Force) {
    $locked = Get-Content $Lock -Raw | ConvertFrom-Json
    $resolved = [ordered]@{}
    $order = @()
    foreach ($p in $locked.packages) { $resolved[$p.id] = $p.version; $order += $p.id }
    Write-Host "Using pinned package versions from desktop\packages.lock.json"
} else {
    $roots = [ordered]@{
        "Microsoft.WindowsAppSDK"   = Get-LatestStable "Microsoft.WindowsAppSDK" $WindowsAppSdkMajor
        "Microsoft.Windows.CppWinRT" = Get-LatestStable "Microsoft.Windows.CppWinRT" ""
    }
    $resolved = [ordered]@{}
    $deps = @{}
    $queue = New-Object System.Collections.Queue
    foreach ($k in $roots.Keys) { $queue.Enqueue(@($k, $roots[$k])) }
    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue(); $id = $item[0]; $ver = $item[1]
        if ($resolved.Contains($id) -and ([version]$resolved[$id] -ge [version]$ver)) { continue }
        $resolved[$id] = $ver
        $spec = Get-Nuspec $id $ver
        $id = $spec.package.metadata.id       # canonical casing
        if (-not $resolved.Contains($id)) { $resolved[$id] = $ver }
        $deps[$id] = @()
        foreach ($d in (Get-NativeDependencies $spec)) {
            $dv = Get-MinVersion $d.version
            $deps[$id] += $d.id
            $queue.Enqueue(@($d.id, $dv))
        }
    }
    # dependency-first order (props/targets of dependencies are imported first)
    $order = New-Object System.Collections.ArrayList
    $visit = @{}
    function Visit($n) {
        if ($visit[$n]) { return }; $visit[$n] = $true
        foreach ($c in @($deps[$n])) { if ($c) { Visit $c } }
        [void]$order.Add($n)
    }
    foreach ($k in @($resolved.Keys)) { Visit $k }
    $lockObj = @{ generated = (Get-Date).ToString("s"); packages = @(
        foreach ($n in $order) { @{ id = $n; version = $resolved[$n] } }) }
    $lockObj | ConvertTo-Json -Depth 4 | Set-Content -Path $Lock -Encoding UTF8
    Write-Host "Resolved $($order.Count) packages; pinned in desktop\packages.lock.json"
}

# --------------------------------------------------------------- download
foreach ($id in $order) {
    $ver = $resolved[$id]
    $target = Join-Path $PkgDir "$id.$ver"
    $lid = $id.ToLower(); $lv = $ver.ToLower()
    # Keep the .nupkg inside the package folder, like NuGet does: some
    # Windows App SDK targets look for it to decide whether to run checks
    # that only apply to packages.config projects.
    $nupkg = Join-Path $target "$lid.$lv.nupkg"
    if ((Test-Path (Join-Path $target ".complete")) -and (Test-Path $nupkg)) { continue }
    $url = "$Feed/$lid/$lv/$lid.$lv.nupkg"
    $tmp = Join-Path $env:TEMP "$lid.$lv.zip"
    Write-Host "  downloading $id $ver"
    try { Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing }
    catch { throw "Download of $id $ver failed ($($_.Exception.Message))." }
    if (-not (Test-Path (Join-Path $target ".complete"))) {
        if (Test-Path $target) { Remove-Item $target -Recurse -Force }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($tmp, $target)
        New-Item -ItemType File -Path (Join-Path $target ".complete") | Out-Null
    }
    Move-Item $tmp $nupkg -Force
}

# ---------------------------------------------------------------- imports
function Find-BuildFile([string]$Dir, [string]$Id, [string]$Ext) {
    foreach ($sub in @("buildTransitive\native", "build\native", "buildTransitive", "build")) {
        $f = Join-Path $Dir (Join-Path $sub "$Id$Ext")
        if (Test-Path $f) { return $f }
    }
    return $null
}
$props = New-Object System.Text.StringBuilder
$targets = New-Object System.Text.StringBuilder
foreach ($id in $order) {
    $dir = Join-Path $PkgDir "$id.$($resolved[$id])"
    $p = Find-BuildFile $dir $id ".props"
    $t = Find-BuildFile $dir $id ".targets"
    $rel = { param($f) '$(MSBuildThisFileDirectory)..\' + $f.Substring($Desktop.Length + 1) }
    if ($p) { [void]$props.AppendLine("  <Import Project=`"$(& $rel $p)`" />") }
    if ($t) { [void]$targets.AppendLine("  <Import Project=`"$(& $rel $t)`" />") }
}
$header = "<?xml version=`"1.0`" encoding=`"utf-8`"?>`r`n<!-- Generated by scripts\restore-desktop.ps1. Do not edit. -->`r`n<Project xmlns=`"http://schemas.microsoft.com/developer/msbuild/2003`">`r`n"
Set-Content -Path (Join-Path $Desktop "PFI\Packages.g.props") -Encoding UTF8 -Value ($header + $props.ToString() + "</Project>")
Set-Content -Path (Join-Path $Desktop "PFI\Packages.g.targets") -Encoding UTF8 -Value ($header + $targets.ToString() + "</Project>")
Write-Host "Windows App SDK $($resolved['Microsoft.WindowsAppSDK']) ready ($($order.Count) packages)."
