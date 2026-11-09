@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Building DigitalPersona 4500 Windows Executable (.exe)
echo ============================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Installing build requirements (pyinstaller, numpy, pillow)...
python -m pip install --upgrade pip
python -m pip install pyinstaller numpy pillow

echo.
echo [2/4] Checking for DigitalPersona U.are.U Windows SDK DLLs...
set "DP_DLL_DIR=C:\Program Files\DigitalPersona\U.are.U SDK\Windows\Lib\x64"
if exist "%DP_DLL_DIR%\dpfpdd.dll" (
    echo   Found dpfpdd.dll at %DP_DLL_DIR%
    copy "%DP_DLL_DIR%\dpfpdd.dll" . >nul
    copy "%DP_DLL_DIR%\dpfj.dll" . >nul
    echo   Copied dpfpdd.dll and dpfj.dll into build folder.
) else (
    echo   [Notice] Official SDK not detected in standard directory.
    echo   If you have dpfpdd.dll / dpfj.dll, place them in this folder.
)

echo.
echo [3/4] Compiling Web/REST Server: dp4500_server.exe ...
python -m PyInstaller --clean --noconfirm dp4500_server.spec

echo.
echo [4/4] Compiling CLI tool: dp4500.exe ...
python -m PyInstaller --clean --noconfirm dp4500_cli.spec

echo.
echo ============================================================
echo   BUILD COMPLETE!
echo ============================================================
echo Executables created in: %CD%\dist\
echo   - dist\dp4500_server.exe  (Web & REST Biometric Server)
echo   - dist\dp4500.exe         (Command-Line Interface Tool)
echo.
echo Simply double-click 'dist\dp4500_server.exe' to launch!
echo ============================================================
pause
