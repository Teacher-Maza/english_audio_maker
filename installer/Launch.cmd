@echo off
setlocal
set "VTS_V2_HUMANIZATION_A_DATA_ROOT=%LOCALAPPDATA%\EnglishAudioMakerV2HumanizationAData"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "TCL_LIBRARY=%~dp0runtime\tcl\tcl8.6"
set "TK_LIBRARY=%~dp0runtime\tcl\tk8.6"
start "English Audio Maker V2 - Humanization A" "%~dp0runtime\pythonw.exe" -B "%~dp0v2_kokoro\app\main.py"
