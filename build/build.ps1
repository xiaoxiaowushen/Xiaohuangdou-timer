# WinTimer 打包脚本
#   用法： pwsh -File build\build.ps1              # 只出绿色单文件 exe
#          pwsh -File build\build.ps1 -Installer   # 同时出安装包
#          pwsh -File build\build.ps1 -SkipTests
param(
    [switch]$SkipTests,
    [switch]$Installer
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 本机 PyInstaller 装在 .pylibs（pip 被沙箱挡住，用 tools\fetch_pyinstaller.py 抓的）
$env:PYTHONPATH = "$root\.pylibs"
$env:TEMP = "$root\.tmp"
$env:TMP = "$root\.tmp"
New-Item -ItemType Directory -Force -Path "$root\.tmp" | Out-Null

Write-Host "[1/4] 生成图标" -ForegroundColor Cyan
python tools\make_icon.py

if (-not $SkipTests) {
    Write-Host "[2/4] 逻辑自检" -ForegroundColor Cyan
    python tools\selftest.py
    if ($LASTEXITCODE -ne 0) { throw "自检未通过，已中止打包" }
} else {
    Write-Host "[2/4] 跳过自检" -ForegroundColor DarkGray
}

Write-Host "[3/4] 打包主程序（单文件）" -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean build\WinTimer.spec
if ($LASTEXITCODE -ne 0) { throw "主程序打包失败" }

if ($Installer) {
    Write-Host "[4/4] 打包安装程序" -ForegroundColor Cyan
    python -m PyInstaller --noconfirm --clean build\Setup.spec
    if ($LASTEXITCODE -ne 0) { throw "安装程序打包失败" }
} else {
    Write-Host "[4/4] 跳过安装程序（加 -Installer 生成）" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "产物：" -ForegroundColor Green
Get-ChildItem dist -File | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize
