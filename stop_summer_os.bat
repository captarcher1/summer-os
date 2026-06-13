@echo off
setlocal EnableDelayedExpansion

REM ==========================================================
REM  stop_summer_os.bat
REM  Stops the Summer-OS Flask app by killing the process
REM  bound to port 5000.  Ollama is left running.
REM  Safe to run even if the app is not currently running.
REM ==========================================================

REM ── Configuration ─────────────────────────────────────────
set PROJECT_DIR=%~dp0
set PROJECT_DIR=%PROJECT_DIR:~0,-1%
set LOG_DIR=%PROJECT_DIR%\logs
set LOG_FILE=%LOG_DIR%\summer_os_stop.log
set APP_PORT=5000

REM ── Ensure logs directory exists ───────────────────────────
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "===== Summer-OS Stop Script ====="

REM ── Check if anything is listening on port 5000 ───────────
netstat -ano | findstr /R ":%APP_PORT% .*LISTENING" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    call :log "Summer-OS is not running on port %APP_PORT% — nothing to stop."
    call :log "===== Stop Script Done ====="
    exit /b 0
)

REM ── Extract the PID bound to port 5000 ────────────────────
REM  netstat line format: Proto  Local Addr  Foreign Addr  State  PID
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R ":%APP_PORT% .*LISTENING"') do (
    set TARGET_PID=%%P
)

if not defined TARGET_PID (
    call :log "ERROR: Could not determine PID for port %APP_PORT%."
    exit /b 1
)

call :log "Found Summer-OS on port %APP_PORT% — PID: %TARGET_PID%"

REM ── Kill Flask process only ────────────────────────────────
REM  /F = force  /T = include child processes
taskkill /PID %TARGET_PID% /F /T >nul 2>&1

if %ERRORLEVEL% equ 0 (
    call :log "Successfully stopped Summer-OS (PID %TARGET_PID%)."
) else (
    call :log "ERROR: taskkill failed for PID %TARGET_PID% (exit code %ERRORLEVEL%)."
    call :log "Try running this script as Administrator."
    exit /b 1
)

REM ── Verify port is now free ────────────────────────────────
timeout /t 2 /nobreak >nul
netstat -ano | findstr /R ":%APP_PORT% .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    call :log "WARNING: Port %APP_PORT% is still in use after kill — process may need more time."
) else (
    call :log "Port %APP_PORT% is now free."
)

call :log "NOTE: Ollama was NOT stopped — it remains available for other uses."
call :log "===== Stop Script Done ====="
exit /b 0


:log
set MSG=%~1
echo [%date% %time%] %MSG%
echo [%date% %time%] %MSG%>> "%LOG_FILE%"
exit /b
