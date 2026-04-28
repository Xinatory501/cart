# Скрипт автоматической пересборки Docker при изменениях

$lastHash = ""

function Get-ProjectHash {
    $files = Get-ChildItem -Path . -Recurse -Include *.py,*.json,*.txt,Dockerfile,docker-compose.yml -File
    $content = $files | ForEach-Object { Get-Content $_.FullName -Raw } | Out-String
    return [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($content)))
}

Write-Host "Мониторинг изменений проекта..." -ForegroundColor Green

while ($true) {
    $currentHash = Get-ProjectHash

    if ($lastHash -ne "" -and $currentHash -ne $lastHash) {
        Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] Обнаружены изменения! Пересборка..." -ForegroundColor Yellow

        docker compose down
        docker compose build --no-cache
        docker system prune -f
        docker compose up -d

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Пересборка завершена`n" -ForegroundColor Green
    }

    $lastHash = $currentHash
    Start-Sleep -Seconds 3
}
