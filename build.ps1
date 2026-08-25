$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-Iscc {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 7\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

python installer\make_icon.py
python -m pip install -r requirements.txt

$pyiArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "RDPManager",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "build",
    "--hidden-import", "rdp_core"
)
if (Test-Path "assets\rdpmanager.ico") {
    $pyiArgs += @("--icon", (Resolve-Path "assets\rdpmanager.ico").Path)
}

Get-Process RDPManager -ErrorAction SilentlyContinue | Stop-Process -Force
python -m PyInstaller @pyiArgs main.py
Copy-Item -Force accounts.json dist\accounts.json
Write-Host "EXE: $PSScriptRoot\dist\RDPManager.exe"

$iscc = Get-Iscc
if (-not $iscc) {
    Write-Warning "Inno Setup не найден. Установщик не собран. Установите JRSoftware.InnoSetup и запустите build.ps1 снова."
    exit 0
}

& $iscc "installer\rdp_manager.iss"
Write-Host "Установщик: $PSScriptRoot\dist\OpenRPA_RDP_Manager_Setup.exe"
