@echo off
echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt

echo Running migrations...
python manage.py migrate

echo.
echo Setup complete!
echo.
echo IMPORTANT: Add your GEMINI_API_KEY to .env file!
echo Get it from: https://makersuite.google.com/app/apikey
echo.
echo To start the server:
echo 1. Activate venv: venv\Scripts\activate
echo 2. Run server: python manage.py runserver
echo.
pause
