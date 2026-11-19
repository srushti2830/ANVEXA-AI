$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$quietPeriodSeconds = 4
$pollIntervalSeconds = 2
$pushRetrySeconds = 30
$lastStatus = $null
$lastChangeAt = Get-Date
$lastPushAttempt = [datetime]::MinValue

Write-Host "Auto-sync is watching $repoRoot"

while ($true) {
    $statusOutput = & git status --porcelain --untracked-files=all 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Auto-sync could not read Git status: $($statusOutput -join ' ')"
        Start-Sleep -Seconds $pollIntervalSeconds
        continue
    }

    $status = $statusOutput -join "`n"
    if ($status -ne $lastStatus) {
        $lastStatus = $status
        $lastChangeAt = Get-Date
        if (-not [string]::IsNullOrWhiteSpace($status)) {
            Write-Host "Changes detected; waiting for edits to settle."
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($status) -and
        ((Get-Date) - $lastChangeAt).TotalSeconds -ge $quietPeriodSeconds) {
        $addOutput = & git add --all 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Auto-sync could not stage changes: $($addOutput -join ' ')"
            $lastChangeAt = Get-Date
            Start-Sleep -Seconds $pollIntervalSeconds
            continue
        }

        $stagedStatus = & git status --porcelain --untracked-files=all 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Auto-sync could not verify staged changes: $($stagedStatus -join ' ')"
            $lastChangeAt = Get-Date
            Start-Sleep -Seconds $pollIntervalSeconds
            continue
        }

        if (-not [string]::IsNullOrWhiteSpace(($stagedStatus -join "`n"))) {
            $commitOutput = & git commit -m "Auto-sync local changes" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Committed local changes."
                $lastStatus = $null
                $lastPushAttempt = [datetime]::MinValue
            }
            else {
                Write-Host "Auto-sync could not commit changes: $($commitOutput -join ' ')"
                $lastChangeAt = Get-Date
            }
        }
        else {
            $lastStatus = $null
        }
    }

    $head = & git rev-parse --quiet --verify HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and
        ((Get-Date) - $lastPushAttempt).TotalSeconds -ge $pushRetrySeconds) {
        $lastPushAttempt = Get-Date
        $pushOutput = & git push --set-upstream origin HEAD 2>&1
        if ($LASTEXITCODE -eq 0) {
            if ($pushOutput) {
                Write-Host ($pushOutput -join "`n")
            }
        }
        else {
            Write-Host "Auto-sync could not push to origin; it will retry: $($pushOutput -join ' ')"
        }
    }

    Start-Sleep -Seconds $pollIntervalSeconds
}
