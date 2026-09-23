@echo off
title Automated Session Recording Upload System
echo ===================================================
echo   Automated Session Recording Upload System
echo ===================================================
echo.
cd /d "%~dp0"

echo [1/2] Checking MySQL Database connection on port 3307...
netstat -ano | findstr ":3307" >nul 2>&1
if errorlevel 1 (
    echo [!] MySQL not running on port 3307. Starting XAMPP MySQL automatically...
    if exist "C:\xampp\mysql\bin\mysqld.exe" (
        start "" /B "C:\xampp\mysql\bin\mysqld.exe" --defaults-file="C:\xampp\mysql\bin\my.ini" --port=3307 --standalone
        timeout /t 2 /nobreak >nul
        echo [OK] MySQL server started on port 3307!
    ) else (
        echo [!] Please start MySQL via XAMPP Control Panel.
    )
) else (
    echo [OK] MySQL is active on port 3307.
)

echo.
echo [2/2] Launching Web Application Server...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" backend\app.py
) else (
    python backend\app.py
)

pause
