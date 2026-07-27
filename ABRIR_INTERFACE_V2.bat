@echo off
cd /d "%~dp0"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "TCL_LIBRARY=\\?\%~dp0runtime\tcl\tcl8.6"
set "TK_LIBRARY=\\?\%~dp0runtime\tcl\tk8.6"
set "PYTHONPATH=%~dp0runtime\Lib\site-packages"
start "Humanization B2 - Conservative Prosodic Segmentation" "%~dp0runtime\pythonw.exe" -B "%~dp0app\main.py"
