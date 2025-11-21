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
# MAIN: INVESTMENT PLAN API
# ================================================================
@api_view(["GET", "POST"])
def generate_investment_plan(request):

    # -------------------------------------------------------------
    # GET (simple API info)
    # -------------------------------------------------------------
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

    print("\n================= API HIT =================")
    print("AI_ENABLED =", AI_ENABLED)
    print("Request Body:", request.data)
    print("===========================================\n")

    # -------------------------------------------------------------
    # AI MODE ENABLED
    # -------------------------------------------------------------
    if AI_ENABLED:
        serializer = InvestmentRequestSerializer(data=request.data)

        if not serializer.is_valid():
            print("❌ Serializer errors:", serializer.errors)
            return Response(serializer.errors, status=400)

        try:
            print("🚀 Running AI Crew...")
            result = run_investment_advisory_crew(serializer.validated_data)
            print("✅ AI Crew Completed")
            return Response(result, status=200)

        except Exception as e:
            print("\n🔥🔥 AI ERROR 🔥🔥")
            traceback.print_exc()
            print("🔥🔥 END ERROR 🔥🔥\n")

            return Response(
                {"error": "AI processing failed", "detail": str(e)},
                status=500,
            )

    # -------------------------------------------------------------
    # FALLBACK PLAN (AI_DISABLED)
    # -------------------------------------------------------------
    try:
        data = request.data

        total_income = sum(float(i.get("amount", 0)) for i in data.get("incomes", []))
        tax = total_income * 0.20
        post_tax = total_income - tax

        if data.get("investmentMode") == "percent":
            inv_amount = post_tax * (data.get("investmentValue", 30) / 100)
        else:
            inv_amount = data.get("investmentValue", 30)

        return Response(
            {
                "totalIncome": total_income,
                "tax": tax,
                "postTaxIncome": post_tax,
                "fallback": "AI disabled — returned simple calculation",
                "yearlyInvestment": inv_amount,
            }
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
