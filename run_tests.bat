@echo off
cd /d "%~dp0"
echo.
echo [1/3] Checking Python...
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing pytest...
pip install pytest -q 2>nul
if errorlevel 1 (
    echo [ERROR] Failed to install pytest.
    pause
    exit /b 1
)

echo.
echo [3/3] Running tests...
echo ============================================================
python -m pytest tests/ -v --tb=short --junitxml=test_report.xml
echo ============================================================
echo.
echo Report saved to: test_report.xml
echo Done.
pause
