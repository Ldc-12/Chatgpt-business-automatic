import json, os, re
from datetime import datetime, timezone

REPORT = "data/opportunities.json"
OUT = "site/products"

PRODUCT = {
    "name": "AI Coding Productivity ROI Kit",
    "slug": "ai-coding-productivity-roi-kit",
    "tagline": "Measure whether AI coding tools actually save you time.",
    "description": "A practical 7-day tracking and ROI kit for developers using AI coding assistants. Track task time, rework, review effort, and estimated value instead of relying on guesswork.",
    "price_usd": 12,
    "status": "ready_for_sale",
    "target_user": "developers, freelancers, and small engineering teams",
}

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def build():
    path = f"{OUT}/{PRODUCT['slug']}"
    os.makedirs(path, exist_ok=True)
    product = dict(PRODUCT)
    product["generated_at"] = datetime.now(timezone.utc).isoformat()
    product["files"] = [
        "README.md", "task-log.csv", "weekly-review.md",
        "roi-calculator.csv", "team-rollup.csv", "quick-start.md"
    ]
    write(f"{path}/product.json", json.dumps(product, ensure_ascii=False, indent=2))

    write(f"{path}/README.md", f"""# {PRODUCT['name']}

**{PRODUCT['tagline']}**

{PRODUCT['description']}

## What you get

- 7-day AI coding task log
- Rework and review-time tracker
- Weekly review worksheet
- Simple ROI calculator
- Team roll-up sheet
- Quick-start guide
- No software installation required

## Who it is for

Developers and small teams who want a simple, evidence-based way to compare AI-assisted work with their normal workflow.

## What this is not

This kit does not promise that AI will save time. It gives you a repeatable measurement method so you can test that question with your own work.

## License

For personal or internal business use by the purchaser. Do not redistribute or resell the files.

## Price

Suggested launch price: US$12 one-time.
""")

    write(f"{path}/quick-start.md", """# Quick Start

## Day 0 — Baseline
Pick 3–5 recurring coding tasks. Record how long each normally takes and what review/rework is required.

## Days 1–7 — Track
For each task, record:
- task type
- start/end time
- AI minutes
- human editing minutes
- review minutes
- rework minutes
- outcome

## Day 7 — Review
Compare total effort, rework, and completed outcomes with your baseline.

## Decision rule
Keep an AI workflow only when it improves the metric you care about without creating unacceptable quality or review costs.
""")

    write(f"{path}/task-log.csv", """date,task_id,task_type,baseline_minutes,ai_minutes,human_edit_minutes,review_minutes,rework_minutes,outcome,notes
2026-01-01,T001,feature,60,20,25,10,5,completed,example row - replace
""")

    write(f"{path}/weekly-review.md", """# Weekly Review

Week:

Tasks completed:

## Metrics
Baseline total minutes:
AI-assisted total minutes:
Human editing minutes:
Review minutes:
Rework minutes:

## Quality
What improved?

What got worse?

What required the most rework?

## Decision
[ ] Continue this workflow
[ ] Modify it
[ ] Stop using it for this task

Next week's experiment:
""")

    write(f"{path}/roi-calculator.csv", """input,value,notes
hours_saved_per_week,0,Enter measured hours saved
hourly_value,50,Use your own estimated value per hour
weekly_value,=B2*B3,Estimated weekly value
annual_value,=B4*52,Simple annualized value
tool_cost_per_month,0,Enter monthly AI/tool cost
annual_tool_cost,=B6*12,Annualized tool cost
net_annual_value,=B5-B7,Estimated net annual value
""")

    write(f"{path}/team-rollup.csv", """week,developer,tasks_completed,total_baseline_minutes,total_ai_work_minutes,total_rework_minutes,estimated_hours_saved
2026-W01,Example,5,300,240,20,1
""")

    write(f"{path}/index.html", f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{PRODUCT['name']}</title><style>body{{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6}}.box{{border:1px solid #ddd;border-radius:14px;padding:24px;margin:20px 0}}.buy{{display:inline-block;padding:12px 18px;border-radius:9px;background:#111;color:#fff;text-decoration:none}}code{{background:#f4f4f4;padding:2px 5px}}</style></head><body><h1>{PRODUCT['name']}</h1><p><strong>{PRODUCT['tagline']}</strong></p><p>{PRODUCT['description']}</p><div class='box'><h2>Included</h2><ul><li>7-day task tracker</li><li>ROI calculator</li><li>Weekly review worksheet</li><li>Team roll-up</li><li>Quick-start guide</li></ul><p><strong>US$12 one-time</strong></p><p><a class='buy' href='#buy'>Buy when checkout is connected</a></p></div><h2>How it works</h2><p>Measure baseline → track AI-assisted work → review time, quality and rework → decide what to keep.</p><p><a href='README.md'>Product details</a> · <a href='quick-start.md'>Quick start</a></p><small>Launch edition · No software installation required.</small></body></html>""")
    return product

def main():
    os.makedirs(OUT, exist_ok=True)
    products = [build()]
    with open("site/products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"Generated {len(products)} paid-ready product")

if __name__ == "__main__":
    main()
