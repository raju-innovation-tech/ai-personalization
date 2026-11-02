# One-time backend setup + start (run from the repo root, Docker Desktop must be running).
$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\backend"

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $secret = ([Convert]::ToBase64String($bytes)) -replace '[^A-Za-z0-9]', 'x'
    (Get-Content .env) -replace '^JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$secret" | Set-Content .env
    Write-Host "Created backend\.env with a fresh JWT secret."
}

docker compose up --build -d
Write-Host "Waiting for the API to become healthy..."
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-RestMethod http://localhost:8000/api/v1/health -TimeoutSec 2
        if ($r.success) { $ok = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) { Write-Host "API did not come up. Check: docker compose logs backend"; exit 1 }

docker compose exec backend python -m scripts.seed_data
Write-Host ""
Write-Host "Backend ready  -> http://localhost:8000/docs"
Write-Host "Login          -> admin@example.com / ChangeMe123!"
Write-Host "Demo staff     -> marketing@example.com, viewer@example.com (same password)"
Write-Host "More users     -> docker compose exec backend python -m scripts.create_user --help"
