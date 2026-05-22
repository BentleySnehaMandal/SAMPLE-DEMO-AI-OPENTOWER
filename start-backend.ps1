#!/usr/bin/env pwsh
# Start backend server
$env:PYTHONWARNINGS = "ignore"
Write-Host "Starting Tower AI Backend on http://localhost:8000" -ForegroundColor Cyan
python -m uvicorn main:app --app-dir "$PSScriptRoot\backend" --reload --port 8000 --host 0.0.0.0
