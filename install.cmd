@echo off
rem CoatLink - install the 3D-Coat half.  Double-click this file, that is all.
rem
rem It runs coat_side\CoatLinkInstall.py, which works out both folders itself and
rem writes the menu entries with this machine's paths.  No admin rights, no PATH
rem editing, nothing to configure.
rem
rem   COATLINK_PYTHON   optional: the Python to use
rem   COATLINK_PREFS    optional: 3D-Coat's UserPrefs folder
rem   COATLINK_COAT_DIR optional: 3D-Coat's program folder (for the button icons)
rem
rem Pass ..\install.cmd --uninstall to take it back out.

setlocal enabledelayedexpansion
title CoatLink setup
set "HERE=%~dp0"
set "PY="

rem COATLINK_PYTHON=... points at a Python when the search below cannot find one
if defined COATLINK_PYTHON if exist "%COATLINK_PYTHON%" set "PY=%COATLINK_PYTHON%"

rem 3D-Coat ships its own Python - in its Documents folder, and that is not always
rem %USERPROFILE%\Documents: redirect Documents to OneDrive and it lives there.
rem COATLINK_DOCS=... skips the search below and names that folder outright.
if not defined COATLINK_DOCS for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Personal 2^>nul') do set "COATLINK_DOCS=%%B"
if defined COATLINK_DOCS call set "COATLINK_DOCS=%COATLINK_DOCS%"
for %%R in ("%COATLINK_DOCS%" "%OneDrive%\Documents" "%OneDriveCommercial%\Documents" "%OneDriveConsumer%\Documents" "%USERPROFILE%\Documents") do (
    rem two passes: the folders named after a recent version (3DCoat2025, 3DCoat2026)
    rem first, then any 3DCoat folder.  for /d takes one wildcard level at a time.
    if not defined PY for /d %%A in ("%%~fR\3DCoat20*") do (
        if not defined PY for /d %%D in ("%%~A\python-*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
    )
    if not defined PY for /d %%A in ("%%~fR\3DCoat*") do (
        if not defined PY for /d %%D in ("%%~A\python-*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
    )
)

rem A python.exe on PATH can be the Windows Store stub: it opens the Store and
rem runs nothing, so the installer would look like it did nothing at all.  Only
rem what is left has to actually run - the Python 3D-Coat ships is its own.
if not defined PY for %%P in (python.exe py.exe python3.exe) do (
    if not defined PY (
        set "CAND=%%~$PATH:P"
        if defined CAND (
            set "CHECK=!CAND:WindowsApps=!"
            if not "!CHECK!"=="!CAND!" set "CAND="
        )
        if defined CAND (
            "!CAND!" -c "import sys" >nul 2>nul
            if not errorlevel 1 set "PY=!CAND!"
        )
    )
)
if not defined PY goto :no_python

if not exist "%HERE%coat_side\CoatLinkInstall.py" goto :not_unpacked

echo Using %PY%
echo.
"%PY%" "%HERE%coat_side\CoatLinkInstall.py" %*
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" (
    echo Setup did not finish - the message above says why.
) else (
    echo Done.  Restart 3D-Coat, then look for Scripts ^> CoatLink.
)
pause
exit /b %CODE%

:no_python
echo.
echo No Python found.  Start 3D-Coat once - it creates its own Python folder - and
echo run this file again, or install Python from python.org.
pause
exit /b 1

:not_unpacked
echo.
echo coat_side\CoatLinkInstall.py is missing next to this file.
echo Unzip the whole release first, then double-click install.cmd inside it.
pause
exit /b 1
