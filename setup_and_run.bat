@echo off
echo ========================================================
echo   Let me TEST it....! - Setup ^& Launch (Windows)
echo ========================================================

:: 1. Verify Python Installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please download and install Python 3.10, 3.11 or 3.12 from:
    echo   https://www.python.org/downloads/
    echo **IMPORTANT**: Make sure to check the box "Add Python to PATH" during install!
    pause
    exit /b 1
)

:: 2. Create Virtual Environment
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
)

:: 3. Activate Virtual Environment
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:: 4. Upgrade pip and install dependencies
echo [*] Installing required Python libraries...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 5. Install Playwright browser engine
echo [*] Installing Playwright Chromium browser...
playwright install chromium

:: 6. Launch Application
echo.
echo ========================================================
echo   Starting Let me TEST it....! Dashboard
echo ========================================================
echo Dashboard will open automatically in your browser...
streamlit run app/ui.py
pause

