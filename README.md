# Chatgpt-business-automatic

Automated, low-cost business experimentation engine.

## Current loop

1. GitHub Actions runs every 6 hours or manually.
2. A public trend feed is collected.
3. Potential micro-product opportunities are scored.
4. The latest report is saved to `data/opportunities.json`.
5. Tests run before the report is committed.

## Safety

This stage does not spend money, move funds, send unsolicited messages, or publish paid products automatically. Secrets such as payment credentials and API keys must be stored in GitHub Actions Secrets, never in source code.

Future stages can add product generation, a public landing page, analytics, and payment integration with explicit spending and audit limits.
