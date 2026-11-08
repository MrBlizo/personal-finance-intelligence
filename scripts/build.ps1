<#
.SYNOPSIS
    Builds Personal Finance Intelligence: PFI.exe (WinUI 3) + backend +
    screens + bundled PostgreSQL, tests it, and creates PFI-Setup.exe.

.DESCRIPTION
    Steps: preflight -> Python env -> backend tests -> Next.js build ->
    PyInstaller -> WinUI 3 build -> stage dist\PFI -> smoke test ->
    Inno Setup. Progress is written to dist\build.log and the result to
    dist\build-status.txt. Your own data is never touched: the smoke test
    uses a throw-away folder dist\smoke-data.

.EXAMPLE
    build.bat                 (double-click, or run from a terminal)
    build.bat -SkipTests      (faster rebuild)
    build.bat -DebugBuild          (Debug build of PFI.exe, no installer)
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$DebugBuild,
    [string]$Version = "0.2.0"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Stage = Join-Path $Dist "PFI"
$Log = Join-Path $Dist "build.log"
$StatusFile = Join-Path $Dist "build-status.txt"
$Config = if ($DebugBuild) { "Debug" } else { "Release" }
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Set-Content -Path $Log -Value "PFI build $Version started $(Get-Date -Format s)" -Encoding UTF8

function Status([string]$text) { Set-Content -Path $StatusFile -Value $text -Encoding UTF8 }
function Say([string]$text) {
    Write-Host $text -ForegroundColor Cyan
    Add-Content -Path $Log -Value "`r`n=== $text ($(Get-Date -Format HH:mm:ss)) ===" -Encoding UTF8
    Status "RUNNING: $text"
}
function Fail([string]$text) {
    Add-Content -Path $Log -Value "`r`nBUILD FAILED: $text" -Encoding UTF8
    Status "FAILED: $text"
    Write-Host "`nBUILD FAILED: $text" -ForegroundColor Red
    Write-Host "Full log: $Log"
    exit 1
}
# Runs a command line through cmd.exe, appending all output to the log.
# -Robocopy: robocopy exit codes below 8 mean success.
function Run([string]$CommandLine, [string]$WorkDir = $Root, [string]$What = "", [switch]$Robocopy) {
    $tmp = Join-Path $env:TEMP ("pfi-step-" + [guid]::NewGuid().ToString("N") + ".cmd")
    $check = if ($Robocopy) { "if errorlevel 8 exit /b 1`r`nexit /b 0" } else { "exit /b %ERRORLEVEL%" }
    Set-Content -Path $tmp -Encoding Default -Value "@echo off`r`nchcp 65001 >nul`r`ncd /d `"$WorkDir`"`r`n$CommandLine >> `"$Log`" 2>&1`r`n$check"
    # Wait for cmd.exe itself only. (Start-Process -Wait also waits for every
    # descendant, e.g. MSBuild worker nodes or mspdbsrv.exe, which can linger
    # for many minutes after the build has finished.)
    $p = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$tmp`"" -NoNewWindow -PassThru
    $null = $p.Handle
    $p.WaitForExit()
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) {
        $tail = (Get-Content $Log -Tail 25) -join "`r`n"
        Write-Host $tail
        Fail "$What failed (exit code $($p.ExitCode)). See the end of dist\build.log."
    }
}

try {
# ------------------------------------------------------------- preflight
Say "1/9 Checking tools"
$conda = @("$env:USERPROFILE\miniconda3\Scripts\conda.exe", "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
           "$env:ProgramData\miniconda3\Scripts\conda.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $conda) { $c = Get-Command conda.exe -ErrorAction SilentlyContinue; if ($c) { $conda = $c.Source } }
if (-not $conda) { Fail "Miniconda was not found. Install it from https://docs.conda.io/en/latest/miniconda.html and run build.bat again." }
$condaBase = Split-Path -Parent (Split-Path -Parent $conda)
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) { Fail "Node.js (npm) was not found. Install Node.js LTS from https://nodejs.org and run build.bat again." }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { Fail "Visual Studio was not found (vswhere.exe missing). Install Visual Studio 2026 with C++ and WinUI workloads." }
$vsPath = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -property installationPath
$msbuild = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe" | Select-Object -First 1
if (-not $msbuild) { Fail "MSBuild was not found. In Visual Studio Installer add 'Desktop development with C++'." }
$pgRoot = Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "bin\pg_ctl.exe") } |
    Sort-Object { [int]($_.Name -replace '\D', '') } | Select-Object -Last 1
if (-not $pgRoot) { Fail "PostgreSQL was not found in $env:ProgramFiles\PostgreSQL. Install PostgreSQL (EDB installer) and run build.bat again." }
$iscc = @("$env:ProgramFiles\Inno Setup 7\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc -and -not $SkipInstaller -and -not $DebugBuild) { Fail "Inno Setup was not found. Install it from https://jrsoftware.org/isinfo.php or run build.bat -SkipInstaller." }
$crt = Get-ChildItem (Join-Path $vsPath "VC\Redist\MSVC") -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name | ForEach-Object { Get-ChildItem (Join-Path $_.FullName "x64") -Directory -Filter "Microsoft.VC*.CRT" -ErrorAction SilentlyContinue } |
    Select-Object -Last 1
Add-Content $Log -Encoding UTF8 -Value "conda=$conda`r`nnpm=$npm`r`nmsbuild=$msbuild`r`npostgres=$($pgRoot.FullName)`r`niscc=$iscc`r`ncrt=$($crt.FullName)"

# ---------------------------------------------------------- python env
Say "2/9 Python environment (conda env 'pfi')"
$py = Join-Path $condaBase "envs\pfi\python.exe"
$yml = Join-Path $Root "backend\environment.yml"
$hashFile = Join-Path $Dist ".env-hash"
$hash = (Get-FileHash $yml -Algorithm SHA256).Hash
# Packages come from conda-forge only (--override-channels): this avoids the
# Anaconda "defaults" channels and their Terms-of-Service prompt.
$specs = @(); $pipSpecs = @(); $inDeps = $false
foreach ($line in (Get-Content $yml)) {
    if ($line -match '^dependencies:') { $inDeps = $true; continue }
    if (-not $inDeps) { continue }
    if ($line -match '^  - (?!pip)([^\s#][^#]*?)\s*$') { $specs += '"' + $Matches[1] + '"' }
    elseif ($line -match '^      - ([^\s#][^#]*?)\s*$') { $pipSpecs += '"' + $Matches[1] + '"' }
}
$specs = ($specs + '"pip"') -join " "
if (-not (Test-Path $py)) {
    Run "`"$conda`" create -y -n pfi --override-channels -c conda-forge $specs" $Root "Creating the conda environment"
    Run "`"$py`" -m pip install $($pipSpecs -join ' ')" $Root "Installing pip packages"
} elseif (-not (Test-Path $hashFile) -or (Get-Content $hashFile) -ne $hash) {
    Run "`"$conda`" install -y -n pfi --override-channels -c conda-forge $specs" $Root "Updating the conda environment"
    Run "`"$py`" -m pip install $($pipSpecs -join ' ')" $Root "Installing pip packages"
}
Set-Content $hashFile $hash

# ------------------------------------------------------------ backend tests
if (-not $SkipTests) {
    Say "3/9 Backend tests (real PostgreSQL $($pgRoot.Name))"
    $env:PFI_TEST_PG_BIN = Join-Path $pgRoot.FullName "bin"
    Run "`"$py`" -m pytest -q -p no:cacheprovider tests" (Join-Path $Root "backend") "Backend tests"
} else { Say "3/9 Backend tests skipped" }

# ---------------------------------------------------------------- frontend
Say "4/9 Building the screens (Next.js)"
$fe = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $fe "node_modules\next"))) {
    Run "`"$npm`" ci --no-audit --no-fund" $fe "npm install"
}
Run "`"$npm`" run build" $fe "Next.js build"

# ---------------------------------------------------------------- backend exe
Say "5/9 Packaging the backend (PyInstaller)"
$be = Join-Path $Root "backend"
Run "`"$py`" -m PyInstaller --noconfirm --clean --log-level WARN pfi-api.spec" $be "PyInstaller"

# ---------------------------------------------------------------- desktop
Say "6/9 Building PFI.exe (WinUI 3, $Config)"
Run "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\restore-desktop.ps1`"" $Root "Downloading the Windows App SDK packages"
$sln = Join-Path $Root "desktop\PFI.sln"
Run "`"$msbuild`" `"$sln`" /t:Build /p:Configuration=$Config /p:Platform=x64 /m /nodeReuse:false /nologo /v:minimal /bl:`"$Dist\desktop.binlog`"" $Root "MSBuild of PFI.exe"
$exe = Get-ChildItem (Join-Path $Root "desktop\x64\$Config") -Recurse -Filter "PFI.exe" | Select-Object -First 1
if (-not $exe) { Fail "MSBuild finished but PFI.exe was not found under desktop\x64\$Config." }

# ---------------------------------------------------------------- stage
Say "7/9 Assembling dist\PFI"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Run "robocopy `"$($exe.DirectoryName)`" `"$Stage`" /E /XF *.pdb *.lib *.exp *.ilk pfi.ini /XD AppX /NFL /NDL /NJH /NJS" $Root "Copying PFI.exe" -Robocopy
Run "robocopy `"$be\dist\pfi-api`" `"$Stage\backend`" /E /NFL /NDL /NJH /NJS" $Root "Copying backend" -Robocopy
Run "robocopy `"$fe\out`" `"$Stage\web`" /E /NFL /NDL /NJH /NJS" $Root "Copying screens" -Robocopy
Run "robocopy `"$($pgRoot.FullName)`" `"$Stage\pgsql`" /E /XD doc include symbols `"pgAdmin 4`" StackBuilder installer scripts data /XF *.pdb /NFL /NDL /NJH /NJS" $Root "Copying PostgreSQL" -Robocopy
if ($crt) {
    foreach ($dest in @($Stage, (Join-Path $Stage "pgsql\bin"))) {
        Get-ChildItem $crt.FullName -Filter *.dll | ForEach-Object {
            if (-not (Test-Path (Join-Path $dest $_.Name))) { Copy-Item $_.FullName $dest }
        }
    }
}
Copy-Item (Join-Path $Root "desktop\PFI\Assets\pfi.ico") $Stage -Force
$size = "{0:N0} MB" -f ((Get-ChildItem $Stage -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Add-Content $Log -Encoding UTF8 -Value "Staged size: $size"

# ---------------------------------------------------------------- smoke test
Say "8/9 Smoke test of the packaged backend"
$smoke = Join-Path $Dist "smoke-data"
if (Test-Path $smoke) { Remove-Item $smoke -Recurse -Force }
$token = [guid]::NewGuid().ToString("N")
$port = 8799
$env:PFI_PG_BIN = Join-Path $Stage "pgsql\bin"; $env:PFI_DATA_DIR = $smoke
$env:PFI_FRONTEND_DIST = Join-Path $Stage "web"; $env:PFI_API_TOKEN = $token; $env:PFI_PG_PORT = "54398"
$proc = Start-Process -FilePath (Join-Path $Stage "backend\pfi-api.exe") -ArgumentList "--port $port --log-file `"$smoke\logs\api.log`"" `
    -WindowStyle Hidden -PassThru
$h = @{ "X-PFI-Token" = $token }; $base = "http://127.0.0.1:$port"; $ok = $false
for ($i = 0; $i -lt 180 -and -not $proc.HasExited; $i++) {
    try { Invoke-RestMethod "$base/api/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ok) {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    if (Test-Path "$smoke\logs\api.log") { Get-Content "$smoke\logs\api.log" -Tail 40 | Add-Content $Log }
    Fail "The packaged backend did not start (see the api.log lines above in dist\build.log)."
}
$results = @()
try {
    $demo = Invoke-RestMethod "$base/api/demo" -Method Post -Headers $h
    $results += "demo: $($demo.transactions) transactions"
    $dash = Invoke-RestMethod "$base/api/analytics/dashboard" -Headers $h
    $results += "dashboard: net worth $([math]::Round($dash.summary.net_worth, 2)) $($dash.summary.currency)"
    $fc = Invoke-RestMethod "$base/api/forecast" -Headers $h
    $results += "forecast: $($fc.dates.Count) days"
    $ui = Invoke-WebRequest "$base/forecast/" -UseBasicParsing
    $results += "ui: HTTP $($ui.StatusCode)"
    $js = [regex]::Match($ui.Content, '/_next/static/[^"]+\.js').Value
    if (-not $js) { throw "No script tag found in the UI page." }
    $asset = Invoke-WebRequest "$base$js" -UseBasicParsing
    $ctype = $asset.Headers["Content-Type"]
    $results += "ui script: $js -> $ctype"
    if ($ctype -notmatch "javascript") { throw "UI scripts are served as '$ctype' instead of JavaScript; the app window would stay blank." }
    try { Invoke-RestMethod "$base/api/settings" | Out-Null; throw "API answered without the token" } catch { if ($_.Exception.Message -like "*without the token*") { throw } }
    $results += "token check: ok"
} catch {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Fail "Smoke test request failed: $($_.Exception.Message)"
}
Invoke-RestMethod "$base/api/system/shutdown" -Method Post -Headers $h | Out-Null
if (-not $proc.WaitForExit(30000)) { Stop-Process -Id $proc.Id -Force; Fail "Backend did not stop within 30 s after shutdown." }
Remove-Item Env:PFI_PG_BIN, Env:PFI_DATA_DIR, Env:PFI_FRONTEND_DIST, Env:PFI_API_TOKEN, Env:PFI_PG_PORT
$results | ForEach-Object { Write-Host "  $_"; Add-Content $Log -Encoding UTF8 -Value "  $_" }

# ---------------------------------------------------------------- installer
if (-not $SkipInstaller -and -not $DebugBuild) {
    Say "9/9 Creating the installer (Inno Setup)"
    $iss = Join-Path $Root "installer\PFI.iss"
    Run "`"$iscc`" /Q /DAppVersion=$Version /DSourceDir=`"$Stage`" /DOutputDir=`"$Dist`" `"$iss`"" $Root "Inno Setup"
    $setup = Join-Path $Dist "PFI-Setup-$Version.exe"
    Status "SUCCESS: $setup ($size installed)"
    Write-Host "`nDone: $setup" -ForegroundColor Green
} else {
    Status "SUCCESS: $Stage\PFI.exe ($size)"
    Write-Host "`nDone: $Stage\PFI.exe" -ForegroundColor Green
}
} catch {
    Fail "Unexpected error: $($_.Exception.Message) at line $($_.InvocationInfo.ScriptLineNumber)"
}
