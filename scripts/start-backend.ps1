<#
.SYNOPSIS
    一键启动后端服务（本地开发模式）

.DESCRIPTION
    自动读取 docker/env/.env.dev 中的环境变量，并针对本地启动做必要的覆盖：
      - MYSQL_HOST / QDRANT_HOST 从容器内主机名改为 127.0.0.1
      - MYSQL_PORT 改用宿主机映射端口（MYSQL_HOST_PORT）
      - OLLAMA_BASE_URL 改用 http://localhost:OLLAMA_PORT（本地模式）

.PARAMETER EnvFile
    指定环境变量文件路径，默认为 docker/env/.env.dev

.EXAMPLE
    .\scripts\start-backend.ps1
    .\scripts\start-backend.ps1 ..\docker\env\.env.prod
#>

param(
    [string]$EnvFile = ""
)

# 定位项目根目录（脚本所在目录的父目录）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "backend"

# 确定环境变量文件
if ([string]::IsNullOrEmpty($EnvFile)) {
    $EnvFile = Join-Path $ProjectRoot "docker\env\.env.dev"
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "[错误] 环境变量文件不存在: $EnvFile" -ForegroundColor Red
    Write-Host "请先复制模板: cp docker/env/.env.dev.example docker/env/.env.dev" -ForegroundColor Yellow
    exit 1
}

Write-Host "[信息] 读取环境变量文件: $EnvFile" -ForegroundColor Cyan

# 读取并解析 env 文件（跳过空行、注释行、去除引号）
# 注意：必须显式指定 UTF8，否则 PS5.1 按 GBK 读取中文注释会吞掉换行符导致行合并
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ([string]::IsNullOrEmpty($line) -or $line.StartsWith("#")) { return }

    $idx = $line.IndexOf("=")
    if ($idx -gt 0) {
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        # 去除首尾双引号
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "env:$key" -Value $value
    }
}

# ---------- 本地启动覆盖 ----------
# 容器内用服务名（mysql/qdrant/ollama）互访，本地直连需改为宿主机地址
$env:MYSQL_HOST = "127.0.0.1"
$env:QDRANT_HOST = "127.0.0.1"

# MySQL 容器内监听 3306，但映射到宿主机的端口是 MYSQL_HOST_PORT
if (-not [string]::IsNullOrEmpty($env:MYSQL_HOST_PORT)) {
    $env:MYSQL_PORT = $env:MYSQL_HOST_PORT
}

# Ollama 容器内监听 11434，映射到宿主机的端口是 OLLAMA_PORT
if (-not [string]::IsNullOrEmpty($env:OLLAMA_PORT)) {
    $env:OLLAMA_BASE_URL = "http://localhost:$($env:OLLAMA_PORT)"
}

Write-Host "[信息] MySQL  连接: $($env:MYSQL_HOST):$($env:MYSQL_PORT)" -ForegroundColor Cyan
Write-Host "[信息] Qdrant 连接: $($env:QDRANT_HOST):$($env:QDRANT_PORT)" -ForegroundColor Cyan
Write-Host "[信息] 模型模式: $($env:MODEL_MODE)" -ForegroundColor Cyan
if ($env:MODEL_MODE -eq "local") {
    Write-Host "[信息] Ollama 地址: $($env:OLLAMA_BASE_URL)" -ForegroundColor Cyan
}

# 进入 backend 目录并启动
Set-Location $BackendDir
Write-Host "[启动] uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Gray

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
