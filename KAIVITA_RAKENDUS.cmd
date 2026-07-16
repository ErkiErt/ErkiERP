@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH="
set "ERKI_INTERNAL_MODE=1"

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%CODEX_PY%" goto run_codex_python

where py >nul 2>&1
if not errorlevel 1 goto run_py_launcher

echo Sobivat Pythonit ei leitud.
echo Paigalda Python aadressilt https://www.python.org/downloads/
echo Paigaldamisel vali kindlasti "Add Python to PATH".
pause
exit /b 1

:run_codex_python
"%CODEX_PY%" -c "import streamlit, pandas, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo Paigaldan vajalikud paketid...
    "%CODEX_PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto install_failed
)
echo Kaivitan Saetoo rakenduse...
"%CODEX_PY%" -m streamlit run app.py --browser.gatherUsageStats=false --server.showEmailPrompt=false
goto end

:run_py_launcher
py -3 -c "import streamlit, pandas, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo Paigaldan vajalikud paketid...
    py -3 -m pip install -r requirements.txt
    if errorlevel 1 goto install_failed
)
echo Kaivitan Saetoo rakenduse...
py -3 -m streamlit run app.py --browser.gatherUsageStats=false --server.showEmailPrompt=false
goto end

:install_failed
echo.
echo Pakettide paigaldamine ebaonnestus. Vaata uleval olevat veateadet.
pause
exit /b 1

:end
endlocal
