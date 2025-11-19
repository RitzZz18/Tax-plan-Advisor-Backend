from crewai import Crew, Process
from .agents import (
    market_research_agent, 
    tax_calculator_agent, 
    investment_strategist_agent, 
    portfolio_optimizer_agent
)
from .tasks import (
    create_market_analysis_task,
    create_tax_calculation_task, 
    create_investment_strategy_task, 
    create_portfolio_optimization_task
)
import json

def run_investment_advisory_crew(request_data):
    print("🔍 Starting real-time market research...")
    
    # Step 1: Force Real-Time Market Research
    market_task = create_market_analysis_task(
        market_research_agent, 
        request_data['riskAppetite']
    )
    
    market_crew = Crew(
        agents=[market_research_agent],
        tasks=[market_task],
        process=Process.sequential,
        verbose=True,
        memory=True
    )
    
    print(" Executing market research with live data...")
    market_result = market_crew.kickoff()
    print(f" Market research completed: {len(str(market_result))} characters of analysis")
    
    # Step 2: Tax Calculation
    tax_task = create_tax_calculation_task(
        tax_calculator_agent, 
        request_data['incomes']
    )
    
    tax_crew = Crew(
        agents=[tax_calculator_agent],
        tasks=[tax_task],
        process=Process.sequential,
        verbose=True
    )
    
    tax_result = tax_crew.kickoff()
    
    # Parse tax result with better error handling
    try:
        if isinstance(tax_result, str):
            # Try to extract JSON from string
            import re
            json_match = re.search(r'\{.*\}', tax_result, re.DOTALL)
            if json_match:
                tax_data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in tax result")
        else:
            tax_data = tax_result
    except Exception as e:
        print(f"⚠️ Tax calculation fallback: {e}")
        total_income = sum(float(inc['amount']) for inc in request_data['incomes'])
        tax_data = {
            'total_income': total_income,
            'total_tax': max(0, (total_income - 75000) * 0.2),  # Basic tax calculation
            'post_tax_income': total_income - max(0, (total_income - 75000) * 0.2)
        }
    
    # Step 3: Calculate investment amount
    investment_amount = request_data['investmentValue']
    if request_data['investmentMode'] == 'percent':
        investment_amount = tax_data['post_tax_income'] * (request_data['investmentValue'] / 100)
    
    user_profile = {
        'post_tax_income': tax_data['post_tax_income'],
        'investment_amount': investment_amount,
        'expected_return': request_data['expectedReturn'],
        'risk_appetite': request_data['riskAppetite']
    }
    
    print(f"💰 Investment profile: ₹{investment_amount:,.0f} for {request_data['riskAppetite']} risk")
    
    # Step 4: Create strategy based on market research
    strategy_task = create_investment_strategy_task(
        investment_strategist_agent, 
        user_profile,
        [market_task]
    )
    
    optimization_task = create_portfolio_optimization_task(
        portfolio_optimizer_agent,
        [strategy_task]
    )
    
    # Execute strategy and optimization with market context
    investment_crew = Crew(
        agents=[investment_strategist_agent, portfolio_optimizer_agent],
        tasks=[strategy_task, optimization_task],
        process=Process.sequential,
        verbose=True,
        memory=True
    )
    
    print("🎯 Creating market-driven investment strategy...")
    investment_result = investment_crew.kickoff()
    print(f"✅ Strategy completed: {type(investment_result)}")
    
    # Parse investment result with better handling
    try:
        if isinstance(investment_result, str):
            import re
            json_match = re.search(r'\{.*\}', investment_result, re.DOTALL)
            if json_match:
                investment_data = json.loads(json_match.group())
            else:
                investment_data = {'name': 'AI Strategy', 'allocation': [], 'expected_return': '10-15%'}
        else:
            investment_data = investment_result
    except Exception as e:
        print(f"⚠️ Parsing error: {e}")
        investment_data = {'name': 'AI Strategy', 'allocation': [], 'expected_return': '10-15%'}
    
    # Minimal fallback only if AI completely fails
    if not investment_data.get('allocation') or len(investment_data.get('allocation', [])) == 0:
        print("⚠️ AI failed to generate allocation - using minimal fallback")
        investment_data['allocation'] = [
            {'name': 'Nifty 50 Index Fund', 'percent': 40, 'returns': '11-14%', 'risk': 'Medium'},
            {'name': 'Debt Mutual Funds', 'percent': 30, 'returns': '7-8%', 'risk': 'Low'},
            {'name': 'Gold ETF', 'percent': 20, 'returns': '8-12%', 'risk': 'Low'},
            {'name': 'Mid Cap Funds', 'percent': 10, 'returns': '13-16%', 'risk': 'High'}
        ]
        investment_data['name'] = 'Balanced Portfolio (AI Fallback)'
        investment_data['expected_return'] = '9-12%'
    
    # Add investment amounts and projections
    if 'yearly_investment' not in investment_data:
        investment_data['yearly_investment'] = round(investment_amount)
    if 'monthly_investment' not in investment_data:
        investment_data['monthly_investment'] = round(investment_amount / 12)
    
    # Calculate projections if not present
    if 'projected_returns' not in investment_data:
        expected_ret = investment_data.get('expected_return', '10-15%')
        returns = expected_ret.replace('%', '').split('-')
        avg_return = (float(returns[0]) + float(returns[-1])) / 200
        investment_data['projected_returns'] = {
            'one_year': round(investment_amount * (1 + avg_return)),
            'five_years': round(investment_amount * (((1 + avg_return) ** 5 - 1) / avg_return) * (1 + avg_return)),
            'ten_years': round(investment_amount * (((1 + avg_return) ** 10 - 1) / avg_return) * (1 + avg_return))
        }
    
    # Structure final response with market insights
    market_insights = {
        'analysis': str(market_result)[:1000] + '...' if len(str(market_result)) > 1000 else str(market_result),
        'summary': 'Real-time market analysis using current data',
        'timestamp': 'Current market conditions analyzed'
    }
    
    print(f"📈 Returning AI plan: {investment_data.get('name', 'Unknown')}")
    print(f"📊 Allocations: {len(investment_data.get('allocation', []))} instruments")
    
    return {
        'totalIncome': round(tax_data['total_income']),
        'tax': round(tax_data['total_tax']),
        'postTaxIncome': round(tax_data['post_tax_income']),
        'marketAnalysis': market_insights,
        'investmentPlan': investment_data,
        'aiInsights': {
            'market_research': str(market_result),
            'strategy_reasoning': str(investment_result),
            'research_length': len(str(market_result)),
            'strategy_length': len(str(investment_result))
        }
    }


def regenerate_portfolio_allocation(excluded_instruments, current_allocation, user_profile):
    """Regenerate allocation excluding certain instruments"""
    from .agents import portfolio_optimizer_agent
    from crewai import Task, Crew, Process
    
    excluded_names = ', '.join(excluded_instruments)
    current_instruments = [inst['name'] for inst in current_allocation]
    
    task = Task(
        description=f"""
        User wants to REPLACE these instruments: {excluded_names}
        
        Current portfolio has: {', '.join(current_instruments)}
        
        User Profile:
        - Risk Appetite: {user_profile.get('riskAppetite', 'medium')}
        - Expected Returns: {user_profile.get('expectedReturn', 'medium')}
        - Investment Amount: ₹{user_profile.get('investmentAmount', 0):,.0f}
        
        AVAILABLE INSTRUMENTS (choose replacements):
        
        EQUITY: Nifty 50 Index Fund, AI & Technology ETF, Mid Cap Funds, Small Cap Funds, Large Cap Funds, Flexi Cap Fund
        
        SECTORAL: Defense Sector Fund, Banking Sector ETF, IT Sector Fund, Pharma Sector Fund, Auto Sector Fund, Infrastructure & PSU ETF, Healthcare & Biotech Fund, EV & Mobility Fund, Semiconductor ETF, Green Energy/ESG Fund, FMCG Sector Fund
        
        DEBT: Debt Mutual Funds, Fixed Deposits, PPF, Arbitrage Fund, Balanced Advantage Fund
        
        COMMODITIES: Sovereign Gold Bonds, Gold ETF, Silver ETF, Commodity ETFs
        
        ALTERNATIVE: REITs, International ETF (Nasdaq/S&P 500), Cryptocurrency/Blockchain Funds
        
        YOUR TASK:
        1. Keep instruments user didn't remove
        2. Suggest NEW instruments to replace removed ones
        3. Adjust percentages to total 100%
        4. Match user's risk and return profile
        
        Return ONLY JSON:
        {{
            "allocation": [
                {{"name": "<instrument>", "percent": <number>, "returns": "<range>%", "risk": "<level>"}}
            ],
            "reasoning": "Why these replacements"
        }}
        
        DO NOT include: {excluded_names}
        """,
        agent=portfolio_optimizer_agent,
        expected_output="JSON with new allocation excluding removed instruments"
    )
    
    crew = Crew(
        agents=[portfolio_optimizer_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True
    )
    
    result = crew.kickoff()
    
    try:
        import json, re
        if isinstance(result, str):
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {'allocation': [], 'reasoning': 'Failed to parse'}
        else:
            data = result
    except:
        data = {'allocation': [], 'reasoning': 'Error parsing result'}
    
    return {
        'newAllocation': data.get('allocation', []),
        'reasoning': data.get('reasoning', '')
    }
