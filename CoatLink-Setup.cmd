@echo off
rem =====================================================================
rem  CoatLink - the 3D-Coat half, in one double-click.
rem
rem  It downloads CoatLink-Setup.py from the latest release, runs it with
rem  the Python that 3D-Coat itself ships, and keeps the window open so you
rem  can read what it did.  Nothing is installed except CoatLink's own files
rem  (see coat_side/CoatLinkInstall.py - the same installer every other door
rem  runs).
rem
rem  Read it before running it, if you like: this is the whole file.
rem =====================================================================

setlocal
set "URL=https://github.com/VictoryLuode/Blender-CoatLink/releases/latest/download/CoatLink-Setup.py"
set "GET=%TEMP%\CoatLink-Setup.py"

rem ---- the Python 3D-Coat ships (nothing to install) -------------------
set "PY="
for /d %%D in ("%USERPROFILE%\Documents\3DCoat\python-*") do set "PY=%%D\python.exe"
if not defined PY for %%P in (py.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY (
    echo.
    echo No Python found.  Start 3D-Coat once - it ships one - and run this again.
    goto :done
)

rem ---- fetch the installer --------------------------------------------
where curl >nul 2>nul
if errorlevel 1 (
    echo.
    echo curl is missing on this Windows.  Download this file yourself:
    echo   %URL%
    echo and run it with:  "%PY%" CoatLink-Setup.py
    goto :done
)
echo.
echo Downloading the installer ...
curl -L --fail --silent --show-error -o "%GET%" "%URL%"
if errorlevel 1 (
    echo.
    echo Download failed.  Get it from:
    echo   %URL%
    echo then run:  "%PY%" CoatLink-Setup.py
    goto :done
)

rem ---- run it ----------------------------------------------------------
echo Running the CoatLink installer with:
echo   %PY%
echo.
"%PY%" "%GET%"
echo.
echo Restart 3D-Coat, then look for Scripts ^> CoatLink.

:done
echo.
pause
endlocal
