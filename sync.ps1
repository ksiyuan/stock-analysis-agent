# ============================================================
#  本地更新推送到 GitHub
#  用法: .\sync.ps1 "更新说明"
#  说明: 自动 add 全部改动 -> commit -> push
# ============================================================
param([string]$message = "update")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

# 检查改动
$changed = git status --porcelain
if (-not $changed) {
    Write-Host "没有检测到改动，工作区已是最新。" -ForegroundColor Yellow
    exit 0
}

Write-Host "以下文件将被提交：" -ForegroundColor Cyan
git status --short
Write-Host ""

git add -A
git commit -m $message

Write-Host "正在推送到 GitHub ..."
git push

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "已推送到 GitHub [OK]" -ForegroundColor Green
    Write-Host "新机器上拉取: git pull" -ForegroundColor Green
}
