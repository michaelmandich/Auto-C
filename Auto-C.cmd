@echo off
setlocal
cd /d "%~dp0"
set "python=.venv\Scripts\python.exe"
if not exist "%python%" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
"%python%" -c "import sounddevice, webrtcvad" >nul 2>&1
if errorlevel 1 (
    "%python%" -m pip install --only-binary=:all: -r requirements.txt
    if errorlevel 1 goto failed
)
if "%~1"=="" goto display
if /i "%~1"=="--display" goto display
"%python%" auto_c.py %*
if errorlevel 1 goto failed
exit /b 0

:display
start "" ".venv\Scripts\pythonw.exe" auto_c.py --display %*
exit /b %errorlevel%

:failed
echo Auto-C could not start or stopped with an error. See the message above.
if not defined AUTO_C_NO_PAUSE pause
exit /b 1
