from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
from crewai_tools import SerperDevTool
import os

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=os.getenv('GEMINI_API_KEY'))
search_tool = SerperDevTool(api_key=os.getenv('SERPER_API_KEY'))

market_research_agent = Agent(
    role='Real-Time Market Research Analyst',
    goal='Search and analyze LIVE market data to provide current investment insights based on today\'s market conditions',
    backstory="""You are a market analyst who MUST use search tools to get real-time data. 
    You NEVER provide generic responses. You always search for current market data first, 
    then analyze the actual results. You specialize in Indian markets but always verify 
    current conditions through web search before making any recommendations.""",
    tools=[search_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=5,
    memory=True
)

tax_calculator_agent = Agent(
    role='Tax Calculation Expert',
    goal='Calculate accurate tax liability based on Indian tax laws',
    backstory='Expert in Indian Income Tax Act with deep knowledge of tax slabs, deductions, and various income types',
    llm=llm,
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
    llm=llm,
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
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=2,
    memory=True
)
