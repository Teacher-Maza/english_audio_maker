@echo off
setlocal
set "RC_ROOT=%~dp0.."
for %%I in ("%RC_ROOT%") do set "RC_ROOT=%%~fI"
set "EAM_RC_PAYLOAD=%RC_ROOT%\temp\build_humanization_a\payload"
for %%I in ("%~dp0installer_bootstrap.py") do set "EAM_RC_BOOTSTRAP=%%~fI"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%RC_ROOT%\temp\build_tools\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%RC_ROOT%\tools\inno_setup_6_7_3\compiler\ISCC.exe"
set "CANDIDATE=%RC_ROOT%\temp\final_candidate\EnglishAudioMaker_2.0.0_Setup.exe"
set "FINAL=%RC_ROOT%\dist\EnglishAudioMaker_2.0.0_Setup.exe"

if not exist "%EAM_RC_PAYLOAD%\PAYLOAD_MANIFEST.json" (
  echo Payload stage missing. Run build_installer.py --stage-only first.
  exit /b 2
)
if not exist "%ISCC%" (
  echo Inno Setup 6 compiler not found.
  exit /b 3
)
"%ISCC%" /Qp "%~dp0EnglishAudioMakerV2_RC.iss"
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist "%CANDIDATE%" (
  echo Inno did not produce the candidate installer.
  exit /b 4
)
if not exist "%RC_ROOT%\dist" mkdir "%RC_ROOT%\dist"
copy /Y "%CANDIDATE%" "%FINAL%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
echo Local test installer: %FINAL%
exit /b 0
