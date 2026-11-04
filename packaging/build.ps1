# Builds the Windows app and packs it into dist\control_devices_windows.zip.
# Run from the project folder, after installing requirements-build.txt.

$ErrorActionPreference = "Stop"

& .venv\Scripts\python.exe -m PyInstaller control_devices.spec --noconfirm --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Saved as .txt so that a double-click opens it on any Windows laptop.
Copy-Item "docs\huong-dan-laptop.md" "dist\control_devices\HUONG_DAN_LAPTOP.txt"

$zip = "dist\control_devices_windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\control_devices" -DestinationPath $zip
Write-Host "Built $zip"
