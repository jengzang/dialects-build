# ==========================================
# 稳定版：提取文件并保存至 /pull_yindian
# ==========================================

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/osfans/MCPDict.git"
$TargetFolder = "tools/tables/output"
$OutputFolderName = "pull_yindian"
$TempDir = "temp_git_dl_$(Get-Random)" 
$CurrentDir = Get-Location
$FullOutputPath = Join-Path -Path $CurrentDir -ChildPath $OutputFolderName

Write-Host "🚀 开始标准克隆 (利用 GitHub 预打包缓存)..." -ForegroundColor Cyan

try {
    # 1. 确保目标文件夹存在
    if (!(Test-Path -Path $FullOutputPath)) {
        New-Item -ItemType Directory -Path $FullOutputPath | Out-Null
        Write-Host "📂 已创建目标目录: $OutputFolderName" -ForegroundColor Gray
    }

    # 2. 完整克隆
    git clone $RepoUrl $TempDir
    
    # 3. 提取文件到指定目录
    Write-Host "🚚 克隆完成！正在将文件释放至 $OutputFolderName ..." -ForegroundColor Yellow
    # 使用 Copy-Item 后接 Remove-Item 以确保跨盘符或特殊权限下的稳定性，或直接 Move-Item
    Get-ChildItem -Path "$TempDir/$TargetFolder/*" | Move-Item -Destination $FullOutputPath -Force
    
    # 4. 销毁临时文件夹
    Write-Host "🧹 正在清理临时文件..." -ForegroundColor Yellow
    Remove-Item -Path $TempDir -Recurse -Force
    
    Write-Host "✅ 搞定！你要的表格文件已全部存入: $FullOutputPath" -ForegroundColor Green
}
catch {
    Write-Host "❌ 发生错误：" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    # 发生错误时尝试清理临时目录
    if (Test-Path -Path $TempDir) { Remove-Item -Path $TempDir -Recurse -Force }
}