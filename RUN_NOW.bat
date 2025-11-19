@echo off
cls
echo ========================================
echo   AI Investment Advisory Backend
echo ========================================
echo.

REM Check if venv exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

echo Activating virtual environment...
call venv\Scripts\activate
echo.

REM Check if Django is installed
python -c "import django" 2>nul
if errorlevel 1 (
    echo Django not found. Installing basic packages...
    echo.
    python -m pip install --upgrade pip
    pip install Django==5.0
    pip install djangorestframework==3.14.0
    pip install django-cors-headers==4.3.1
    pip install python-dotenv==1.0.0
    echo.
    
    echo Running migrations...
    python manage.py migrate
    echo.
)

echo ========================================
echo Starting Django Server...
echo ========================================
echo.
echo Backend will run at: http://localhost:8000
echo API Health Check: http://localhost:8000/api/health/
echo.
echo Press Ctrl+C to stop the server
echo.

python manage.py runserver
