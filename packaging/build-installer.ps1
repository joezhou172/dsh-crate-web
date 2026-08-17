# 构建 DSH Crate Web 本地离线安装器（单文件 EXE）。
# 用法：在 packaging 目录执行  .\build-installer.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$package = Get-Content (Join-Path $root "package.json") -Raw | ConvertFrom-Json
$version = $package.version
$payload = Join-Path $PSScriptRoot "payload"
$dist = Join-Path $PSScriptRoot "dist"
New-Item -ItemType Directory -Force -Path $payload, $dist | Out-Null

Write-Host "==> npm pack (生成插件 tgz)" -ForegroundColor Cyan
Push-Location $root
try { npm pack --pack-destination $payload | Out-Host } finally { Pop-Location }

$tgz = Get-ChildItem -Path (Join-Path $payload "*.tgz") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $tgz) { throw "未生成 tgz" }
Write-Host "==> 使用安装包: $($tgz.FullName)" -ForegroundColor Cyan

$nsis = "C:\path\to\nsis\makensis.exe"
if (-not (Test-Path $nsis)) { throw "未找到 NSIS: $nsis" }

Push-Location $PSScriptRoot
try {
  & $nsis "/DVERSION=$version" "/DCRATE_TGZ=$($tgz.FullName)" "dsh-crate-web-installer.nsi"
  if ($LASTEXITCODE -ne 0) { throw "makensis 失败 (exit=$LASTEXITCODE)" }
} finally { Pop-Location }

$exe = Join-Path $dist "dsh-crate-web-installer-$version.exe"
Write-Host ""
Write-Host "==> 构建完成: $exe" -ForegroundColor Green
Write-Host "    大小: $((Get-Item $exe).Length / 1MB) MB (完全本地，不联网)"
