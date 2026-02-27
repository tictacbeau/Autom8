@echo off
REM -----------------------------------------------------------------------
REM run.bat — Launch the Remittance Reconciliation Tool
REM Activates the virtual environment and starts Flask.
REM The default browser opens automatically at http://localhost:5000
REM -----------------------------------------------------------------------

cd /d "%~dp0"

if not exist "venv\" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Starting Remittance Reconciliation Tool...
echo Browser will open at http://localhost:5000
echo Press Ctrl+C to stop.
echo.

python app\main.py
