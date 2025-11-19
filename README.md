# AI Investment Advisory Backend

Django REST Framework backend with CrewAI for market trend-based investment advisory.

## Setup Instructions

### 1. Create Virtual Environment
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Edit `.env` file and add your API keys:
```
GEMINI_API_KEY=your_gemini_api_key_here
SERPER_API_KEY=your_serper_api_key_here
```

Get API keys:
- Google Gemini: https://makersuite.google.com/app/apikey (FREE)
- Serper (for web search): https://serper.dev (free tier available)

### 4. Run Migrations
```bash
python manage.py migrate
```

### 5. Start Server
```bash
python manage.py runserver
```

Server will run at: http://localhost:8000

## API Endpoints

- `GET /api/health/` - Health check
- `POST /api/investment-plan/` - Generate AI-powered investment plan

## Features

- **Market Research Agent**: Analyzes real-time market trends
- **Tax Calculator Agent**: Calculates Indian tax liability
- **Investment Strategist Agent**: Creates personalized portfolios
- **Portfolio Optimizer Agent**: Optimizes allocations based on market trends

## Request Format

```json
{
  "incomes": [
    {"type": "salary", "amount": 1000000}
  ],
  "expectedReturn": "medium",
  "riskAppetite": "medium",
  "investmentMode": "percent",
  "investmentValue": 30
}
```
