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

  What it does: copies the add-on, copies the 3D-Coat scripts, writes the two
  XML files that give 3D-Coat its menu entry and tool buttons, and copies the
  button icons next to 3D-Coat's own.  The same six files, the same two XML
  files and the same icons the bash installer writes - byte for byte.
#>

[CmdletBinding()]
param(
    [string] $BlenderAddons,
    [string] $CoatScripts,
    [string] $CoatDir,
    [switch] $BlenderOnly,
    [switch] $CoatOnly
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-TextLf {
    # LF only, no BOM: 3D-Coat reads these files and the bash installer writes LF
    param([string] $Path, [string] $Text)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, ($Text -replace "`r`n", "`n"), $utf8)
}

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
        'C:\Program Files (x86)\3DCoat*',
        (Join-Path $env:LOCALAPPDATA 'Programs\3DCoat*'),
        (Join-Path $env:LOCALAPPDATA '3DCoat*')
    )
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
    $coat = Get-CoatDir

    $dir = Join-Path $scripts 'CoatBridge'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    foreach ($stale in 'CoatBridge.py', 'CoatBridgeQt.py', 'CoatBridgeDialog.py') {
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $dir $stale)
    }
    foreach ($name in 'CoatBridgeLib.py', 'CoatBridgeReceipts.py', 'CoatBridgeScopedExport.py',
                      'CoatBridge_Send.py', 'CoatBridge_Pull.py', 'CoatBridge_Setup.py') {
        Copy-Item -Force (Join-Path $Repo "coat_side\$name") (Join-Path $dir $name)
    }
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $dir '__pycache__')

    # 3D-Coat reads Windows paths in the XML; forward slashes, like the bash side
    $winDir = $dir.Replace('\', '/')

    $menuDir = Join-Path $scripts 'ExtraMenuItems'
    New-Item -ItemType Directory -Force -Path $menuDir | Out-Null

    $tools = Get-Content -Raw (Join-Path $Repo 'coat_side\tools\CoatBridgeTools.xml.in')
    Write-TextLf (Join-Path $menuDir 'CoatBridgeTools.xml') ($tools.Replace('__SCRIPT_DIR__', $winDir))

    $menu = @"
<ClassArray.ExtraMenuItem>
`t<ExtraMenuItem>
`t`t<MenuPath>Scripts</MenuPath>
`t`t<MenuItem>CoatBridge</MenuItem>
`t`t<inRoom></inRoom>
`t`t<inSection></inSection>
`t`t<Command>script:$winDir/CoatBridge_Setup.py</Command>
`t</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
"@
    Write-TextLf (Join-Path $menuDir 'CoatBridge.xml') ($menu + "`n")

    if ($coat) {
        $iconDir = Join-Path $coat 'data\Textures\icons64'
        if (Test-Path $iconDir) {
            foreach ($icon in 'CoatBridge.png', 'CoatBridge_Send.png', 'CoatBridge_Pull.png', 'CoatBridge_Setup.png') {
                Copy-Item -Force (Join-Path $Repo "coat_side\icon\$icon") (Join-Path $iconDir $icon) -ErrorAction SilentlyContinue
            }
            Write-Host "icons  : $iconDir\CoatBridge_*.png"
        } else {
            Write-Warning "icons  : skipped, no such folder: $iconDir"
        }
    } else {
        Write-Warning 'icons  : skipped, the 3D-Coat program folder was not found (pass -CoatDir)'
    }

    Write-Host "scripts: $dir"
    Write-Host "buttons: $menuDir\CoatBridgeTools.xml  (Voxels + Paint tool panels)"
    Write-Host "menu   : $menuDir\CoatBridge.xml  (Scripts > CoatLink: opens the panel)"
    Write-Host ''
    Write-Host 'Restart 3D-Coat, then look at the end of the tool list in the Sculpt room.'
}
