<#
  CoatLink installer for Windows - PowerShell only, no bash, no git.

      .\install.ps1                      detect both halves and install
      .\install.ps1 -BlenderOnly         just the Blender add-on
      .\install.ps1 -CoatOnly            just the 3D-Coat half

      .\install.ps1 -BlenderAddons "C:\Users\you\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons" `
                    -CoatScripts  "C:\Users\you\Documents\3DCoat\UserPrefs\Scripts" `
                    -CoatDir      "D:\Program Files\3DCoat-2026"

  If Windows refuses to run the script, start it like this instead:

      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

  The Blender half is copied here.  The 3D-Coat half runs
  coat_side\CoatLinkInstall.py, which is the same code install.cmd, coat_side/install.sh
  and the single file in dist/ run - so the four of them cannot drift apart.  It
  writes the two XML files with this machine's paths and copies the button icons
  next to 3D-Coat's own when that folder is writable.
#>

[CmdletBinding()]
param(
    [string] $BlenderAddons,
    [string] $CoatScripts,
    [string] $CoatDir,
    [switch] $BlenderOnly,
    [switch] $CoatOnly,
    [switch] $Uninstall
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Newest {
    # newest path matching a wildcard, or $null
    param([string[]] $Patterns)
    foreach ($pattern in $Patterns) {
        $hits = @(Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
                  Sort-Object -Property Name | Select-Object -Last 1)
        if ($hits.Count -gt 0) { return $hits[0].FullName }
    }
    return $null
}

function Get-BlenderAddons {
    if ($BlenderAddons) { return $BlenderAddons }
    if ($env:BLENDER_ADDON_DIR) { return $env:BLENDER_ADDON_DIR }
    $root = if ($env:BLENDER_CONFIG_DIR) { $env:BLENDER_CONFIG_DIR }
            else { Join-Path $env:APPDATA 'Blender Foundation\Blender' }
    return Find-Newest @( (Join-Path $root '*\scripts\addons') )
}

function Get-CoatScripts {
    if ($CoatScripts) { return $CoatScripts }
    if ($env:COAT_SCRIPTS_DIR) { return $env:COAT_SCRIPTS_DIR }
    return (Join-Path $env:USERPROFILE 'Documents\3DCoat\UserPrefs\Scripts')
}

function Get-CoatDir {
    if ($CoatDir) { return $CoatDir }
    if ($env:COAT_DIR) { return $env:COAT_DIR }
    return Find-Newest @(
        'C:\Program Files\3DCoat*',
        'D:\Program Files\3DCoat*',
        'E:\Program Files\3DCoat*',
        'F:\Program Files\3DCoat*',
        'G:\Program Files\3DCoat*',
        'H:\Program Files\3DCoat*',
        'C:\Program Files (x86)\3DCoat*',
        (Join-Path $env:LOCALAPPDATA 'Programs\3DCoat*'),
        (Join-Path $env:LOCALAPPDATA '3DCoat*')
    )
}

function Get-CoatPython {
    # 3D-Coat ships its own Python folder: using it means nothing has to be installed
    if ($env:COATLINK_PYTHON -and (Test-Path $env:COATLINK_PYTHON)) { return $env:COATLINK_PYTHON }
    $bundled = Find-Newest @( (Join-Path $env:USERPROFILE 'Documents\3DCoat\python-*\python.exe') )
    if ($bundled) { return $bundled }
    foreach ($name in 'python', 'py', 'python3') {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

# ---- Blender half ----------------------------------------------------------
if (-not $CoatOnly) {
    $addons = Get-BlenderAddons
    if (-not $addons) {
        Write-Host 'Blender add-on folder not found - pass it explicitly:' -ForegroundColor Red
        Write-Host '  .\install.ps1 -BlenderAddons "$env:APPDATA\Blender Foundation\Blender\<version>\scripts\addons"'
        exit 1
    }
    $target = Join-Path $addons 'coat_bridge'
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $Repo 'coat_bridge\*') -Destination $target -Recurse -Force
    Get-ChildItem -Path $target -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "add-on : $target"
    Write-Host '         enable it in Edit > Preferences > Add-ons, then press Detect'
}

# ---- 3D-Coat half ----------------------------------------------------------
if (-not $BlenderOnly) {
    $scripts = Get-CoatScripts
    if (-not (Test-Path $scripts)) {
        Write-Host "no such scripts folder: $scripts" -ForegroundColor Red
        Write-Host 'Start 3D-Coat once so it creates its user folders, or pass -CoatScripts <path>.'
        exit 1
    }
    $installer = Join-Path $Repo 'coat_side\CoatLinkInstall.py'
    if (-not (Test-Path $installer)) {
        Write-Host "missing $installer - unzip the whole release, not just this file" -ForegroundColor Red
        exit 1
    }
    $python = Get-CoatPython
    if (-not $python) {
        Write-Host 'No Python found: start 3D-Coat once (it ships one), or install Python.' -ForegroundColor Red
        exit 1
    }
    $installerArgs = @($installer, '--scripts', $scripts)
    $coat = Get-CoatDir
    if ($coat) { $installerArgs += @('--coat', $coat) }
    if ($Uninstall) { $installerArgs += '--uninstall' }
    & $python @installerArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
