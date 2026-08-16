# ============================================================
#  A 股股票分析 Agent - 新机器一键安装脚本
#  用法: powershell -ExecutionPolicy Bypass -File setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "===== A 股股票分析 Agent 安装 =====" -ForegroundColor Cyan
Write-Host ""

# [1/4] 检查 Python
Write-Host "[1/4] 检查 Python..." -ForegroundColor Cyan
$pyOut = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  未检测到 Python！请先安装 Python 3.12: https://www.python.org/downloads/ (勾选 Add to PATH)" -ForegroundColor Red
    exit 1
}
Write-Host "  $pyOut"

# [2/4] 创建虚拟环境
Write-Host "[2/4] 创建虚拟环境 .venv ..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "  创建 .venv 失败" -ForegroundColor Red; exit 1 }
    Write-Host "  .venv 已创建"
} else {
    Write-Host "  .venv 已存在，跳过"
}

$pip = ".venv\Scripts\python.exe -m pip"

# [3/4] 安装依赖
Write-Host "[3/4] 安装依赖（清华镜像）..." -ForegroundColor Cyan
& $pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
& $pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "  依赖安装失败，请检查网络后重试" -ForegroundColor Red
    exit 1
}
Write-Host "  依赖安装完成 [OK]"

# [4/4] 检查 API 密钥
Write-Host "[4/4] 检查 API 密钥 api.txt ..." -ForegroundColor Cyan
if (-not (Test-Path "api.txt")) {
    Write-Host "  未找到 api.txt（仅 TradingAgents AI 分析需要，可选）" -ForegroundColor Yellow
    Write-Host "  如需使用 AI 分析，请创建 api.txt 并写入 DeepSeek API Key" -ForegroundColor Yellow
} else {
    Write-Host "  api.txt 已存在 [OK]" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host " 安装完成！" -ForegroundColor Green
Write-Host " 1. 用 VS Code 打开本目录（.github/skills 会被 Copilot 自动识别）" -ForegroundColor Green
Write-Host " 2. 报告输出到 分析报告/，中间数据在 output/（均已被 gitignore 排除）" -ForegroundColor Green
Write-Host " 3. 每日更新推送: .\sync.ps1 \"更新说明\"" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
