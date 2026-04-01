"""
Customer Support Triage Agent
CCA Portfolio Project — Domain 1: Agentic Architecture & Orchestration

This is a ROUTING WORKFLOW, not an agent:
- The classifier (Claude) categorizes the message
- The router (code) sends it to the right template
- No loops, no autonomy — the developer controls the flow

Architecture: Message → Classify (Claude) → Route (Code) → Template → Response
"""

import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

# ============================================================
# SETUP — Load API key and create the Claude client
# ============================================================
load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"


# ============================================================
# SYSTEM PROMPT — Tells Claude exactly how to classify messages
# ============================================================
CLASSIFICATION_PROMPT = """You are a customer support classifier. Your job is to analyze 
incoming customer messages and return a structured classification.

For every message, determine:
1. CATEGORY: One of "billing", "technical", or "general"
2. URGENCY: One of "low", "medium", or "high"
3. SUMMARY: A one-sentence summary of the customer's issue

Classification rules:
- billing: refunds, charges, invoices, payment methods, subscription changes, pricing
- technical: bugs, errors, crashes, API issues, integration problems, performance
- general: feature questions, how-to, account info, feedback, general inquiries

Urgency rules:
- high: service is DOWN, money was lost/charged incorrectly, security concern, data loss
- medium: feature not working but workaround exists, billing question about upcoming charge
- low: general question, feedback, feature request, how-to inquiry

Respond with ONLY valid JSON in this exact format, no other text:
{"category": "billing", "urgency": "high", "summary": "Customer was double-charged"}"""


# ============================================================
# RESPONSE TEMPLATES — Pre-written responses for each category
# ============================================================
TEMPLATES = {
    "billing": {
        "high": "URGENT — Billing Issue\n\nThank you for contacting us. We take billing discrepancies very seriously. A billing specialist has been notified and will review your account within 1 hour. If you were incorrectly charged, a refund will be processed within 2-3 business days.\n\nReference: {summary}",

        "medium": "Billing Inquiry\n\nThank you for reaching out about your billing concern. Our billing team will review your account and respond within 24 hours. You can also view your billing history in Account Settings > Billing.\n\nReference: {summary}",

        "low": "Billing Information\n\nThank you for your billing question. You can find most billing information in Account Settings > Billing. Our team is available if you need additional help.\n\nReference: {summary}",
    },
    "technical": {
        "high": "URGENT — Technical Issue\n\nWe understand you're experiencing a critical technical issue. Our engineering team has been alerted and is investigating. For immediate workarounds, please check our status page at status.example.com.\n\nReference: {summary}",

        "medium": "Technical Support\n\nThank you for reporting this technical issue. Our support team will investigate and respond within 24 hours. In the meantime, please try clearing your cache or using an incognito window.\n\nReference: {summary}",

        "low": "Technical Question\n\nThank you for your technical question. You may find the answer in our documentation at docs.example.com. If not, our team will follow up within 48 hours.\n\nReference: {summary}",
    },
    "general": {
        "high": "Priority Inquiry\n\nThank you for reaching out. We've flagged your message as high priority and a team member will respond shortly.\n\nReference: {summary}",

        "medium": "General Inquiry\n\nThank you for contacting us. A team member will review your message and respond within 24-48 hours.\n\nReference: {summary}",

        "low": "General Information\n\nThank you for reaching out! Check out our FAQ at help.example.com for quick answers. Our team is also happy to help if you need anything else.\n\nReference: {summary}",
    },
}


# ============================================================
# CLASSIFIER — Sends the message to Claude for classification
# ============================================================
def classify_message(customer_message):
    """
    Takes a customer message, sends it to Claude with the classification
    system prompt, and returns structured classification data.
    
    This is a single API call — no loop, no agent. Claude classifies
    and returns JSON. Our code parses and uses it.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=CLASSIFICATION_PROMPT,
        messages=[
            {"role": "user", "content": customer_message}
        ]
    )

    # Parse Claude's JSON response
    try:
        classification = json.loads(response.content[0].text)
        return classification
    except json.JSONDecodeError:
        # If Claude doesn't return valid JSON, return a safe default
        return {
            "category": "general",
            "urgency": "medium",
            "summary": "Unable to classify — routing to general support"
        }


# ============================================================
# ROUTER — Maps classification to the right response template
# ============================================================
def route_to_template(classification):
    """
    Takes the classification dict and selects the correct response
    template. This is pure code — no Claude involved.
    
    This is the SWITCHBOARD — the same pattern from Session 4.
    """
    category = classification.get("category", "general")
    urgency = classification.get("urgency", "medium")
    summary = classification.get("summary", "No summary available")

    # Get the right template (with fallbacks for unexpected values)
    category_templates = TEMPLATES.get(category, TEMPLATES["general"])
    template = category_templates.get(urgency, category_templates["medium"])

    # Fill in the summary
    return template.format(summary=summary)


# ============================================================
# TRIAGE — The complete pipeline: classify → route → respond
# ============================================================
def triage(customer_message):
    """
    The full triage pipeline. This is a CHAINING WORKFLOW:
    Step 1 (classify) feeds into Step 2 (route).
    
    More precisely, it's a ROUTING pattern — the classification
    determines which template handles the response.
    """
    # Step 1: Claude classifies the message
    classification = classify_message(customer_message)

    # Step 2: Code routes to the right template
    response = route_to_template(classification)

    return {
        "classification": classification,
        "response": response
    }


# ============================================================
# MAIN — Run the triage on a sample message
# ============================================================
if __name__ == "__main__":
    # Sample customer messages to test
    sample_messages = [
        "I was charged twice for my subscription this month. I need a refund immediately!",
        "How do I change my password?",
        "The API keeps returning 500 errors and our production system is down!",
    ]

    for i, message in enumerate(sample_messages, 1):
        print(f"\n{'='*60}")
        print(f"MESSAGE {i}: {message}")
        print(f"{'='*60}")

        result = triage(message)

        print(f"\nCategory: {result['classification']['category']}")
        print(f"Urgency:  {result['classification']['urgency']}")
        print(f"Summary:  {result['classification']['summary']}")
        print(f"\nRESPONSE:")
        print(result['response'])
