@echo off
title SAP S/4HANA Playwright Launcher
cd /d "%~dp0"
echo Starting SAP Login Automation in Google Chrome...
.\.venv\Scripts\python.exe test_sap_login.py
pause

