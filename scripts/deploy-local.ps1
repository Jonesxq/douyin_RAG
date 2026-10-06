$ErrorActionPreference = "Stop"

$installRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $installRoot "docker-compose.yml"
$logFile = Join-Path $installRoot "deploy.log"
$composeBaseArgs = @(
    "--project-name", "douyin-rag",
    "--project-directory", $installRoot,
    "-f", $composeFile
)

function Write-DeployLog {
    param([string]$Message)

    if (Test-Path -LiteralPath $logFile) {
        $existingLog = Get-Item -LiteralPath $logFile
        if ($existingLog.Length -gt 5MB) {
            Move-Item -LiteralPath $logFile -Destination "$logFile.previous" -Force
        }
    }

    $line = "{0:u} {1}" -f (Get-Date), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Invoke-DockerCompose {
    param([string[]]$ComposeArguments)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 maps native stderr output into PowerShell error records.
        # Compose writes normal pull progress to stderr, so keep it non-terminating here.
        $ErrorActionPreference = "Continue"
        $output = & docker compose @composeBaseArgs @ComposeArguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($line in $output) {
        Write-DeployLog ([string]$line)
    }

    if ($exitCode -ne 0) {
        throw "docker compose $($ComposeArguments -join ' ') exited with code $exitCode"
    }
}

$env:IMAGE_TAG = "latest"

while ($true) {
    try {
        Invoke-DockerCompose -ComposeArguments @("pull")
        Invoke-DockerCompose -ComposeArguments @("up", "-d", "--remove-orphans")

        Write-DeployLog "Image check and deployment completed."
    }
    catch {
        Write-DeployLog "Deployment check failed: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 300
}
