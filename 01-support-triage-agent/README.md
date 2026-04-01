# Customer Support Triage Agent

A Claude-powered routing workflow that classifies incoming customer messages by category and urgency, then routes them to appropriate response templates.

Built as a **CCA Portfolio Project** demonstrating Domain 1 (Agentic Architecture & Orchestration) concepts.

## Architecture

```
Customer Message
       │
       ▼
┌──────────────┐
│  Classifier  │  ← Claude API call with classification system prompt
│  (Claude)    │     Returns: { category, urgency, summary }
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Router     │  ← Pure code — maps classification to template
│   (Code)     │     No Claude involved
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Template    │  ← Pre-written response filled with summary
│  (Response)  │     9 templates: 3 categories × 3 urgency levels
└──────────────┘
```

**This is a routing workflow, not an agent.** Claude classifies the input (one API call, no loop), and code handles all routing decisions. The developer controls the flow — Claude never decides what to do next.

## Why This Architecture?

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Agent vs Workflow? | **Workflow** | Every step is predictable — no need for Claude to loop or make autonomous decisions |
| Which pattern? | **Routing** | Different input types (billing/technical/general) need different handling |
| Who classifies? | **Claude** | Natural language understanding required to interpret customer intent |
| Who routes? | **Code** | Deterministic mapping from category → template. Code is guaranteed; prompts are not |

## Setup

```bash
# 1. Clone and navigate
cd cca-portfolio/01-support-triage-agent

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install anthropic python-dotenv

# 4. Add your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Run the triage agent
python triage_agent.py

# 6. Run the test suite
python test_cases.py
```

## Files

| File | Purpose |
|------|---------|
| `triage_agent.py` | Main script — classifier, router, templates, and triage pipeline |
| `test_cases.py` | 12 test messages with expected classifications and accuracy reporting |
| `.env.example` | Template for environment variables |
| `README.md` | This file |

## CCA Exam Concepts Demonstrated

- **Routing Pattern** (Domain 1): Classifier dispatches to the right handler based on input type
- **Workflow vs Agent** (Domain 1): Predictable steps with code-controlled flow = workflow
- **System Prompt Design** (Domain 4): Structured classification prompt with JSON output constraint
- **Error Handling** (Domain 1): try/except with safe fallback when classification fails
- **Evaluation Pipeline** (Domain 4): Systematic testing with expected vs actual comparison
- **Tool Schema Thinking** (Domain 2): The classification prompt mirrors tool definition design — clear inputs, structured outputs

## Example Output

```
============================================================
MESSAGE 1: I was charged twice for my subscription this month. I need a refund immediately!
============================================================

Category: billing
Urgency:  high
Summary:  Customer reports being double-charged for subscription and requests immediate refund

RESPONSE:
URGENT — Billing Issue

Thank you for contacting us. We take billing discrepancies very seriously.
A billing specialist has been notified and will review your account within
1 hour. If you were incorrectly charged, a refund will be processed within
2-3 business days.
```

## What I Learned

This project reinforced the difference between agents and workflows. The classifier could theoretically be an agent that loops and asks follow-up questions — but that would be over-engineering. The customer sends a message, we classify it, we respond. One pass, predictable flow, reliable output. That's a workflow.

The routing pattern is the most practical Domain 1 concept — it appears everywhere from customer support to content moderation to email sorting. The key insight: the classifier is a single Claude call, but the routing logic is pure code. You never want Claude deciding which template to use when a dictionary lookup is guaranteed to work.

---

*Built as part of the Claude Certified Architect (CCA) Foundations study plan.*
