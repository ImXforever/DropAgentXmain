@echo off
echo ============================================
echo    Hermes Marketplace Bot
echo ============================================
echo.

cd /d "%~dp0"

if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo.
    echo ====================================================
    echo Please edit .env file and set your tokens:
    echo   BOT_TOKEN   - from @BotFather
    echo   AI_API_KEY  - from OpenRouter or OpenAI
    echo   ADMIN_IDS   - your Telegram user ID
    echo ====================================================
    pause
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt
echo.

echo Starting Hermes Marketplace Bot...
python bot.py
pause
