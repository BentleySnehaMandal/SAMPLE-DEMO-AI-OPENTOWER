#!/usr/bin/env pwsh
# Start frontend dev server
Set-Location $PSScriptRoot\frontend
Write-Host "Starting Tower AI Frontend on http://localhost:5173" -ForegroundColor Green
npm run dev
