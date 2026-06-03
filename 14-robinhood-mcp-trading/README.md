# Building an AI Trading Agent with Robinhood MCP

## Introduction

This lesson will cover:

- What Robinhood Agentic Trading is and how it works
- How the Model Context Protocol (MCP) enables AI agents to interact with financial platforms
- How to connect Claude to Robinhood's MCP server
- How to build a trading agent that analyzes stocks and places orders
- Safety considerations and best practices for AI-driven trading

## Learning Goals

After completing this lesson you will be able to:

- Explain what MCP is and why it is important for AI agents
- Set up the Robinhood Agentic Trading MCP connection with Claude
- Build a Claude-powered trading agent using the Anthropic SDK
- Apply a safety-first mindset when designing agentic financial workflows

## Scenario: An AI Day-Trading Research Agent

You want to learn how professional algorithmic traders use data-driven strategies. You will build a Claude-powered agent that connects to your Robinhood Agentic account, analyzes your portfolio, researches stocks, and can place trades — all while keeping you in the loop with human-in-the-loop confirmation.

## What is Robinhood Agentic Trading?

[Robinhood Agentic Trading](https://robinhood.com/us/en/agentic-trading/) (launched May 2026) is a brokerage product that lets you connect a third-party AI agent to a **dedicated, isolated Robinhood account**. Key design principles:

- **Isolation**: The agentic account is completely separate from your main portfolio. Agents can only access funds you explicitly deposit there.
- **Transparency**: You get push notifications for every trade. A real-time activity feed and P&L is visible in the Robinhood app.
- **Control**: You can pause or disconnect the agent at any time with one tap.

The connection between AI agents and Robinhood uses the **Model Context Protocol (MCP)**.

## What is MCP?

MCP (Model Context Protocol) is an open standard that lets AI agents connect to external apps and take actions — not just answer questions. Think of it like a USB-C standard for AI integrations: any MCP-compatible agent can connect to any MCP-compatible service.

```
┌─────────────────┐       MCP (HTTP)      ┌──────────────────────────┐
│   Claude Agent  │ ───────────────────▶  │  Robinhood MCP Server    │
│  (your code)    │ ◀───────────────────  │  agent.robinhood.com/mcp │
└─────────────────┘    tools + results    └──────────────────────────┘
```

Robinhood's MCP server exposes tools for:
- Querying account info (portfolio value, buying power)
- Getting stock quotes and market data
- Placing market and limit orders
- Reviewing order history

## Prerequisites

1. **Robinhood account** in good standing (individual investing account)
2. **Agentic account** — created automatically during MCP onboarding
3. **Anthropic API key** — [get one here](https://console.anthropic.com)
4. Python 3.9+ and `pip`

> **Capital risk**: Only deposit into your agentic account what you are willing to lose. AI agents can and do make mistakes.

## Setup

### 1. Install dependencies

```bash
pip install anthropic mcp python-dotenv
```

### 2. Add Robinhood MCP to Claude Code

If you are using Claude Code (the CLI), run:

```bash
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
```

Claude will then prompt you to authenticate with Robinhood and set up your agentic account.

### 3. Set up your environment file

Create a `.env` file in this directory:

```
ANTHROPIC_API_KEY=your_api_key_here
```

> Never commit your `.env` file to version control.

### 4. Run the notebook

Open `notebook-robinhood-trading.ipynb` and follow along step by step.

## How the Agent Works

```
User prompt
    │
    ▼
Claude (claude-opus-4-8)
    │  "I should check the portfolio first"
    ▼
Tool call: get_portfolio()
    │
    ▼
Robinhood MCP Server ──▶ returns portfolio JSON
    │
    ▼
Claude analyzes data
    │  "AAPL is underweight, buying power available"
    ▼
Tool call: place_order(symbol="AAPL", side="buy", qty=1)
    │
    ▼
[Human confirmation required] ──▶ User approves / rejects
    │
    ▼
Order executed (or cancelled)
```

## Safety Considerations

Before building AI trading agents, understand these risks:

| Risk | Mitigation |
|------|-----------|
| Agent places unintended trades | Always require human approval for orders |
| Strategy loses money | Start with a small amount; paper trade first |
| API errors cause duplicate orders | Implement idempotency checks |
| Pattern Day Trader (PDT) rule | Track trade count; stay under 3 round trips / 5 days unless you have $25k+ |
| Over-trading (churn) | Set daily trade limits in your agent logic |

## Assignment

After completing the notebook:

1. Modify the agent to implement a **momentum strategy**: buy stocks that have risen >2% in the past 5 days, sell stocks that have fallen >3%.
2. Add a **daily trade limit** so the agent makes at most 3 trades per day.
3. Log every decision the agent makes (buy, hold, sell) to a local CSV file for review.

## Additional Resources

- [Robinhood Agentic Trading Overview](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
- [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/tool-use)
- [MCP Specification](https://modelcontextprotocol.io)
- [GitHub: verygoodplugins/robinhood-mcp](https://github.com/verygoodplugins/robinhood-mcp) — read-only research MCP
