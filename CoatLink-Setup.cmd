@echo off
rem =====================================================================
rem  CoatLink - the 3D-Coat half, in one double-click.
rem
rem  It downloads CoatLink-Setup.py from the latest release, runs it with
rem  the Python that 3D-Coat itself ships, and keeps the window open so you
rem  can read what it did.  If 3D-Coat lives under "C:\Program Files" the
rem  button icons need administrator rights, so the installer is run once
rem  more with elevation - that is the only reason this file ever asks.
rem
rem  It installs nothing by itself: coat_side/CoatLinkInstall.py does the
rem  work, the same installer every other door runs.  Read it first, if you
rem  like: this is the whole file.
rem
rem  Set COATLINK_NO_ELEVATE=1 to skip the elevation retry.
rem =====================================================================

setlocal enabledelayedexpansion
set "URL=https://github.com/VictoryLuode/Blender-CoatLink/releases/latest/download/CoatLink-Setup.py"
set "GET=%TEMP%\CoatLink-Setup.py"
set "OUT=%TEMP%\CoatLink-install.log"

rem ---- the Python 3D-Coat ships (nothing to install) -------------------
set "PY="

rem 3D-Coat's own Python lives in its Documents folder, and that is not always
rem %USERPROFILE%\Documents: redirect Documents to OneDrive and it lives there.
rem COATLINK_PYTHON=... overrides the search entirely, and COATLINK_DOCS=... names
rem the Documents folder outright when Windows' answer is not where it lives.
if defined COATLINK_PYTHON if exist "%COATLINK_PYTHON%" set "PY=%COATLINK_PYTHON%"
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
rem runs nothing, so the download would look like it did nothing at all.  Only
rem what is left has to actually run.
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
if not defined PY (
    echo.
    echo No Python found.  Start 3D-Coat once - it ships one - and run this again,
    echo or set COATLINK_PYTHON to a python.exe and run this again.
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

rem ---- run it (the output is kept, so the icon question can be answered) ----
echo Running the CoatLink installer with:
echo   %PY%
echo.
"%PY%" "%GET%" > "%OUT%" 2>&1
type "%OUT%"
echo.

rem ---- the 3D-Coat icon folder is inside Program Files, so it needs admin --
if defined COATLINK_NO_ELEVATE goto :installed
findstr /c:"Permission denied" "%OUT%" >nul 2>nul
if errorlevel 1 goto :installed
echo The button icons need administrator rights for the 3D-Coat program folder.
echo Asking Windows for elevation once - approve the prompt to get the icons.
echo (The buttons work without them; they just use the default tool icons.)
echo.
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '%GET%' -Verb RunAs -Wait"

:installed
echo.
echo Restart 3D-Coat, then look for Scripts ^> CoatLink.

:done
echo.
pause
endlocal
