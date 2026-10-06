$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installRoot = Join-Path $env:LOCALAPPDATA "DouyinRAG"
$taskName = "Douyin RAG Image Deployment"

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot "docker-compose.yml") -Destination $installRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "deploy-local.ps1") -Destination $installRoot -Force

$exampleEnv = Join-Path $repoRoot ".env.deploy.example"
$localEnv = Join-Path $installRoot ".env"
if (-not (Test-Path -LiteralPath $localEnv)) {
    Copy-Item -LiteralPath $exampleEnv -Destination $localEnv
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$localScript = Join-Path $installRoot "deploy-local.ps1"
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$localScript`""

$action = New-ScheduledTaskAction -Execute $powershellExe -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Write-Host "本机镜像轮询任务已启动：$taskName"
Write-Host "配置文件：$localEnv"
Write-Host "日志文件：$(Join-Path $installRoot 'deploy.log')"
