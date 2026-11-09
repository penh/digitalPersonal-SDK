# DigitalPersona 4500 - Windows Executable Build Script (PowerShell)
# Builds standalone dp4500_server.exe and dp4500.exe using PyInstaller

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Building DigitalPersona 4500 Windows Executable (.exe)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "Python detected: $pyVersion" -ForegroundColor Green
} catch {
    Write-Error "Python is not installed or not in PATH. Please install Python 3.8+."
    exit 1
}

# 2. Install requirements
Write-Host "`n[1/4] Installing PyInstaller, NumPy, Pillow..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install pyinstaller numpy pillow

# 3. Locate DigitalPersona DLLs
Write-Host "`n[2/4] Checking for DigitalPersona Windows SDK DLLs..." -ForegroundColor Yellow
$dpPaths = @(
    "C:\Program Files\DigitalPersona\U.are.U SDK\Windows\Lib\x64",
    "C:\Program Files (x86)\DigitalPersona\U.are.U SDK\Windows\Lib\win32",
    "C:\Program Files\Crossmatch\U.are.U SDK\Windows\Lib\x64"
)

$foundDll = $false
foreach ($p in $dpPaths) {
    if (Test-Path "$p\dpfpdd.dll") {
        Write-Host "  Found DigitalPersona SDK at $p" -ForegroundColor Green
        Copy-Item "$p\dpfpdd.dll" -Destination "." -Force
        Copy-Item "$p\dpfj.dll" -Destination "." -Force
        $foundDll = $true
        break
    }
}
if (-not $foundDll) {
    Write-Host "  Official SDK DLLs not found in default paths." -ForegroundColor DarkYellow
    Write-Host "  If available, copy dpfpdd.dll and dpfj.dll into this directory." -ForegroundColor DarkYellow
}

# 4. Build Server
Write-Host "`n[3/4] Compiling dp4500_server.exe (Web Console & REST API)..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm dp4500_server.spec

# 5. Build CLI
Write-Host "`n[4/4] Compiling dp4500.exe (CLI Tool)..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm dp4500_cli.spec

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Executables generated in: $(Get-Location)\dist\"
Write-Host "  -> dist\dp4500_server.exe  (Web & REST Biometric Server)" -ForegroundColor White
Write-Host "  -> dist\dp4500.exe         (Command-Line Interface)" -ForegroundColor White
Write-Host "`nDouble-click 'dist\dp4500_server.exe' to launch the web console!" -ForegroundColor Green
