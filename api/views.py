from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import DubaiInquiry
import os
import logging
import traceback

logger = logging.getLogger(__name__)

# ================================================================
# AI ENABLED CHECK
# ================================================================
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
AI_ENABLED = False  # Temporarily disabled - Gemini API compatibility issue

if AI_ENABLED:
    try:
        from .serializers import InvestmentRequestSerializer
        from .crew.crew import run_investment_advisory_crew
    except Exception as e:
        print("⚠️ AI disabled due to import error:", e)
        traceback.print_exc()
        AI_ENABLED = False


# ================================================================
# HEALTH CHECK ENDPOINT
# ================================================================
@api_view(["GET"])
def health_check(request):
    ai_status = "enabled" if AI_ENABLED else "disabled"

    return Response(
        {
            "status": "healthy",
            "message": "Investment API Running",
            "ai_enabled": AI_ENABLED,
            "ai_status": ai_status,
        },
        status=200,
    )


# ================================================================
# REGENERATE ALLOCATION
# ================================================================
@api_view(["POST"])
def regenerate_allocation(request):
    try:
        excluded = request.data.get("excludedInstruments", [])
        allocation = request.data.get("currentAllocation", [])

        remaining = [x.copy() for x in allocation if x["name"] not in excluded]

        if not remaining:
            return Response(
                {"error": "Cannot remove all instruments"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total = sum(item["percent"] for item in remaining)
        for item in remaining:
            item["percent"] = round((item["percent"] / total) * 100)

        diff = 100 - sum(item["percent"] for item in remaining)
        remaining[0]["percent"] += diff

        return Response(
            {
                "newAllocation": remaining,
                "reasoning": f"Removed {', '.join(excluded)} and redistributed.",
            }
        )

    except Exception as e:
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


# ================================================================
# PREDEFINED INVESTMENT PLANS
# ================================================================
PREDEFINED_PLANS = {
    "low_low": {
        "name": "Conservative Stable Plan",
        "allocation": [
            {"name": "PPF", "percent": 30, "returns": "7-8%", "risk": "Low"},
            {"name": "Debt Mutual Funds", "percent": 25, "returns": "6-8%", "risk": "Low"},
            {"name": "Fixed Deposits", "percent": 20, "returns": "6-7%", "risk": "Low"},
            {"name": "Gold ETF", "percent": 15, "returns": "8-10%", "risk": "Low"},
            {"name": "Liquid Funds", "percent": 10, "returns": "5-6%", "risk": "Low"},
        ],
        "expectedReturn": "6-8%"
    },
    "low_medium": {
        "name": "Conservative Balanced Plan",
        "allocation": [
            {"name": "PPF", "percent": 25, "returns": "7-8%", "risk": "Low"},
            {"name": "Debt Funds", "percent": 25, "returns": "6-8%", "risk": "Low"},
            {"name": "Large Cap Index", "percent": 20, "returns": "10-12%", "risk": "Medium"},
            {"name": "Gold", "percent": 15, "returns": "8-10%", "risk": "Low"},
            {"name": "Corporate Bonds", "percent": 15, "returns": "7-9%", "risk": "Low"},
        ],
        "expectedReturn": "7-9%"
    },
    "low_high": {
        "name": "Conservative Growth Plan",
        "allocation": [
            {"name": "Nifty 50 Index", "percent": 25, "returns": "11-13%", "risk": "Medium"},
            {"name": "Debt Funds", "percent": 25, "returns": "6-8%", "risk": "Low"},
            {"name": "PPF", "percent": 20, "returns": "7-8%", "risk": "Low"},
            {"name": "Gold ETF", "percent": 15, "returns": "8-10%", "risk": "Low"},
            {"name": "Banking ETF", "percent": 15, "returns": "12-15%", "risk": "Medium"},
        ],
        "expectedReturn": "9-11%"
    },
    "medium_low": {
        "name": "Balanced Conservative Plan",
        "allocation": [
            {"name": "Nifty 50", "percent": 25, "returns": "11-13%", "risk": "Medium"},
            {"name": "Debt Funds", "percent": 25, "returns": "6-8%", "risk": "Low"},
            {"name": "Gold", "percent": 20, "returns": "8-10%", "risk": "Low"},
            {"name": "PPF", "percent": 15, "returns": "7-8%", "risk": "Low"},
            {"name": "IT Sector Fund", "percent": 15, "returns": "13-16%", "risk": "Medium"},
        ],
        "expectedReturn": "9-11%"
    },
    "medium_medium": {
        "name": "Balanced Growth Plan",
        "allocation": [
            {"name": "Nifty 50 Index", "percent": 25, "returns": "11-13%", "risk": "Medium"},
            {"name": "Mid Cap Fund", "percent": 20, "returns": "13-16%", "risk": "Medium"},
            {"name": "Debt Funds", "percent": 20, "returns": "6-8%", "risk": "Low"},
            {"name": "Banking Sector", "percent": 15, "returns": "12-15%", "risk": "Medium"},
            {"name": "Gold ETF", "percent": 12, "returns": "8-10%", "risk": "Low"},
            {"name": "Infrastructure Fund", "percent": 8, "returns": "14-17%", "risk": "Medium"},
        ],
        "expectedReturn": "11-13%"
    },
    "medium_high": {
        "name": "Balanced Aggressive Plan",
        "allocation": [
            {"name": "Nifty 50", "percent": 20, "returns": "11-13%", "risk": "Medium"},
            {"name": "Mid Cap Fund", "percent": 20, "returns": "13-16%", "risk": "Medium"},
            {"name": "Small Cap Fund", "percent": 15, "returns": "15-20%", "risk": "High"},
            {"name": "Sectoral Funds", "percent": 15, "returns": "14-18%", "risk": "High"},
            {"name": "Debt Funds", "percent": 15, "returns": "6-8%", "risk": "Low"},
            {"name": "Gold", "percent": 10, "returns": "8-10%", "risk": "Low"},
            {"name": "International ETF", "percent": 5, "returns": "12-15%", "risk": "Medium"},
        ],
        "expectedReturn": "12-15%"
    },
    "high_low": {
        "name": "Growth Conservative Plan",
        "allocation": [
            {"name": "Nifty 50", "percent": 30, "returns": "11-13%", "risk": "Medium"},
            {"name": "Mid Cap", "percent": 20, "returns": "13-16%", "risk": "Medium"},
            {"name": "Debt Funds", "percent": 20, "returns": "6-8%", "risk": "Low"},
            {"name": "Banking Sector", "percent": 15, "returns": "12-15%", "risk": "Medium"},
            {"name": "Gold", "percent": 15, "returns": "8-10%", "risk": "Low"},
        ],
        "expectedReturn": "10-13%"
    },
    "high_medium": {
        "name": "Aggressive Balanced Plan",
        "allocation": [
            {"name": "Mid Cap Fund", "percent": 25, "returns": "13-16%", "risk": "Medium"},
            {"name": "Nifty 50", "percent": 20, "returns": "11-13%", "risk": "Medium"},
            {"name": "Small Cap Fund", "percent": 15, "returns": "15-20%", "risk": "High"},
            {"name": "Sectoral Funds", "percent": 15, "returns": "14-18%", "risk": "High"},
            {"name": "Debt Funds", "percent": 15, "returns": "6-8%", "risk": "Low"},
            {"name": "Gold ETF", "percent": 10, "returns": "8-10%", "risk": "Low"},
        ],
        "expectedReturn": "12-15%"
    },
    "high_high": {
        "name": "Aggressive Growth Plan",
        "allocation": [
            {"name": "Small Cap Fund", "percent": 25, "returns": "15-20%", "risk": "High"},
            {"name": "Mid Cap Fund", "percent": 20, "returns": "13-16%", "risk": "Medium"},
            {"name": "Sectoral Funds", "percent": 18, "returns": "14-18%", "risk": "High"},
            {"name": "Nifty 50", "percent": 15, "returns": "11-13%", "risk": "Medium"},
            {"name": "International ETF", "percent": 10, "returns": "12-15%", "risk": "Medium"},
            {"name": "Debt Funds", "percent": 7, "returns": "6-8%", "risk": "Low"},
            {"name": "Gold", "percent": 5, "returns": "8-10%", "risk": "Low"},
        ],
        "expectedReturn": "14-18%"
    },
}

def calculate_tax(incomes):
    slab_income = 0
    stcg_tax = 0
    ltcg_tax = 0
    
    for inc in incomes:
        amount = float(inc.get('amount', 0))
        inc_type = inc.get('type', 'salary')
        
        if inc_type == 'rental':
            slab_income += amount * 0.7
        elif inc_type in ['salary', 'business', 'interest', 'dividend', 'freelance', 'pension', 'custom']:
            slab_income += amount
        elif inc_type == 'stcg_equity':
            stcg_tax += amount * 0.15
        elif inc_type == 'ltcg_equity':
            ltcg_tax += max(0, amount - 100000) * 0.10
    
    taxable = slab_income - 75000
    slab_tax = 0
    
    if taxable <= 300000:
        slab_tax = 0
    elif taxable <= 600000:
        slab_tax = (taxable - 300000) * 0.05
    elif taxable <= 900000:
        slab_tax = 15000 + (taxable - 600000) * 0.1
    elif taxable <= 1200000:
        slab_tax = 45000 + (taxable - 900000) * 0.15
    elif taxable <= 1500000:
        slab_tax = 90000 + (taxable - 1200000) * 0.2
    else:
        slab_tax = 150000 + (taxable - 1500000) * 0.3
    
    total_tax = (slab_tax + stcg_tax + ltcg_tax) * 1.04
    return total_tax

def calculate_projections(yearly_investment, avg_return):
    r = avg_return / 100
    one_year = yearly_investment * (1 + r)
    five_years = yearly_investment * (((1 + r) ** 5 - 1) / r) * (1 + r)
    ten_years = yearly_investment * (((1 + r) ** 10 - 1) / r) * (1 + r)
    return {
        "oneYear": round(one_year),
        "fiveYears": round(five_years),
        "tenYears": round(ten_years)
    }

# ================================================================
# MAIN: INVESTMENT PLAN API
# ================================================================
@api_view(["GET", "POST"])
def generate_investment_plan(request):
    if request.method == "GET":
        return Response(
            {
                "message": "Investment Plan API",
                "method": "POST",
                "required_fields": [
                    "incomes",
                    "expectedReturn",
                    "riskAppetite",
                    "investmentMode",
                    "investmentValue",
                ],
            },
            status=200,
        )

    try:
        data = request.data
        incomes = data.get("incomes", [])
        expected_return = data.get("expectedReturn", "medium")
        risk_appetite = data.get("riskAppetite", "medium")
        investment_mode = data.get("investmentMode", "percent")
        investment_value = float(data.get("investmentValue", 30))

        # Calculate tax
        total_income = sum(float(i.get("amount", 0)) for i in incomes)
        tax = calculate_tax(incomes)
        post_tax = total_income - tax

        # Calculate investment amount
        if investment_mode == "percent":
            yearly_investment = post_tax * (investment_value / 100)
        else:
            yearly_investment = investment_value

        # Select plan based on risk and return
        plan_key = f"{risk_appetite}_{expected_return}"
        selected_plan = PREDEFINED_PLANS.get(plan_key, PREDEFINED_PLANS["medium_medium"])

        # Calculate average return
        total_return = 0
        for inst in selected_plan["allocation"]:
            returns = inst["returns"].replace("%", "").split("-")
            avg_return = (float(returns[0]) + float(returns[-1])) / 2
            total_return += (avg_return * inst["percent"]) / 100

        # Calculate projections
        projections = calculate_projections(yearly_investment, total_return)

        return Response(
            {
                "totalIncome": total_income,
                "tax": round(tax),
                "postTaxIncome": round(post_tax),
                "investmentPlan": {
                    "name": selected_plan["name"],
                    "allocation": selected_plan["allocation"],
                    "expectedReturn": selected_plan["expectedReturn"],
                    "yearlyInvestment": round(yearly_investment),
                    "monthlyInvestment": round(yearly_investment / 12),
                    "projectedReturns": projections,
                },
            },
            status=200,
        )

    except Exception as e:
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
    
# backend/api/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(["GET", "POST"])
def save_inquiry(request):
    DubaiInquiry.objects.create(**request.data)
    return Response({'status': 'success'})    
