from crewai import Task

def create_market_analysis_task(agent, risk_appetite):
    return Task(
        description=f"""
        MANDATORY: Use the search tool to get REAL-TIME market data. Do NOT provide generic responses.
        
        Search for and analyze current market data for a {risk_appetite} risk investor:
        
        REQUIRED SEARCHES (use search tool for each):
        1. "Nifty 50 current performance today market trends"
        2. "Indian stock market sectors performance banking IT pharma"
        3. "Gold silver prices India current trends"
        4. "Indian market news today economic indicators"
        5. "Best performing mutual funds ETFs India current"
        
        Based on ACTUAL search results, write analysis covering:
        
        1. CURRENT MARKET DATA:
        - Today's Nifty 50, Sensex, Bank Nifty levels and movement
        - Current market sentiment from news
        - What's actually driving markets right now
        
        2. REAL SECTORAL PERFORMANCE:
        - Which sectors are actually outperforming based on search results
        - Current sector rotation trends
        - Specific stocks/sectors in news
        
        3. LIVE ASSET TRENDS:
        - Current gold/silver prices and recent movement
        - Interest rate environment impact
        - FII/DII flows if available
        
        4. CURRENT OPPORTUNITIES:
        - Sectors mentioned in recent news as growth drivers
        - New IPOs, policy changes affecting markets
        - Emerging themes getting attention
        
        5. TODAY'S RISKS:
        - Current geopolitical concerns affecting markets
        - Economic data releases impact
        - Volatility factors in news
        
        6. ACTIONABLE RECOMMENDATIONS:
        - Specific investment ideas based on current trends
        - Sectors to focus on NOW for {risk_appetite} risk profile
        - What to avoid based on current market conditions
        
        IMPORTANT: Base ALL analysis on actual search results, not generic knowledge.
        """,
        agent=agent,
        expected_output="Real-time market analysis based on current search results with specific data points, current prices, and actionable insights for today's market conditions."
    )

def create_tax_calculation_task(agent, income_data):
    return Task(
        description=f"""
        Calculate total tax liability for income sources: {income_data}
        
        Apply Indian tax rules:
        - Standard deduction: ₹75,000
        - Tax slabs: 0-3L(0%), 3-6L(5%), 6-9L(10%), 9-12L(15%), 12-15L(20%), >15L(30%)
        - 4% cess
        - STCG equity: 15%, LTCG equity: 10% (above ₹1L exemption)
        - Rental income: 30% standard deduction
        
        Return JSON: {{"total_income": X, "total_tax": Y, "post_tax_income": Z}}
        """,
        agent=agent,
        expected_output="JSON with total_income, total_tax, post_tax_income"
    )

def create_investment_strategy_task(agent, user_profile, market_context):
    return Task(
        description=f"""
        Create a personalized investment strategy using the REAL market research data provided.
        
        User Profile:
        - Post-tax income: ₹{user_profile['post_tax_income']:,.0f}
        - Investment amount: ₹{user_profile['investment_amount']:,.0f}
        - Expected returns: {user_profile['expected_return']}
        - Risk appetite: {user_profile['risk_appetite']}
        
        Using the current market analysis, create a strategy that:
        
        1. LEVERAGES CURRENT TRENDS:
        - Use the sectors identified as outperforming in market research
        - Align with current market momentum and opportunities
        - Consider today's market conditions and sentiment
        
        2. SPECIFIC PORTFOLIO ALLOCATION:
        Create allocation based on current market data:
        - If IT sector is performing well → include IT ETFs/funds
        - If banking is strong → include banking funds
        - If gold is trending → adjust gold allocation
        - Use ACTUAL performing sectors from market research
        
        3. RISK-APPROPRIATE SELECTION:
        For {user_profile['risk_appetite']} risk:
        - Low risk: Focus on stable, currently performing large caps
        - Medium risk: Mix of current winners with some growth bets
        - High risk: Aggressive allocation to trending sectors and themes
        
        4. CURRENT MARKET POSITIONING:
        - Position for identified opportunities from market research
        - Avoid sectors/assets flagged as risky in current analysis
        - Time entry based on current market conditions
        
        Provide specific fund names, percentages, and rationale based on TODAY'S market conditions.
        """,
        agent=agent,
        expected_output="Investment strategy with specific allocations based on current market research, including fund names, percentages, and rationale tied to today's market conditions.",
        context=market_context
    )

def create_portfolio_optimization_task(agent, strategy_context):
    return Task(
        description=f"""
        Based on market research, create a CUSTOM portfolio allocation from available instruments.
        
        AVAILABLE INVESTMENT INSTRUMENTS (choose based on market conditions):
        
        EQUITY (High Growth):
        - Nifty 50 Index Fund (11-14% returns, Medium risk)
        - AI & Technology ETF (14-20% returns, High risk)
        - Mid Cap Funds (13-16% returns, High risk)
        - Small Cap Funds (16-20% returns, Very High risk)
        - Large Cap Funds (12-14% returns, Medium risk)
        - Flexi Cap Fund (12-15% returns, Medium risk)
        
        SECTORAL (Thematic):
        - Defense Sector Fund (13-17% returns, Medium risk)
        - Banking Sector ETF (12-15% returns, Medium risk)
        - IT Sector Fund (13-17% returns, High risk)
        - Pharma Sector Fund (11-15% returns, Medium risk)
        - Auto Sector Fund (12-16% returns, High risk)
        - Infrastructure & PSU ETF (11-14% returns, Medium risk)
        - Healthcare & Biotech Fund (11-15% returns, Medium risk)
        - EV & Mobility Fund (14-18% returns, High risk)
        - Semiconductor ETF (15-19% returns, High risk)
        - Green Energy/ESG Fund (12-16% returns, Medium risk)
        - FMCG Sector Fund (10-13% returns, Low risk)
        
        DEBT (Stability):
        - Debt Mutual Funds (7-8% returns, Low risk)
        - Fixed Deposits (6.5-7.5% returns, Very Low risk)
        - PPF (7.1% returns, Very Low risk)
        - Arbitrage Fund (6-7% returns, Very Low risk)
        - Balanced Advantage Fund (9-11% returns, Low risk)
        
        COMMODITIES:
        - Sovereign Gold Bonds (9-13% returns, Low risk)
        - Gold ETF (8-12% returns, Low risk)
        - Silver ETF (9-13% returns, Low risk)
        - Commodity ETFs (10-15% returns, Medium risk)
        
        ALTERNATIVE:
        - REITs (8-10% returns, Low risk)
        - Cryptocurrency (15-60% returns, Extreme risk)
        
        YOUR TASK:
        1. Analyze current market research to identify trending sectors
        2. Select 5-8 instruments that match:
           - Current market opportunities
           - User's risk appetite
           - User's expected returns
        3. Allocate percentages (must total 100%)
        4. Prioritize currently performing sectors from market data
        
        Return ONLY valid JSON:
        {{
            "name": "AI Market-Driven Strategy",
            "allocation": [
                {{"name": "<instrument>", "percent": <number>, "returns": "<range>%", "risk": "<level>"}}
            ],
            "expected_return": "<range>%",
            "reasoning": "Brief explanation of why these instruments based on current market"
        }}
        
        CRITICAL: Choose instruments dynamically based on TODAY's market conditions, not generic templates.
        """,
        agent=agent,
        expected_output="Pure JSON with dynamic allocation based on current market research",
        context=strategy_context
    )
