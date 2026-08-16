# ============================================================
#  自动同步守护 - 股票分析 Agent
#  轮询工作区改动：检测到变化并度过静默期后，
#  自动 git add -A -> commit -> pull --rebase -> push
#
#  用法: powershell -ExecutionPolicy Bypass -File auto_sync.ps1
#  由 install_auto_sync.ps1 注册为开机自启（登录时运行，隐藏窗口）
#  日志: logs/auto_sync.log（已被 gitignore 排除，不会上传）
# ============================================================
param(
    [int]$PollSeconds = 30,    # 轮询间隔（秒）
    [int]$QuietSeconds = 60,   # 改动后需持续无新变化的静默期（秒），防止提交到一半的文件
    [string]$LogFile = "logs/auto_sync.log"
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logDir = Split-Path $LogFile -Parent
if ($logDir) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

function Write-Log([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
    Write-Host $line
}

Write-Log "自动同步守护已启动（轮询 ${PollSeconds}s / 静默 ${QuietSeconds}s）"

$lastChange = $null
while ($true) {
    try {
        $changed = @(git status --porcelain 2>$null)
        if ($changed.Count -gt 0) {
            if ($null -eq $lastChange) {
                $lastChange = Get-Date
                Write-Log "检测到 $($changed.Count) 个文件改动，进入静默期..."
            }
            elseif (((Get-Date) - $lastChange).TotalSeconds -ge $QuietSeconds) {
                $files = @($changed | ForEach-Object { ($_ -replace '^\s*\S+\s+', '').Trim('"') })
                $leafs = $files | ForEach-Object { Split-Path $_ -Leaf }
                $msg = "auto: " + (($leafs | Select-Object -First 5) -join ", ")
                if ($files.Count -gt 5) { $msg += " 等 $($files.Count) 个文件" }

                Write-Log ">>> 开始自动同步: $msg"
                git add -A 2>&1 | Out-Null
                $commitOut = (git commit -m $msg 2>&1 | Out-String).Trim()
                $commitExit = $LASTEXITCODE
                if ($commitExit -eq 0) {
                    Write-Log $commitOut
                    $pullOut = (git pull --rebase origin main 2>&1 | Out-String).Trim()
                    $pullExit = $LASTEXITCODE
                    if ($pullExit -eq 0) {
                        $pushOut = (git push origin main 2>&1 | Out-String).Trim()
                        $pushExit = $LASTEXITCODE
                        Write-Log $pushOut
                        if ($pushExit -eq 0) {
                            Write-Log "<<< 自动同步完成 [OK]"
                        } else {
                            Write-Log "<<< push 失败（可能远端有冲突），下次轮询将重试"
                        }
                    } else {
                        Write-Log "<<< pull --rebase 失败，可能存在冲突，已中止 rebase，请手动处理"
                        git rebase --abort 2>&1 | Out-Null
                    }
                } else {
                    Write-Log "无内容可提交（改动可能已被还原）"
                }
                $lastChange = $null
            }
        } else {
            $lastChange = $null
        }
    } catch {
        Write-Log "运行错误: $($_.Exception.Message)"
        $lastChange = $null
    }
    Start-Sleep -Seconds $PollSeconds
}
