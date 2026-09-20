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

setlocal
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
    if not defined PY for /d %%D in ("%%~fR\3DCoat\python-*") do if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)

if not defined PY (where py >nul 2>nul && set "PY=py")
if not defined PY (where python >nul 2>nul && set "PY=python")
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
