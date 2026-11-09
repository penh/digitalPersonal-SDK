@echo off
:: Self-elevate to Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~fn0\"\"' -Verb RunAs"
    exit /b
)

title DigitalPersona 4500 Driver Switcher
echo ============================================================
echo   Switching DigitalPersona 4500 to Official SDK Driver
echo ============================================================
echo.

echo [1/3] Installing DigitalPersona Legacy Driver (dPersona_x64.inf)...
pnputil /add-driver "C:\Users\fuyon\Downloads\DP4500_Legacy_Driver\x64\dPersona_x64.inf" /install

echo.
echo [2/3] Removing conflicting WBF driver (oem2.inf)...
pnputil /delete-driver oem2.inf /uninstall /force

echo.
echo [3/3] Refreshing USB biometric devices...
powershell -Command "Get-PnpDevice | Where-Object { $_.InstanceId -like '*05BA*' } | Disable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 800; Get-PnpDevice | Where-Object { $_.InstanceId -like '*05BA*' } | Enable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue"

echo.
echo ============================================================
echo   DRIVER SETUP FINISHED!
echo ============================================================
echo.
echo Checking current status:
powershell -Command "Get-PnpDevice | Where-Object { $_.InstanceId -like '*05BA*' } | Select-Object FriendlyName, Status, Service | Format-Table -AutoSize"
echo.
pause
