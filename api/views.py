from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import os
import logging

logger = logging.getLogger(__name__)

# Check if AI is enabled
AI_ENABLED = os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_API_KEY') != 'your_gemini_api_key_here'

if AI_ENABLED:
    try:
        from .serializers import InvestmentRequestSerializer
        from .crew.crew import run_investment_advisory_crew
    except ImportError:
        AI_ENABLED = False

@api_view(['GET'])
def health_check(request):
    ai_status = 'disabled'
    ai_packages = {}
    
    if AI_ENABLED:
        ai_status = 'enabled'
        try:
            import crewai
            import langchain_google_genai
            import google.generativeai
            ai_packages = {
                'crewai': 'installed',
                'langchain_google_genai': 'installed',
                'google_generativeai': 'installed'
            }
        except ImportError as e:
            ai_status = 'error'
            ai_packages = {'error': str(e)}
    
    return Response({
        'status': 'healthy',
        'message': 'AI Advisory API is running',
        'ai_enabled': AI_ENABLED,
        'ai_status': ai_status,
        'ai_packages': ai_packages
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def regenerate_allocation(request):
    """Regenerate allocation when user removes instruments"""
    try:
        excluded_instruments = request.data.get('excludedInstruments', [])
        current_allocation = request.data.get('currentAllocation', [])
        user_profile = request.data.get('userProfile', {})
        
        # Keep non-excluded instruments
        remaining = [inst.copy() for inst in current_allocation if inst['name'] not in excluded_instruments]
        
        if len(remaining) == 0:
            return Response({'error': 'Cannot remove all instruments'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Redistribute percentages
        total = sum(inst['percent'] for inst in remaining)
        for inst in remaining:
            inst['percent'] = round((inst['percent'] / total) * 100)
        
        # Fix rounding to ensure 100%
        current_total = sum(inst['percent'] for inst in remaining)
        if current_total != 100:
            remaining[0]['percent'] += (100 - current_total)
        
        result = {
            'newAllocation': remaining,
            'reasoning': f"Removed {', '.join(excluded_instruments)}. Redistributed allocation among remaining instruments."
        }
        
        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error regenerating allocation: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
def generate_investment_plan(request):
    if request.method == 'GET':
        return Response({
            'message': 'Investment Plan API',
            'method': 'POST',
            'required_fields': ['incomes', 'expectedReturn', 'riskAppetite', 'investmentMode', 'investmentValue']
        })
    
    if AI_ENABLED:
        # Use AI-powered analysis
        serializer = InvestmentRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            logger.info("Starting AI investment advisory crew...")
            result = run_investment_advisory_crew(serializer.validated_data)
            logger.info("Crew execution completed successfully")
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error in crew execution: {str(e)}")
            return Response(
                {'error': f'AI analysis failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    else:
        # AI disabled - return text-based analysis
        data = request.data
        
        total_income = sum(float(inc.get('amount', 0)) for inc in data.get('incomes', []))
        tax = total_income * 0.2
        post_tax = total_income - tax
        
        investment_value = data.get('investmentValue', 30)
        if data.get('investmentMode') == 'percent':
            investment_amount = post_tax * (investment_value / 100)
        else:
            investment_amount = investment_value
        
        risk = data.get('riskAppetite', 'medium')
        expected_return = data.get('expectedReturn', 'medium')
        
        # Generate AI-style text response
        risk_analysis = {
            'low': 'Conservative approach focusing on capital preservation with minimal volatility. Suitable for investors nearing retirement or those who cannot afford losses.',
            'medium': 'Balanced approach balancing growth and stability. Ideal for investors with 5-10 year investment horizon who can tolerate moderate fluctuations.',
            'high': 'Aggressive growth strategy accepting high volatility for potentially superior returns. Best for young investors with long-term horizon and high risk tolerance.'
        }
        
        return_analysis = {
            'low': 'Targeting 7-10% annual returns through stable instruments like debt funds, FDs, and government securities.',
            'medium': 'Aiming for 10-14% returns through diversified equity and debt allocation with focus on large-cap stability.',
            'high': 'Pursuing 15-20% returns via growth-oriented investments including mid-cap, small-cap, and thematic opportunities.'
        }
        
        investment_strategy = f"""
        INVESTMENT ANALYSIS FOR ₹{investment_amount:,.0f} ANNUAL INVESTMENT
        
        RISK PROFILE ASSESSMENT:
        Your {risk.upper()} risk appetite indicates: {risk_analysis[risk]}
        
        RETURN EXPECTATIONS:
        With {expected_return.upper()} return expectations: {return_analysis[expected_return]}
        
        MARKET OUTLOOK:
        Current market conditions suggest a cautious optimism approach. Indian markets are showing resilience with strong domestic consumption and government infrastructure spending. However, global uncertainties and inflation concerns warrant careful asset selection.
        
        RECOMMENDED STRATEGY:
        Based on your profile, a diversified approach across equity (60-70%), debt (20-30%), and alternative investments (5-10%) would be optimal. Focus on systematic investment plans (SIP) to benefit from rupee cost averaging.
        
        RISK MITIGATION:
        - Diversify across market capitalizations and sectors
        - Maintain emergency fund equivalent to 6-12 months expenses
        - Review and rebalance portfolio quarterly
        - Consider tax-efficient instruments like ELSS for Section 80C benefits
        
        PROJECTED OUTCOMES:
        With disciplined investing and market-average performance:
        - 1 Year: ₹{investment_amount * 1.12:,.0f} (12% growth)
        - 5 Years: ₹{investment_amount * 6.8:,.0f} (compound growth)
        - 10 Years: ₹{investment_amount * 18.5:,.0f} (long-term wealth creation)
        
        IMPORTANT DISCLAIMERS:
        Past performance doesn't guarantee future results. Market investments are subject to risks. Consult a financial advisor for personalized advice. Consider your financial goals, time horizon, and risk capacity before investing.
        """
        
        # Generate allocation based on risk and expected return
        key = f"{expected_return}-{risk}"
        allocations = {
            'low-low': [{'name': 'Fixed Deposits', 'percent': 30, 'returns': '6.5-7.5%', 'risk': 'Very Low'}, {'name': 'PPF', 'percent': 25, 'returns': '7.1%', 'risk': 'Very Low'}, {'name': 'Debt Mutual Funds', 'percent': 20, 'returns': '7-8%', 'risk': 'Low'}, {'name': 'Gold ETF', 'percent': 15, 'returns': '8-12%', 'risk': 'Low'}, {'name': 'Silver ETF', 'percent': 10, 'returns': '9-13%', 'risk': 'Low'}],
            'low-medium': [{'name': 'Debt Mutual Funds', 'percent': 25, 'returns': '7-8%', 'risk': 'Low'}, {'name': 'Nifty 50 ETF', 'percent': 25, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'PPF', 'percent': 20, 'returns': '7.1%', 'risk': 'Very Low'}, {'name': 'Gold ETF', 'percent': 15, 'returns': '8-12%', 'risk': 'Low'}, {'name': 'REITs', 'percent': 10, 'returns': '8-10%', 'risk': 'Low'}, {'name': 'Bank Nifty ETF', 'percent': 5, 'returns': '12-15%', 'risk': 'Medium'}],
            'low-high': [{'name': 'Nifty 50 ETF', 'percent': 30, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Large Cap Funds', 'percent': 25, 'returns': '12-14%', 'risk': 'Medium'}, {'name': 'Debt Mutual Funds', 'percent': 20, 'returns': '7-8%', 'risk': 'Low'}, {'name': 'Gold ETF', 'percent': 15, 'returns': '8-12%', 'risk': 'Low'}, {'name': 'Mid Cap Funds', 'percent': 10, 'returns': '13-16%', 'risk': 'High'}],
            'medium-low': [{'name': 'Nifty 50 ETF', 'percent': 30, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Debt Mutual Funds', 'percent': 20, 'returns': '7-8%', 'risk': 'Low'}, {'name': 'Large Cap Funds', 'percent': 20, 'returns': '12-14%', 'risk': 'Medium'}, {'name': 'Gold ETF', 'percent': 15, 'returns': '8-12%', 'risk': 'Low'}, {'name': 'REITs', 'percent': 10, 'returns': '8-10%', 'risk': 'Low'}, {'name': 'Silver ETF', 'percent': 5, 'returns': '9-13%', 'risk': 'Low'}],
            'medium-medium': [{'name': 'Nifty 50 ETF', 'percent': 25, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Large Cap Funds', 'percent': 20, 'returns': '12-14%', 'risk': 'Medium'}, {'name': 'Mid Cap Funds', 'percent': 20, 'returns': '13-16%', 'risk': 'High'}, {'name': 'Bank Nifty ETF', 'percent': 15, 'returns': '12-15%', 'risk': 'Medium'}, {'name': 'Gold ETF', 'percent': 10, 'returns': '8-12%', 'risk': 'Low'}, {'name': 'REITs', 'percent': 10, 'returns': '8-10%', 'risk': 'Low'}],
            'medium-high': [{'name': 'Mid Cap Funds', 'percent': 25, 'returns': '13-16%', 'risk': 'High'}, {'name': 'Nifty 50 ETF', 'percent': 20, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Small Cap Funds', 'percent': 20, 'returns': '16-20%', 'risk': 'Very High'}, {'name': 'Bank Nifty ETF', 'percent': 15, 'returns': '12-15%', 'risk': 'Medium'}, {'name': 'Thematic ETFs (IT/Pharma)', 'percent': 10, 'returns': '13-17%', 'risk': 'High'}],
            'high-low': [{'name': 'Nifty 50 ETF', 'percent': 30, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Large Cap Funds', 'percent': 25, 'returns': '12-14%', 'risk': 'Medium'}, {'name': 'Mid Cap Funds', 'percent': 20, 'returns': '13-16%', 'risk': 'High'}, {'name': 'Bank Nifty ETF', 'percent': 15, 'returns': '12-15%', 'risk': 'Medium'}, {'name': 'Gold ETF', 'percent': 10, 'returns': '8-12%', 'risk': 'Low'}],
            'high-medium': [{'name': 'Mid Cap Funds', 'percent': 25, 'returns': '13-16%', 'risk': 'High'}, {'name': 'Small Cap Funds', 'percent': 20, 'returns': '16-20%', 'risk': 'Very High'}, {'name': 'Nifty 50 ETF', 'percent': 20, 'returns': '11-14%', 'risk': 'Medium'}, {'name': 'Thematic ETFs (AI/EV)', 'percent': 15, 'returns': '14-18%', 'risk': 'High'}, {'name': 'Bank Nifty ETF', 'percent': 10, 'returns': '12-15%', 'risk': 'Medium'}],
            'high-high': [{'name': 'Small Cap Funds', 'percent': 25, 'returns': '16-20%', 'risk': 'Very High'}, {'name': 'Mid Cap Funds', 'percent': 20, 'returns': '13-16%', 'risk': 'High'}, {'name': 'Cryptocurrency ETF/Funds', 'percent': 15, 'returns': '15-60%', 'risk': 'Extreme'}, {'name': 'Thematic ETFs (AI/EV)', 'percent': 15, 'returns': '14-18%', 'risk': 'High'}, {'name': 'Sectoral ETFs (IT/Banking)', 'percent': 10, 'returns': '13-18%', 'risk': 'High'}, {'name': 'Commodity ETFs', 'percent': 5, 'returns': '10-15%', 'risk': 'Medium'}]
        }
        
        allocation = allocations.get(key, allocations['medium-medium'])
        expected_ret = {'low-low': '7-9%', 'low-medium': '9-11%', 'low-high': '10-12%', 'medium-low': '10-12%', 'medium-medium': '11-14%', 'medium-high': '13-16%', 'high-low': '12-14%', 'high-medium': '14-17%', 'high-high': '16-24%'}
        
        return Response({
            'totalIncome': round(total_income),
            'tax': round(tax),
            'postTaxIncome': round(post_tax),
            'marketAnalysis': {'analysis': investment_strategy},
            'investmentPlan': {
                'name': f'AI {expected_return.title()}-{risk.title()} Strategy',
                'allocation': allocation,
                'expected_return': expected_ret.get(key, '11-14%'),
                'yearly_investment': round(investment_amount),
                'monthly_investment': round(investment_amount / 12),
                'projected_returns': {
                    'oneYear': round(investment_amount * 1.12),
                    'fiveYears': round(investment_amount * 6.8),
                    'tenYears': round(investment_amount * 18.5)
                }
            }
        }, status=status.HTTP_200_OK)
