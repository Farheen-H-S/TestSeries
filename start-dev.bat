@echo off
rem Enable local variable scope and delayed expansion for runtime variables
setlocal enabledelayedexpansion

rem Set active code page to UTF-8 to support Unicode symbols like ✓
chcp 65001 >nul

rem Define configurable ports
set "DJANGO_PORT=8000"
set "VITE_PORT=5173"
set "REDIS_PORT=6379"

rem Get the directory where the batch file is located (always ends with a backslash)
set "ROOT=%~dp0"

echo ===================================================
echo  Starting TestSeries Development Environment...
echo ===================================================
echo.

rem Initialize status variables (0 = skipped/already running, 1 = started by this script)
set /a REDIS_STATUS=0
set /a BACKEND_STATUS=0
set /a CELERY_STATUS=0
set /a FRONTEND_STATUS=0

rem 1. Start Redis Server
netstat -ano | findstr /C:"LISTENING" | findstr /C:":%REDIS_PORT% " >nul
if !errorlevel! equ 0 (
    echo [INFO] Redis already running on port %REDIS_PORT%.
    goto REDIS_CHECK_DONE
)

echo [START] Starting Redis server...
start "[TestSeries] Redis" cmd /k "title [TestSeries] Redis && redis-server"
set /a REDIS_STATUS=1

rem Wait for Redis to start listening (up to 10 seconds)
echo Waiting for Redis to start listening on port %REDIS_PORT%...
set /a ATTEMPTS=0
:WAIT_REDIS
netstat -ano | findstr /C:"LISTENING" | findstr /C:":%REDIS_PORT% " >nul
if !errorlevel! equ 0 (
    echo [INFO] Redis is now ready.
    goto REDIS_CHECK_DONE
)
set /a ATTEMPTS+=1
if !ATTEMPTS! geq 10 (
    echo [WARNING] Redis did not start listening on port %REDIS_PORT% within 10 seconds.
    goto REDIS_CHECK_DONE
)
rem Sleep for ~1 second using ping
ping 127.0.0.1 -n 2 >nul
goto WAIT_REDIS

:REDIS_CHECK_DONE

rem 2. Start Backend Django Server
netstat -ano | findstr /C:"LISTENING" | findstr /C:":%DJANGO_PORT% " >nul
if !errorlevel! equ 0 (
    echo [INFO] Django already running on port %DJANGO_PORT%.
) else (
    echo [START] Starting Backend Django server...
    start "[TestSeries] Backend" cmd /k "title [TestSeries] Backend && cd /d %ROOT%backend && call ..\.venv\Scripts\activate.bat && python manage.py runserver %DJANGO_PORT%"
    set /a BACKEND_STATUS=1
)

rem 3. Start Celery Worker
rem Check if a Command Prompt window starting with [TestSeries] Celery is already open
tasklist /FI "WINDOWTITLE eq [TestSeries] Celery*" /V 2>nul | findstr /I "cmd.exe" >nul
if !errorlevel! equ 0 (
    echo [INFO] Celery worker already running.
) else (
    echo [START] Starting Celery worker...
    start "[TestSeries] Celery" cmd /k "title [TestSeries] Celery && cd /d %ROOT%backend && call ..\.venv\Scripts\activate.bat && ..\.venv\Scripts\celery.exe -A TestSeries worker --loglevel=info -P solo"
    set /a CELERY_STATUS=1
)

rem 4. Start Frontend Vite Server
netstat -ano | findstr /C:"LISTENING" | findstr /C:":%VITE_PORT% " >nul
if !errorlevel! equ 0 (
    echo [INFO] Vite already running on port %VITE_PORT%.
) else (
    echo [START] Starting Frontend Vite...
    start "[TestSeries] Frontend" cmd /k "title [TestSeries] Frontend && cd /d %ROOT%frontend && npm run dev -- --port %VITE_PORT%"
    set /a FRONTEND_STATUS=1
)

rem Set final checklist display messages
if !REDIS_STATUS! equ 1 (
    set "REDIS_MSG=✓ Redis     : Running"
) else (
    set "REDIS_MSG=✓ Redis     : Already Running"
)

if !BACKEND_STATUS! equ 1 (
    set "BACKEND_MSG=✓ Django    : http://127.0.0.1:%DJANGO_PORT% (Started)"
) else (
    set "BACKEND_MSG=✓ Django    : http://127.0.0.1:%DJANGO_PORT% (Already Running)"
)

if !CELERY_STATUS! equ 1 (
    set "CELERY_MSG=✓ Celery    : Running"
) else (
    set "CELERY_MSG=✓ Celery    : Already Running"
)

if !FRONTEND_STATUS! equ 1 (
    set "FRONTEND_MSG=✓ Frontend  : http://localhost:%VITE_PORT% (Started)"
) else (
    set "FRONTEND_MSG=✓ Frontend  : http://localhost:%VITE_PORT% (Already Running)"
)

rem Display startup summary block
echo.
echo ===================================================
echo  TestSeries Development Environment
echo ===================================================
echo.
echo   !REDIS_MSG!
echo   !BACKEND_MSG!
echo   !CELERY_MSG!
echo   !FRONTEND_MSG!
echo.
echo Double-click stop-dev.bat to stop everything.
echo ===================================================
echo.

endlocal
pause
