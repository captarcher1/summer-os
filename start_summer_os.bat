@echo off
setlocal EnableDelayedExpansion

REM ==========================================================
REM  start_summer_os.bat
REM  Starts the Summer-OS Flask app if it is not already running.
REM  Safe to run at logon, startup, or on a schedule.
REM  Paths are relative to this file — no hardcoded user dirs.
REM ==========================================================

REM ── Configuration ─────────────────────────────────────────
set PYTHON_EXE=C:\Python314\pythonw.exe
set PROJECT_DIR=%~dp0
set PROJECT_DIR=%PROJECT_DIR:~0,-1%
set LOG_DIR=%PROJECT_DIR%\logs
set LOG_FILE=%LOG_DIR%\summer_os_start.log
set APP_PORT=5000

REM ── Ensure logs directory exists ───────────────────────────
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "===== Summer-OS Start Script ====="
call :log "Project dir : %PROJECT_DIR%"
call :log "Python      : %PYTHON_EXE%"

REM ── Verify Python executable ───────────────────────────────
if not exist "%PYTHON_EXE%" (
    call :log "ERROR: Python not found at %PYTHON_EXE%"
    call :log "Update PYTHON_EXE at the top of this script."
    exit /b 1
)

REM ── Check if app is already running on port 5000 ──────────
netstat -ano | findstr /R ":%APP_PORT% .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    call :log "Summer-OS is already running on port %APP_PORT% — nothing to do."
    exit /b 0
)

REM ── Change to project directory ────────────────────────────
cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    call :log "ERROR: Could not cd to %PROJECT_DIR%"
    exit /b 1
)

REM ── Launch app in background (no console window) ──────────
REM pythonw.exe suppresses the console; stdout/stderr go to the log.
call :log "Starting Summer-OS (pythonw app.py) ..."
start "" "%PYTHON_EXE%" app.py >> "%LOG_DIR%\summer_os_app.log" 2>&1

REM ── Give it 3 seconds, then confirm port is now listening ──
timeout /t 3 /nobreak >nul
netstat -ano | findstr /R ":%APP_PORT% .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    call :log "Summer-OS started successfully on port %APP_PORT%."
) else (
    call :log "WARNING: Port %APP_PORT% not yet listening — app may still be loading."
    call :log "Check %LOG_DIR%\summer_os_app.log for errors."
)

call :log "===== Start Script Done ====="
exit /b 0


:log
set MSG=%~1
echo [%date% %time%] %MSG%
echo [%date% %time%] %MSG%>> "%LOG_FILE%"
exit /b
