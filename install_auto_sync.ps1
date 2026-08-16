# ============================================================
#  注册「自动同步」为开机自启（登录时启动，隐藏窗口）
#  使用 Windows 启动文件夹（%APPDATA%\...\Startup），无需管理员权限
#  用法:
#     .\install_auto_sync.ps1             # 注册并立即启动
#     .\install_auto_sync.ps1 -Uninstall  # 取消自动同步
# ============================================================
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = "StockAgentAutoSync"
$script = Join-Path $root "auto_sync.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startupDir "$taskName.lnk"

if ($Uninstall) {
    # 停止正在运行的守护进程
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*auto_sync.ps1*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Remove-Item $lnk -Force -ErrorAction SilentlyContinue
    Write-Host "已取消自动同步（$taskName）" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $script)) {
    Write-Host "未找到 auto_sync.ps1" -ForegroundColor Red
    exit 1
}

# 创建启动文件夹快捷方式（开机自启，无需管理员权限）
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = "powershell.exe"
$sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$sc.WorkingDirectory = $root
$sc.WindowStyle = 7
$sc.Description = "股票分析 Agent 自动同步到 GitHub"
$sc.Save()

Write-Host "已注册开机自启: $taskName.lnk" -ForegroundColor Green
Write-Host "  位置: $startupDir" -ForegroundColor Green
Write-Host "  日志: logs/auto_sync.log" -ForegroundColor Green
Write-Host "如需取消: .\install_auto_sync.ps1 -Uninstall" -ForegroundColor Yellow

# 立即启动守护（隐藏窗口）
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -WindowStyle Hidden
Write-Host "自动同步守护已启动 [OK]" -ForegroundColor Green
