from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import DubaiInquiry
import logging

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "healthy",
        "message": "Investment API Running",
        "mode": "rule-based"
    }, status=200)


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
        logger.error(f"Error in regenerate_allocation: {str(e)}")
        return Response({"error": str(e)}, status=500)


# ================================================================
# INVESTMENT PLAN GENERATOR
# ================================================================
def calculate_tax(incomes):
    slab_income = 0.0
    stcg_tax = 0.0
    ltcg_tax = 0.0

    income_types = {
        "rental": {"deduction": 0.30},
    }

    # -------------------------------
    # Classify income
    # -------------------------------
    for inc in incomes:
        amount = float(inc.get("amount", 0))
        inc_type = inc.get("type")

        if inc_type == "stcg_equity":
            # Section 111A
            stcg_tax += amount * 0.15

        elif inc_type == "ltcg_equity":
            # Section 112A
            taxable_ltcg = max(0, amount - 100000)
            ltcg_tax += taxable_ltcg * 0.10

        else:
            deduction = income_types.get(inc_type, {}).get("deduction", 0)
            slab_income += amount * (1 - deduction)

    # -------------------------------
    # Standard deduction (salary / pension)
    # -------------------------------
    STANDARD_DEDUCTION = 75000
    taxable_for_slab = max(0, slab_income - STANDARD_DEDUCTION)

    # -------------------------------
    # New Tax Regime Slabs (AY 2026-27)
    # -------------------------------
    slab_tax = 0.0

    if taxable_for_slab <= 400000:
        slab_tax = 0

    elif taxable_for_slab <= 800000:
        slab_tax = (taxable_for_slab - 400000) * 0.05

    elif taxable_for_slab <= 1200000:
        slab_tax = (400000 * 0.05) + (taxable_for_slab - 800000) * 0.10

    elif taxable_for_slab <= 1600000:
        slab_tax = (
            (400000 * 0.05) +
            (400000 * 0.10) +
            (taxable_for_slab - 1200000) * 0.15
        )

    elif taxable_for_slab <= 2000000:
        slab_tax = (
            (400000 * 0.05) +
            (400000 * 0.10) +
            (400000 * 0.15) +
            (taxable_for_slab - 1600000) * 0.20
        )

    elif taxable_for_slab <= 2400000:
        slab_tax = (
            (400000 * 0.05) +
            (400000 * 0.10) +
            (400000 * 0.15) +
            (400000 * 0.20) +
            (taxable_for_slab - 2000000) * 0.25
        )

    else:
        slab_tax = (
            (400000 * 0.05) +
            (400000 * 0.10) +
            (400000 * 0.15) +
            (400000 * 0.20) +
            (400000 * 0.25) +
            (taxable_for_slab - 2400000) * 0.30
        )

    # -------------------------------
    # Section 87A rebate (ONLY slab tax)
    # -------------------------------
    if taxable_for_slab <= 1200000:
        slab_tax = 0.0

    # -------------------------------
    # Total tax + cess
    # -------------------------------
    total_tax = slab_tax + stcg_tax + ltcg_tax
    total_tax *= 1.04  # 4% Health & Education Cess

    total_income = sum(float(i.get("amount", 0)) for i in incomes)

    return {
        "total_income": round(total_income, 2),
        "slab_tax": round(slab_tax, 2),
        "stcg_tax": round(stcg_tax, 2),
        "ltcg_tax": round(ltcg_tax, 2),
        "total_tax": round(total_tax, 2),
        "post_tax_income": round(total_income - total_tax, 2),
    }


def generate_allocation(risk_appetite, expected_return):
    portfolios = {
        ('low', 'low'): [
            {'name': 'Fixed Deposits', 'percent': 40, 'returns': '6-7%', 'risk': 'Low'},
            {'name': 'Debt Mutual Funds', 'percent': 30, 'returns': '7-8%', 'risk': 'Low'},
            {'name': 'PPF', 'percent': 20, 'returns': '7.1%', 'risk': 'Low'},
            {'name': 'Gold ETF', 'percent': 10, 'returns': '8-10%', 'risk': 'Low'}
        ],
        ('low', 'medium'): [
            {'name': 'Debt Mutual Funds', 'percent': 40, 'returns': '7-8%', 'risk': 'Low'},
            {'name': 'Balanced Advantage Fund', 'percent': 30, 'returns': '9-11%', 'risk': 'Medium'},
            {'name': 'Nifty 50 Index Fund', 'percent': 20, 'returns': '11-13%', 'risk': 'Medium'},
            {'name': 'Gold ETF', 'percent': 10, 'returns': '8-10%', 'risk': 'Low'}
        ],
        ('medium', 'medium'): [
            {'name': 'Nifty 50 Index Fund', 'percent': 35, 'returns': '11-14%', 'risk': 'Medium'},
            {'name': 'Debt Mutual Funds', 'percent': 25, 'returns': '7-8%', 'risk': 'Low'},
            {'name': 'Mid Cap Funds', 'percent': 20, 'returns': '13-16%', 'risk': 'High'},
            {'name': 'Gold ETF', 'percent': 15, 'returns': '8-12%', 'risk': 'Low'},
            {'name': 'International ETF', 'percent': 5, 'returns': '10-15%', 'risk': 'Medium'}
        ],
        ('medium', 'high'): [
            {'name': 'Nifty 50 Index Fund', 'percent': 30, 'returns': '11-14%', 'risk': 'Medium'},
            {'name': 'Mid Cap Funds', 'percent': 25, 'returns': '13-16%', 'risk': 'High'},
            {'name': 'Flexi Cap Fund', 'percent': 20, 'returns': '12-15%', 'risk': 'Medium'},
            {'name': 'Debt Mutual Funds', 'percent': 15, 'returns': '7-8%', 'risk': 'Low'},
            {'name': 'International ETF', 'percent': 10, 'returns': '10-15%', 'risk': 'Medium'}
        ],
        ('high', 'high'): [
            {'name': 'Mid Cap Funds', 'percent': 30, 'returns': '13-18%', 'risk': 'High'},
            {'name': 'Small Cap Funds', 'percent': 25, 'returns': '15-20%', 'risk': 'High'},
            {'name': 'Nifty 50 Index Fund', 'percent': 20, 'returns': '11-14%', 'risk': 'Medium'},
            {'name': 'Sectoral Funds', 'percent': 15, 'returns': '14-20%', 'risk': 'High'},
            {'name': 'Debt Mutual Funds', 'percent': 10, 'returns': '7-8%', 'risk': 'Low'}
        ]
    }
    
    key = (risk_appetite, expected_return)
    allocation = portfolios.get(key, portfolios[('medium', 'medium')])
    
    return allocation

@api_view(["GET", "POST"])
def generate_investment_plan(request):
    if request.method == "GET":
        return Response({
            "message": "Investment Plan API",
            "method": "POST",
            "required_fields": ["incomes", "expectedReturn", "riskAppetite", "investmentMode", "investmentValue"]
        })
    
    try:
        data = request.data
        incomes = data.get('incomes', [])
        
        if not incomes:
            return Response({'error': 'No income sources provided'}, status=400)
        
        tax_data = calculate_tax(incomes)
        
        if data.get('investmentMode') == 'percent':
            inv_amount = tax_data['post_tax_income'] * (float(data.get('investmentValue', 30)) / 100)
        else:
            inv_amount = float(data.get('investmentValue', 0))
        
        allocation = generate_allocation(
            data.get('riskAppetite', 'medium'),
            data.get('expectedReturn', 'medium')
        )
        
        returns_str = allocation[0]['returns']
        returns = returns_str.replace('%', '').split('-')
        avg_return = (float(returns[0]) + float(returns[-1])) / 200
        
        projected_returns = {
            'oneYear': round(inv_amount * (1 + avg_return)),
            'fiveYears': round(inv_amount * (((1 + avg_return) ** 5 - 1) / avg_return) * (1 + avg_return)),
            'tenYears': round(inv_amount * (((1 + avg_return) ** 10 - 1) / avg_return) * (1 + avg_return))
        }
        
        return Response({
            'totalIncome': round(tax_data['total_income']),
            'tax': round(tax_data['total_tax']),
            'postTaxIncome': round(tax_data['post_tax_income']),
            'investmentPlan': {
                'name': f"{data.get('riskAppetite', 'Medium').title()} Risk Portfolio",
                'expectedReturn': f"{int(avg_return * 100)}-{int(avg_return * 100) + 3}%",
                'yearlyInvestment': round(inv_amount),
                'monthlyInvestment': round(inv_amount / 12),
                'allocation': allocation,
                'projectedReturns': projected_returns
            }
        })
    
    except Exception as e:
        logger.error(f"Error generating plan: {str(e)}")
        return Response({'error': str(e)}, status=500)
    
# backend/api/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(["GET", "POST"])
def save_inquiry(request):
    DubaiInquiry.objects.create(**request.data)
    return Response({'status': 'success'})    
