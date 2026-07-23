@echo off
setlocal enabledelayedexpansion

:: Set active code page to UTF-8 to support Unicode symbols
chcp 65001 >nul

echo ===================================================
echo  Stopping TestSeries Development Environment...
echo ===================================================
echo.

:: Stop Frontend
tasklist /FI "WINDOWTITLE eq [TestSeries] Frontend*" /V 2>nul | findstr /I "cmd.exe" >nul
if !errorlevel! equ 0 (
    taskkill /FI "WINDOWTITLE eq [TestSeries] Frontend*" /T /F >nul 2>&1
    echo [STOPPED] Frontend terminal and its child processes.
) else (
    echo [INFO] Frontend terminal was not running.
)

:: Stop Backend
tasklist /FI "WINDOWTITLE eq [TestSeries] Backend*" /V 2>nul | findstr /I "cmd.exe" >nul
if !errorlevel! equ 0 (
    taskkill /FI "WINDOWTITLE eq [TestSeries] Backend*" /T /F >nul 2>&1
    echo [STOPPED] Backend terminal and its child processes.
) else (
    echo [INFO] Backend terminal was not running.
)

:: Stop Celery
tasklist /FI "WINDOWTITLE eq [TestSeries] Celery*" /V 2>nul | findstr /I "cmd.exe" >nul
if !errorlevel! equ 0 (
    taskkill /FI "WINDOWTITLE eq [TestSeries] Celery*" /T /F >nul 2>&1
    echo [STOPPED] Celery terminal and its child processes.
) else (
    echo [INFO] Celery terminal was not running.
)

:: Stop Redis
tasklist /FI "WINDOWTITLE eq [TestSeries] Redis*" /V 2>nul | findstr /I "cmd.exe" >nul
if !errorlevel! equ 0 (
    taskkill /FI "WINDOWTITLE eq [TestSeries] Redis*" /T /F >nul 2>&1
    echo [STOPPED] Redis terminal and its child processes.
) else (
    echo [INFO] Redis terminal was not running.
)

echo.
echo ===================================================
echo  All services stopped successfully.
echo ===================================================
echo.

endlocal
pause
