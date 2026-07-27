@echo off
setlocal
set "RC_ROOT=%~dp0.."
for %%I in ("%RC_ROOT%") do set "RC_ROOT=%%~fI"
set "EAM_RC_PAYLOAD=%RC_ROOT%\temp\build_humanization_a\payload"
for %%I in ("%~dp0installer_bootstrap.py") do set "EAM_RC_BOOTSTRAP=%%~fI"
set "ISCC=%RC_ROOT%\tools\inno_setup_6_7_3\compiler\ISCC.exe"
set "CANDIDATE=%RC_ROOT%\temp\final_candidate\EnglishAudioMakerV2_Humanization_A_Baseline_Setup.exe"
set "FINAL=%RC_ROOT%\dist\EnglishAudioMakerV2_Humanization_A_Baseline_Setup.exe"

if not exist "%EAM_RC_PAYLOAD%\PAYLOAD_MANIFEST.json" (
  echo Payload stage missing. Run build_installer.py --stage-only first.
  exit /b 2
)
if not exist "%ISCC%" (
  echo ISCC missing. Install the verified Inno Setup 6.7.3 locally under tools\inno_setup_6_7_3\compiler.
  exit /b 3
)
"%ISCC%" /Qp "%~dp0EnglishAudioMakerV2_RC.iss"
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist "%CANDIDATE%" (
  echo Inno did not produce the candidate installer.
  exit /b 4
)
copy /Y "%CANDIDATE%" "%FINAL%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
echo Final Humanization A baseline installer: %FINAL%
exit /b 0
