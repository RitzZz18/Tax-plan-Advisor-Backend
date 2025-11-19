# 📊 Available Investment Instruments

AI can choose from these instruments based on real-time market conditions.

---

## EQUITY (High Growth Potential)

| Instrument | Returns | Risk | Best For |
|------------|---------|------|----------|
| Nifty 50 Index Fund | 11-14% | Medium | Core portfolio, market exposure |
| AI & Technology ETF | 14-20% | High | Tech boom, AI trends |
| Mid Cap Funds | 13-16% | High | Growth seekers |
| Small Cap Funds | 16-20% | Very High | Aggressive investors |
| Large Cap Funds | 12-14% | Medium | Stable growth |
| Flexi Cap Fund | 12-15% | Medium | Flexible allocation |

---

## SECTORAL (Thematic Investments)

| Instrument | Returns | Risk | Best For |
|------------|---------|------|----------|
| Defense Sector Fund | 13-17% | Medium | Defense spending boom |
| Banking Sector ETF | 12-15% | Medium | Banking sector growth |
| IT Sector Fund | 13-17% | High | Tech sector exposure |
| Pharma Sector Fund | 11-15% | Medium | Healthcare trends |
| Auto Sector Fund | 12-16% | High | Auto industry growth |
| Infrastructure & PSU ETF | 11-14% | Medium | Government spending |
| Healthcare & Biotech Fund | 11-15% | Medium | Medical innovation |
| EV & Mobility Fund | 14-18% | High | Electric vehicle boom |
| Semiconductor ETF | 15-19% | High | Chip industry growth |
| Green Energy/ESG Fund | 12-16% | Medium | Sustainability trends |
| FMCG Sector Fund | 10-13% | Low | Consumer staples |

---

## DEBT (Stability & Safety)

| Instrument | Returns | Risk | Best For |
|------------|---------|------|----------|
| Debt Mutual Funds | 7-8% | Low | Capital preservation |
| Fixed Deposits | 6.5-7.5% | Very Low | Guaranteed returns |
| PPF | 7.1% | Very Low | Tax-free returns |
| Arbitrage Fund | 6-7% | Very Low | Low-risk income |
| Balanced Advantage Fund | 9-11% | Low | Balanced approach |

---

## COMMODITIES (Inflation Hedge)

| Instrument | Returns | Risk | Best For |
|------------|---------|------|----------|
| Sovereign Gold Bonds | 9-13% | Low | Gold + interest |
| Gold ETF | 8-12% | Low | Inflation hedge |
| Silver ETF | 9-13% | Low | Industrial metal |
| Commodity ETFs | 10-15% | Medium | Diversified commodities |

---

## ALTERNATIVE (Diversification)

| Instrument | Returns | Risk | Best For |
|------------|---------|------|----------|
| REITs | 8-10% | Low | Real estate exposure |
| International ETF (Nasdaq/S&P 500) | 10-16% | Medium | Global diversification |
| Cryptocurrency/Blockchain Funds | 15-60% | Extreme | High-risk appetite |

---

## AI Selection Logic

### For LOW Risk Appetite
AI prioritizes:
- Debt Funds (30-40%)
- PPF/FD (20-30%)
- Gold (15-20%)
- Large Cap (10-20%)

### For MEDIUM Risk Appetite
AI balances:
- Nifty 50 / Large Cap (25-35%)
- Sectoral Funds (20-30%)
- Debt Funds (15-25%)
- Gold (10-15%)
- Mid Cap (5-15%)

### For HIGH Risk Appetite
AI focuses on:
- Mid/Small Cap (30-40%)
- Sectoral/Thematic (25-35%)
- AI/Tech/EV (15-25%)
- International (10-15%)
- Crypto (0-15% if extreme risk)

---

## Market Condition Examples

### Bull Market (Strong Growth)
AI might select:
- Small Cap Funds (25%)
- AI & Technology ETF (20%)
- Mid Cap Funds (20%)
- Semiconductor ETF (15%)
- Nifty 50 (15%)
- Gold (5%)

### Bear Market (Correction)
AI might select:
- Debt Mutual Funds (35%)
- Gold ETF (25%)
- Arbitrage Fund (15%)
- Large Cap Funds (15%)
- REITs (10%)

### Sector Rotation (Defense Rally)
AI might select:
- Defense Sector Fund (25%)
- Infrastructure ETF (20%)
- Banking ETF (20%)
- Nifty 50 (15%)
- Gold (12%)
- Debt Funds (8%)

### Tech Boom
AI might select:
- AI & Technology ETF (25%)
- Semiconductor ETF (20%)
- IT Sector Fund (18%)
- International Nasdaq ETF (15%)
- Mid Cap (12%)
- Gold (10%)

---

## Adding New Instruments

To add new instruments, edit `backend/api/crew/tasks.py`:

```python
SECTORAL (Thematic):
- Your New Fund Name (X-Y% returns, Risk level)
```

Then AI will automatically consider it in future recommendations!

---

## Instrument Characteristics

### High Return Potential
- Small Cap Funds (16-20%)
- AI & Technology ETF (14-20%)
- Semiconductor ETF (15-19%)
- EV & Mobility Fund (14-18%)
- Cryptocurrency (15-60%)

### Low Risk Options
- PPF (7.1%)
- Fixed Deposits (6.5-7.5%)
- Debt Mutual Funds (7-8%)
- Arbitrage Fund (6-7%)
- REITs (8-10%)

### Balanced Options
- Nifty 50 Index Fund (11-14%)
- Large Cap Funds (12-14%)
- Flexi Cap Fund (12-15%)
- Banking Sector ETF (12-15%)
- Balanced Advantage Fund (9-11%)

---

## Total Available: 40+ Instruments

AI dynamically selects **5-8 instruments** per recommendation based on:
1. Real-time market research
2. User's risk appetite
3. User's expected returns
4. Current sector performance
5. Market sentiment

**Every recommendation is unique!** 🎯
