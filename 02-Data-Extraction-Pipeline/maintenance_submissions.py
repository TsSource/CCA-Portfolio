import os
import re
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"

# ---------- tool schema ----------
parse_submission_tool = {
    "name": "parse_submission",
    "description": (
        "Parse a maintenance request submission into structured fields. "
        "Extract the tenant name, unit number, category, urgency, and description."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Full name of the tenant submitting the request.",
            },
            "unit_number": {
                "type": "string",
                "description": "The unit or apartment number.",
            },
            "category": {
                "type": "string",
                "enum": [
                    "plumbing",
                    "electrical",
                    "HVAC",
                    "appliance",
                    "structural",
                    "general",
                ],
                "description": "Maintenance category for the request.",
            },
            "urgency": {
                "type": "string",
                "enum": ["emergency", "standard", "low"],
                "description": "How urgent the maintenance request is.",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of the maintenance issue.",
            },
        },
        "required": ["category", "urgency", "description"],
    },
}

verify_classification_tool = {
    "name": "verify_classification",
    "description": (
        "Verify whether the category and urgency assigned to a maintenance "
        "request are accurate based on the description and classification rules."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category_correct": {
                "type": "boolean",
                "description": "True if the assigned category matches the description.",
            },
            "suggested_category": {
                "type": "string",
                "enum": [
                    "plumbing",
                    "electrical",
                    "HVAC",
                    "appliance",
                    "structural",
                    "general",
                ],
                "description": "The correct category. Same as original if correct.",
            },
            "urgency_correct": {
                "type": "boolean",
                "description": "True if the assigned urgency matches the description.",
            },
            "suggested_urgency": {
                "type": "string",
                "enum": ["emergency", "standard", "low"],
                "description": "The correct urgency. Same as original if correct.",
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of any mismatch, or 'all correct'.",
            },
        },
        "required": [
            "category_correct",
            "suggested_category",
            "urgency_correct",
            "suggested_urgency",
            "reason",
        ],
    },
}

tools = [parse_submission_tool]
verification_tools = [verify_classification_tool]

# ---------- system prompt ----------
SYSTEM_PROMPT = """\
<instructions>
You are a maintenance request classifier that extracts tenant information and \
categorizes issues from free-text submissions.

<rules>
<category>
The classification criteria for "category" are:
- plumbing: pipes, drains, faucets, toilets, water heaters, leaks, sewer
- electrical: wiring, outlets, switches, breakers, lighting fixtures, sparks
- HVAC: heating, air conditioning, ventilation, thermostat, furnace, ductwork
- appliance: refrigerator, stove, oven, dishwasher, washer, dryer, microwave, garbage disposal
- structural: walls, ceilings, floors, doors, windows, foundation, roof, stairs, railings
- general: anything that does not clearly fit the above categories
</category>

<urgency>
The classification criteria for "urgency" are:
- emergency: water damage actively occurring, gas leak, electrical hazard, no heat in winter, \
flooding, sewage backup, fire damage, broken locks compromising security
- standard: something is broken but not causing active damage or safety risk — e.g., a \
malfunctioning appliance, a slow drain, a broken window latch, inconsistent hot water
- low: cosmetic issues, minor inconveniences, general requests — e.g., scuffed paint, \
squeaky door, a request for a new shelf, weatherstripping replacement
When the urgency classification is ambiguous, default to emergency.
</urgency>

<description>
Provide a brief, factual description of the issue as a single string. Capture the core \
problem and any relevant details (location within the unit, duration, symptoms) without \
editorializing.
</description>
</rules>

<examples>
Example 1 — Multi-line submission, all fields present:
Tenant: "Hi, my name is James Carter and I live in unit 12A. My bathroom ceiling has been \
dripping water since last night. The drywall is starting to bubble and there is a puddle \
forming on the tile floor. I also noticed a musty smell. Please send someone right away."
→ name: "James Carter", unit_number: "12A", category: "plumbing", urgency: "emergency", \
description: "Bathroom ceiling leaking since last night. Drywall bubbling, water pooling on \
tile floor, musty smell present."

Example 2 — Short submission, only required fields:
Tenant: "The hallway light outside my door has been flickering on and off for about a week."
→ category: "electrical", urgency: "low", description: "Hallway light flickering \
intermittently for approximately one week."

Example 3 — Single-line issue:
Tenant: "Dishwasher won't start."
→ category: "appliance", urgency: "standard", description: "Dishwasher is unresponsive and \
will not start."

Example 4 — Messy / vague submission:
Tenant: "hey yeah so theres this weird noise coming from somewhere in the wall maybe near \
the kitchen idk it kinda sounds like banging or clanking and its been driving me nuts for \
a few days lol can u look into it thx"
→ category: "general", urgency: "low", description: "Unidentified banging or clanking noise \
coming from inside the wall near the kitchen, ongoing for several days."
</examples>

<constraints>
Only extract name and unit_number if they are explicitly stated in the submission. \
Never guess, infer, or invent a name or unit number. If the tenant does not provide \
them, omit those fields entirely.
</constraints>
</instructions>
"""

# ---------- helpers ----------
MAX_RETRIES = 5


def _is_valid_unit_number(value: str) -> bool:
    """Return True if the value looks like a real unit number.

    Valid: contains at least one digit, and is not a full sentence or
    a string made up entirely of words with no digits.
    Examples of valid:   "4B", "12A", "301", "unit 4B"
    Examples of invalid: "the one near the lobby", "first floor apartment"
    """
    if not value or not value.strip():
        return False
    text = value.strip()
    # Must contain at least one digit
    if not re.search(r"\d", text):
        return False
    # Reject if it looks like a full sentence (more than 4 whitespace-separated words)
    if len(text.split()) > 4:
        return False
    return True


def _sanitize_unit_number(parsed: dict) -> dict:
    """Blank out unit_number if it is not a valid unit identifier."""
    if "unit_number" in parsed:
        if not _is_valid_unit_number(parsed["unit_number"]):
            parsed["unit_number"] = None
    return parsed


def _call_extraction(raw_text: str, feedback: str | None = None) -> dict:
    """Make a single extraction API call, optionally including feedback."""
    user_content = (
        "Extract the maintenance request details from the following "
        "tenant submission. Use the parse_submission tool.\n\n"
        f"{raw_text}"
    )
    if feedback:
        user_content += (
            "\n\n<feedback>\n"
            "A prior extraction was incorrect. Apply the following corrections "
            "and re-extract:\n"
            f"{feedback}\n"
            "</feedback>"
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "tool", "name": "parse_submission"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input
    return {}


def _cross_check(parsed: dict) -> dict | None:
    """Independent API call (no prior history) that verifies category and urgency.

    Uses the verify_classification tool to guarantee structured output.
    Returns None if both values are correct.
    Returns a dict with keys 'category' and/or 'urgency' holding the corrected
    values plus a 'feedback' string describing what was wrong.
    """
    verification_prompt = f"""\
You are a strict auditor for a property-management maintenance system.

Given the following maintenance request data, verify whether the "category" and
"urgency" values are accurate based on the "description".

<category_rules>
- plumbing: pipes, drains, faucets, toilets, water heaters, leaks, sewer
- electrical: wiring, outlets, switches, breakers, lighting fixtures, sparks
- HVAC: heating, air conditioning, ventilation, thermostat, furnace, ductwork
- appliance: refrigerator, stove, oven, dishwasher, washer, dryer, microwave, garbage disposal
- structural: walls, ceilings, floors, doors, windows, foundation, roof, stairs, railings
- general: anything that does not clearly fit the above categories
</category_rules>

<urgency_rules>
- emergency: water damage actively occurring, gas leak, electrical hazard, no heat in winter, \
flooding, sewage backup, fire damage, broken locks compromising security
- standard: something is broken but not causing active damage or safety risk
- low: cosmetic issues, minor inconveniences, general requests
When the urgency classification is ambiguous, default to emergency.
</urgency_rules>

Data to verify:
- category: {parsed.get("category")}
- urgency: {parsed.get("urgency")}
- description: {parsed.get("description")}

Use the verify_classification tool to report your assessment."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=verification_tools,
        tool_choice={"type": "tool", "name": "verify_classification"},
        messages=[{"role": "user", "content": verification_prompt}],
    )

    # Extract structured result from the forced tool call
    result = {}
    for block in response.content:
        if block.type == "tool_use":
            result = block.input
            break

    if result.get("category_correct") and result.get("urgency_correct"):
        return None  # all good

    corrections = {}
    feedback_parts = []

    if not result.get("category_correct"):
        corrections["category"] = result["suggested_category"]
        feedback_parts.append(
            f'category should be "{result["suggested_category"]}" not '
            f'"{parsed.get("category")}"'
        )

    if not result.get("urgency_correct"):
        corrections["urgency"] = result["suggested_urgency"]
        feedback_parts.append(
            f'urgency should be "{result["suggested_urgency"]}" not '
            f'"{parsed.get("urgency")}"'
        )

    corrections["feedback"] = (
        f"{result.get('reason', '')}. Corrections: {'; '.join(feedback_parts)}"
    )
    return corrections


# ---------- chain steps ----------
def extract_submission(raw_text: str) -> dict:
    """Step 1 – Extract structured data with validation and retry loop.

    1. Call the extraction API.
    2. Validate unit_number format; blank it out if invalid.
    3. Cross-check category & urgency via a separate API call.
    4. If mismatches are found, re-extract with feedback up to MAX_RETRIES times.
    5. Return the validated result, or an error dict after exhausting retries.
    """
    urgency_rank = {"emergency": 0, "standard": 1, "low": 2}

    parsed = _call_extraction(raw_text)
    parsed = _sanitize_unit_number(parsed)

    mismatches = []
    urgency_history = [parsed.get("urgency")]

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  > Cross-check attempt {attempt}/{MAX_RETRIES} …")
        corrections = _cross_check(parsed)

        if corrections is None:
            # Both category and urgency verified — success
            print("  [PASS] Cross-check passed.")
            return parsed

        # Corrections needed
        feedback = corrections["feedback"]
        mismatches.append(feedback)
        print(f"  [FAIL] Mismatch detected: {feedback}")

        # Re-extract with feedback
        parsed = _call_extraction(raw_text, feedback=feedback)
        parsed = _sanitize_unit_number(parsed)

        # Track urgency and detect oscillation
        current_urgency = parsed.get("urgency")
        urgency_history.append(current_urgency)

        if len(urgency_history) >= 3:
            # Check if the last three values form an A-B-A pattern
            a, b, c = urgency_history[-3], urgency_history[-2], urgency_history[-1]
            if a == c and a != b:
                # Oscillation detected — pick the higher urgency
                higher = a if urgency_rank.get(a, 2) < urgency_rank.get(b, 2) else b
                print(
                    f"  [OSCILLATION] Urgency alternating between "
                    f'"{a}" and "{b}". Defaulting to highest: "{higher}".'
                )
                parsed["urgency"] = higher
                return parsed

    # Exhausted all retries — return error with mismatch details
    mismatch_log = "\n".join(f"  Attempt {i+1}: {m}" for i, m in enumerate(mismatches))
    return {
        "error": (
            "Unable to process maintenance request. After "
            f"{MAX_RETRIES} retries, category and/or urgency could not be "
            "verified.\n\nMismatch history:\n" + mismatch_log
        )
    }


def build_summary(parsed: dict) -> str:
    """Step 2 – Ask Claude to produce a human-readable summary from the parsed data."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are a property-management assistant. "
                    "Given the following parsed maintenance request, write a short, "
                    "professional summary suitable for a work-order ticket.\n\n"
                    f"{json.dumps(parsed, indent=2)}"
                ),
            }
        ],
    )
    return response.content[0].text


def run_chain(raw_text: str) -> None:
    """Execute the full chain: extract → summarize → display."""
    print("=" * 60)
    print("STEP 1 — Extracting structured data …")
    print("=" * 60)
    parsed = extract_submission(raw_text)
    print(json.dumps(parsed, indent=2))

    print()
    print("=" * 60)
    print("STEP 2 — Generating work-order summary …")
    print("=" * 60)
    summary = build_summary(parsed)
    print(summary)


# ---------- demo ----------
if __name__ == "__main__":
    samples = [
        # 1 - plumbing / emergency - complete, with name + unit
        (
            "Hi, this is Maria Gonzalez from unit 4B. My kitchen sink has been "
            "leaking under the cabinet since yesterday morning. There's water pooling "
            "on the floor and I'm worried about mold. Can someone come fix it ASAP?"
        ),
        # 2 - electrical / emergency - concise, with name + unit
        (
            "Tom Bradley, unit 19C. Outlet in the bedroom is sparking when I plug "
            "anything in. Smells like burning plastic. I shut off the breaker but "
            "need this fixed immediately."
        ),
        # 3 - HVAC / standard - moderate detail, no name, with unit
        (
            "Unit 7A here. The AC has been blowing warm air for the past three days. "
            "I've checked the thermostat and filter but nothing changed. It's not "
            "unbearable yet but getting uncomfortable."
        ),
        # 4 - appliance / standard - short, with name, no unit
        (
            "This is Diane Patel. My refrigerator stopped cooling overnight. "
            "Everything in the freezer is thawing. The motor sounds like it's "
            "running but nothing is cold."
        ),
        # 5 - structural / low - concise, no name or unit
        (
            "There's a long crack running along the living room ceiling. It's been "
            "there for a few weeks and seems to be getting slightly wider. No water "
            "or anything leaking from it though."
        ),
        # 6 - general / low - vague and messy, no name or unit
        (
            "hey so uh theres this weird smell in the hallway near my door?? idk "
            "what it is, its not like gas or anything dangerous i dont think but its "
            "been there for like a week and its kinda gross lol can someone check it out"
        ),
        # 7 - plumbing / standard - single line, no name, with unit
        (
            "Unit 22F - toilet keeps running nonstop after flushing."
        ),
        # 8 - electrical / low - messy, with name, no unit
        (
            "names ricky wallace and yeah so like two of the light switches in my "
            "hallway dont do anything?? i flip them and nothing happens lol theyve "
            "been like that since i moved in honestly not a huge deal but figured "
            "id mention it whenever u get a chance"
        ),
        # 9 - HVAC / emergency - complete, with name + unit
        (
            "My name is Sandra Liu, apartment 3D. Our furnace completely shut off "
            "last night and will not turn back on. It is currently 15 degrees outside "
            "and the indoor temperature has dropped to 48 degrees. We have a newborn "
            "in the unit. Please send someone urgently."
        ),
        # 10 - structural / emergency - vague-ish, no name, with unit
        (
            "apt 10B - part of the bathroom ceiling just fell in. theres chunks of "
            "drywall and plaster on the floor and i can see pipes above. nobody is "
            "hurt but its a big hole and theres water dripping from it now"
        ),
    ]

    for i, submission in enumerate(samples, start=1):
        print(f"\n{'#' * 60}")
        print(f"  SUBMISSION {i} of {len(samples)}")
        print(f"{'#' * 60}")
        print(f"Raw text: {submission[:80]}...")
        print()
        run_chain(submission)
        print()
