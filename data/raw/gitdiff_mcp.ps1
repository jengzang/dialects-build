# ==========================================
# 终极版：原生 PowerShell 提取 (无乱码/无路径锁死)
# ==========================================

$RepoUrl = "https://github.com/osfans/MCPDict.git"
$TargetFolder = "tools/tables/output"
$OutputFolderName = "pull_yindian"
$TempGitDirName = ".git_cache" 
$CurrentDir = Get-Location

$FullCachePath = Join-Path -Path $CurrentDir -ChildPath $TempGitDirName
$FullOutputPath = Join-Path -Path $CurrentDir -ChildPath $OutputFolderName
$VersionFile = Join-Path $FullOutputPath ".last_commit"

try {
    # 统一双向 UTF-8 编码环境
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:LC_ALL = 'C.UTF-8'

    if (!(Test-Path -Path $FullCachePath)) {
        Write-Host "🚀 Initializing git cache..." -ForegroundColor Cyan
        git clone --filter=blob:none --no-checkout $RepoUrl $FullCachePath
    } 
    
    Set-Location $FullCachePath
    git config core.quotePath false
    if (Test-Path ".git/index.lock") { Remove-Item ".git/index.lock" -Force }

    git fetch origin master --quiet
    $LatestCommit = (git rev-parse origin/master).Trim()
    
    $LastCommit = $null
    if (Test-Path -Path $VersionFile) { $LastCommit = (Get-Content -Path $VersionFile -Raw).Trim() }

    if ($null -eq $LastCommit) {
        Write-Host "⚠️ Mode: Full Export" -ForegroundColor Yellow
        $FilesToExport = git ls-tree -r --name-only origin/master -- "$TargetFolder/*.tsv"
    } else {
        Write-Host "🔍 Diffing: $LastCommit -> $LatestCommit" -ForegroundColor Cyan
        $FilesToExport = git diff --name-only $LastCommit $LatestCommit -- "$TargetFolder/*.tsv"
    }

    if ($FilesToExport.Count -eq 0) {
        Write-Host "✅ All up to date." -ForegroundColor Green
    } else {
        Write-Host "🚚 Extracting $($FilesToExport.Count) files..." -ForegroundColor Yellow
        
        if (!(Test-Path -Path $FullOutputPath)) { New-Item -ItemType Directory -Path $FullOutputPath | Out-Null }
        Get-ChildItem -Path $FullOutputPath -Exclude ".last_commit" | Remove-Item -Force

        foreach ($RelativePath in $FilesToExport) {
            $FileName = [System.IO.Path]::GetFileName($RelativePath)
            $DestPath = Join-Path $FullOutputPath $FileName
            
            # --- 核心修复：使用 ${} 隔离变量，并用原生的 Out-File 保证 UTF-8 编码 ---
            git show "${LatestCommit}:${RelativePath}" | Out-File -FilePath $DestPath -Encoding utf8
            
            Write-Host "  [+] $FileName" -ForegroundColor Gray
        }

        $LatestCommit | Out-File -FilePath $VersionFile -Encoding ASCII
        Write-Host "✨ Done! Version updated to $($LatestCommit.Substring(0,7))" -ForegroundColor Green
    }
}
catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Set-Location $CurrentDir
}