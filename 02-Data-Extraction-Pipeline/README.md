# Maintenance Request Data Extraction Pipeline

## Overview

This system takes in maintenance requests from tenants from varied formats: email, web form submission, and scanned handwritten notes. The system parses through the maintenance requests and categorizes them by name (optional), unit number (optional), category (enum: plumbing, electrical, HVAC, appliance, structural, general)(required), urgency (enum: emergency, standard, low)(required), and description (required). The system produces both a parsed categorization in JSON format and a concise summary in human-readable text format.

## Architecture

### Chain Workflow

The system is a chaining workflow, because all of the requisite steps are predictable and straightforward, requiring no looping or agentic autonomy to produce the desired result. Each workflow in the chain is dependent on the previous workflow to successfully process.

```
Raw Tenant Text
      |
      v
[Step 1: Extraction] --- parse_submission tool ---> Structured JSON
      |
      v
[Step 1a: Unit Number Sanitization] --- regex validation ---> Cleaned JSON
      |
      v
[Step 1b: Cross-Check] --- verify_classification tool (separate API call) ---> Pass / Fail
      |                                                                           |
      |   <--- [Retry with feedback, up to 5x] <--- Fail                         |
      |   <--- [Oscillation detection] <--- alternating urgency values            |
      |                                                                           |
      v                                                                           |
[Step 2: Summary Generation] <--- Pass -------------------------------------------
      |
      v
Human-Readable Work-Order Summary
```

### Tool Schemas

Tool schemas were implemented to guarantee proper return format in the form of key:value, for example, `unit_number: string`, `urgency: enum(emergency, standard, low)`. Prompt-based explicit instruction to return ONLY a selected format was removed due to its unreliability.

**`parse_submission`** — Extraction tool forced via `tool_choice`:
| Field | Type | Required |
|-------|------|----------|
| `name` | string | No |
| `unit_number` | string | No |
| `category` | enum: plumbing, electrical, HVAC, appliance, structural, general | Yes |
| `urgency` | enum: emergency, standard, low | Yes |
| `description` | string | Yes |

Optional fields for name and unit number were implemented, and required fields for category, urgency, and description were implemented, because the model would always be able to create a classification for category and urgency based on the description presented. Name and unit number may not always be present in the maintenance requests.

**`verify_classification`** — Cross-check tool forced via `tool_choice`:
| Field | Type | Required |
|-------|------|----------|
| `category_correct` | boolean | Yes |
| `suggested_category` | enum: plumbing, electrical, HVAC, appliance, structural, general | Yes |
| `urgency_correct` | boolean | Yes |
| `suggested_urgency` | enum: emergency, standard, low | Yes |
| `reason` | string | Yes |

### System Prompt

The system prompt uses XML tags to structure classification rules, few-shot examples, and constraints:

- `<category>` — defines the six maintenance categories with keyword associations
- `<urgency>` — defines the three urgency levels with classification criteria; defaults to emergency under ambiguity
- `<examples>` — four few-shot examples covering multi-line, short, single-line, and messy/vague submissions
- `<constraints>` — instructs the model to only extract name and unit number if explicitly present, never guess or invent them

## Error Handling

### Unit Number Sanitization

Error handling was implemented to perform unit number sanitization, where the string for unit number, if present, is checked for a combination of numbers and letters, or just numbers, and dismissed or set to null if full sentences or more than 4 words are detected in the value for the field.

### Cross-Check Validation

The returned values for category and description are cross-checked to see whether the category matches the description, and whether the urgency value matches `<urgency>` in the system prompt. This is done by calling a separate API call with a fresh context window, and having it perform the cross-check with only the values to be cross-checked passed to it. If the cross-check passes, the function returns the value. If the cross-check fails, a separate API call is made, and the adjusted values are passed to it for a retry with feedback loop, to a maximum of 5 retries.

### Oscillation Detection

If oscillation is detected between API calls on the urgency categorization, the values are tracked with each retry, and if oscillation is detected (an A-B-A pattern), the higher urgency is selected from a ranking of urgencies from high to low: emergency, standard, low.

## Domain 4 Concepts Used

- **`tool_choice`** — forces the model to call a specific tool, guaranteeing structured output on every API call
- **Tool schemas for guaranteed output format** — replaces unreliable prompt-based JSON formatting instructions with schema-enforced key:value pairs and enum constraints
- **XML tags in system prompts** — `<category>`, `<urgency>`, `<examples>`, `<constraints>` provide clear structural boundaries for classification rules
- **Self-review bias resolved by calling a separate API for cross-checking** — a fresh context window with no prior conversation history eliminates confirmation bias from the extraction step
- **Few-shot examples used for urgency and category classification within system prompt** — four varied examples guide the model across different submission styles and completeness levels
- **Semantic validation error handling** — unit number sanitization, category-description cross-checking, urgency-rule cross-checking, retry with feedback loop, and oscillation detection with automatic resolution

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your Anthropic API key:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Usage

```bash
python maintenance_submissions.py
```

## Sample Output

**Input:**
```
Tom Bradley, unit 19C. Outlet in the bedroom is sparking when I plug anything in.
Smells like burning plastic. I shut off the breaker but need this fixed immediately.
```

**Step 1 — Extracting structured data:**
```
  > Cross-check attempt 1/5 ...
  [PASS] Cross-check passed.
```
```json
{
  "name": "Tom Bradley",
  "unit_number": "19C",
  "category": "electrical",
  "urgency": "emergency",
  "description": "Bedroom outlet sparking when items are plugged in, burning plastic smell present. Tenant has shut off breaker as safety precaution."
}
```

**Step 2 — Generating work-order summary:**
```
EMERGENCY - Electrical Hazard

Unit: 19C
Tenant: Tom Bradley
Issue: Sparking bedroom outlet with burning plastic odor. Breaker shut off by
tenant for safety. Requires immediate electrical inspection and repair.
```
