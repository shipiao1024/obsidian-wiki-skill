@echo off
cd /d "%~dp0"
echo.
echo ============================================================
echo  obsidian-wiki-skill V1.1 — Environment Check & Full Test
echo ============================================================
echo.

echo [1/4] Checking Python version...
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
    pause
    exit /b 1
)
python -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [WARN] Python 3.11+ recommended. Current version may have issues.
)
echo [OK] Python version check passed.
echo.

echo [2/4] Running dependency check...
python scripts\check_deps.py
echo.

echo [3/4] Installing test dependencies...
pip install pytest pytest-mock -q 2>nul
if errorlevel 1 (
    echo [ERROR] Failed to install pytest/pytest-mock.
    pause
    exit /b 1
)
echo [OK] Test dependencies installed.
echo.

echo [4/4] Running full test suite (unit + integration + E2E)...
echo ============================================================
python -m pytest tests/ -v --tb=short --junitxml=test_report.xml
echo ============================================================
echo.
echo Report saved to: test_report.xml
echo Done.
pause
