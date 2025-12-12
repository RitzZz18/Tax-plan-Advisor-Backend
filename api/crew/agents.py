from crewai import Agent
import os

os.environ["GEMINI_API_KEY"] = os.getenv('GEMINI_API_KEY')

# Use string format that CrewAI recognizes
llm_config = {
    "model": "gemini/gemini-1.5-flash",
    "api_key": os.getenv('GEMINI_API_KEY')
}

market_research_agent = Agent(
    role='Market Research Analyst',
    goal='Analyze market trends and provide investment insights based on current market conditions',
    backstory="""You are an experienced market analyst specializing in Indian markets. 
    You provide detailed analysis of market conditions, sector performance, and investment opportunities.""",
    tools=[],
    llm="gemini/gemini-1.5-flash-002",
    verbose=True,
    allow_delegation=False,
    max_iter=3,
    memory=True
)

tax_calculator_agent = Agent(
    role='Tax Calculation Expert',
    goal='Calculate accurate tax liability based on Indian tax laws',
    backstory='Expert in Indian Income Tax Act with deep knowledge of tax slabs, deductions, and various income types',
    llm="gemini/gemini-1.5-flash-002",
    verbose=True,
    allow_delegation=False
)

investment_strategist_agent = Agent(
    role='Dynamic Investment Strategy Advisor',
    goal='Create investment portfolios that capitalize on current market opportunities identified through real-time research',
    backstory="""You are an investment strategist who creates portfolios based on CURRENT market conditions. 
    You never use generic allocations. You always base your recommendations on the latest market 
    research provided to you. You adapt strategies in real-time based on what's actually 
    happening in markets today, not historical patterns.""",
    llm="gemini/gemini-1.5-flash-002",
    verbose=True,
    allow_delegation=True,
    max_iter=3,
    memory=True
)

portfolio_optimizer_agent = Agent(
    role='Market-Driven Portfolio Optimizer',
    goal='Optimize portfolios based on current market research to maximize returns while managing risk',
    backstory="""You are a portfolio optimizer who creates allocations based on CURRENT market trends. 
    You use the latest market research to optimize portfolios, ensuring they capitalize on 
    today's opportunities while maintaining appropriate risk levels. You always provide 
    specific fund names and current market-based rationale.""",
    llm="gemini/gemini-1.5-flash-002",
    verbose=True,
    allow_delegation=False,
    max_iter=2,
    memory=True
)
