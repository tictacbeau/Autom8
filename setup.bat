@echo off
REM -----------------------------------------------------------------------
REM setup.bat — First-time setup for Remittance Reconciliation Tool
REM Creates a virtual environment and installs all Python dependencies.
REM No administrator privileges required.
REM -----------------------------------------------------------------------

cd /d "%~dp0"

echo.
echo =======================================================
echo   Remittance Reconciliation Tool ^— Setup
echo =======================================================
echo.

REM ------------------------------------------------------------------
REM Check Python version
REM ------------------------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python was not found in PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Using Python %PYVER%
echo.

REM ------------------------------------------------------------------
REM Create virtual environment
REM ------------------------------------------------------------------
if not exist "venv\" (
    echo Creating virtual environment in .\venv ...
    python -m venv venv
    echo Virtual environment created.
) else (
    echo Virtual environment already exists. Skipping creation.
)
echo.

REM ------------------------------------------------------------------
REM Activate and install dependencies
REM ------------------------------------------------------------------
echo Installing Python dependencies from requirements.txt ...
echo ^(This may take a few minutes on first run.^)
echo.

call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt

REM ------------------------------------------------------------------
REM Create runtime data directories
REM ------------------------------------------------------------------
echo.
echo Creating data directories ...
if not exist "data\tokens\"      mkdir data\tokens
if not exist "data\watch\"       mkdir data\watch
if not exist "data\remittances\" mkdir data\remittances
if not exist "data\attachments\" mkdir data\attachments
echo Data directories ready.

REM ------------------------------------------------------------------
REM Check for optional Tesseract
REM ------------------------------------------------------------------
echo.
echo Checking optional system dependencies ...
tesseract --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Tesseract OCR found.
) else (
    echo   [WARN] Tesseract OCR not found.
    echo          OCR fallback will be unavailable.
    echo          Download from: https://github.com/UB-Mannheim/tesseract/wiki
    echo          Most PDFs are processed without OCR -- this is optional.
)

REM ------------------------------------------------------------------
REM Done
REM ------------------------------------------------------------------
echo.
echo =======================================================
echo   Setup complete!
echo.
echo   To launch the application:
echo     run.bat
echo.
echo   The browser will open automatically at http://localhost:5000
echo =======================================================
echo.
pause
