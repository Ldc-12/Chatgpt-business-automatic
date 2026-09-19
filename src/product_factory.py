import json, os
from datetime import datetime, timezone

OUT = "site/products"

def md(text):
    return text.strip() + "\n"

CHECKOUT_URLS = {
    "ai-coding-productivity-roi-kit": "https://buy.stripe.com/cNi5kFei3g9hbECd8S9Zm00",
    "freelancer-invoice-follow-up-kit": "https://buy.stripe.com/9B6bJ3a1NcX5eQO6Ku9Zm01",
    "small-business-automation-audit-kit": "https://buy.stripe.com/fZu5kF1vh4qzcIG6Ku9Zm02",
    "job-search-application-tracker-pro": "https://buy.stripe.com/eVqaEZddZcX5242c4O9Zm03",
    "ai-content-workflow-planner": "https://buy.stripe.com/14A6oJ6PBg9hgYW8SC9Zm04",
    "client-onboarding-workflow-kit": "https://buy.stripe.com/fZu9AV5Lx8GPfUS3yi9Zm05",
    "meeting-action-tracker": "https://buy.stripe.com/bJeeVf7TFf5d2429WG9Zm06",
    "sop-builder-starter-kit": "https://buy.stripe.com/14A3cxgqbbT15ge0m69Zm07",
    "freelance-proposal-pipeline": "https://buy.stripe.com/28EfZjgqbaOXbEC1qa9Zm08",
    "simple-sales-pipeline-kit": "https://buy.stripe.com/3cI4gBc9V1en6ki1qa9Zm09",
    "creator-content-calendar-pro": "https://buy.stripe.com/cNi8wRfm7bT1eQO4Cm9Zm0a",
    "personal-finance-admin-tracker": "https://buy.stripe.com/3cI28t3Dp3mv5gec4O9Zm0b",
}

PRODUCTS = [
    {
        "name": "AI Coding Productivity ROI Kit",
        "slug": "ai-coding-productivity-roi-kit",
        "price_usd": 12,
        "tagline": "Measure whether AI coding tools actually save you time.",
        "target": "developers, freelancers, small engineering teams",
        "files": {
            "quick-start.md": md("""# Quick Start
1. Pick 3–5 recurring coding tasks.
2. Record normal baseline time.
3. Track AI time, editing, review and rework for 7 days.
4. Compare total effort and quality.
5. Keep only workflows that improve your chosen metric."""),
            "task-log.csv": "date,task_id,task_type,baseline_minutes,ai_minutes,human_edit_minutes,review_minutes,rework_minutes,outcome,notes\n2026-01-01,T001,feature,60,20,25,10,5,completed,replace example row\n",
            "roi-calculator.csv": "input,value,notes\nhours_saved_per_week,0,Measured hours saved\nhourly_value,50,Estimated value per hour\nweekly_value,=B2*B3,Estimated weekly value\nannual_value,=B4*52,Simple annualized value\ntool_cost_per_month,0,Monthly AI/tool cost\nannual_tool_cost,=B6*12,Annualized cost\nnet_annual_value,=B5-B7,Estimated net annual value\n",
            "weekly-review.md": md("""# Weekly Review
Baseline total minutes:
AI-assisted total minutes:
Review minutes:
Rework minutes:

What improved?
What got worse?
What will you change next week?"""),
            "team-rollup.csv": "week,developer,tasks_completed,total_baseline_minutes,total_ai_work_minutes,total_rework_minutes,estimated_hours_saved\n2026-W01,Example,5,300,240,20,1\n",
        },
    },
    {
        "name": "Freelancer Invoice Follow-Up Kit",
        "slug": "freelancer-invoice-follow-up-kit",
        "price_usd": 9,
        "tagline": "A repeatable system for following up on unpaid invoices.",
        "target": "freelancers, consultants, small agencies",
        "files": {
            "quick-start.md": md("""# Quick Start
1. Import outstanding invoices.
2. Assign each invoice a follow-up stage.
3. Use neutral reminder templates.
4. Record response and payment dates.
5. Review overdue amounts every Friday."""),
            "invoice-tracker.csv": "client,invoice_id,amount,currency,due_date,status,last_contact,next_contact,notes\nExample,INV-001,500,USD,2026-01-15,overdue,2026-01-22,2026-01-29,replace example\n",
            "follow-up-templates.md": md("""# Follow-Up Templates
## Friendly reminder
Hi [Name], just a quick reminder that invoice [ID] for [Amount] was due on [Date]. Please let me know if you need anything from me to process it. Thanks!

## Second follow-up
Hi [Name], following up on invoice [ID]. Could you confirm the expected payment date? Thank you."""),
            "weekly-review.md": md("""# Weekly Review
Outstanding amount:
Invoices due this week:
Follow-ups sent:
Payments received:
Next action:"""),
        },
    },
    {
        "name": "Small Business Automation Audit Kit",
        "slug": "small-business-automation-audit-kit",
        "price_usd": 15,
        "tagline": "Find repetitive work worth automating before buying another tool.",
        "target": "solo businesses and small teams",
        "files": {
            "audit-sheet.csv": "process,owner,frequency,minutes_per_run,monthly_runs,monthly_minutes,error_risk,customer_impact,automation_candidate,notes\nExample,Admin,weekly,60,4,240,medium,medium,yes,replace example\n",
            "automation-scorecard.md": md("""# Automation Scorecard
Score each workflow from 1–5 for frequency, time cost, error risk, standardization, and customer impact."""),
            "quick-start.md": md("""# Quick Start
1. List 10 recurring processes.
2. Estimate monthly time spent.
3. Score repeatability and error risk.
4. Select the top 3 candidates.
5. Test one small automation."""),
            "pilot-plan.md": md("""# 7-Day Automation Pilot
Workflow:
Current baseline:
Change tested:
Success metric:
Risks:
Day 1–2 setup:
Day 3–5 pilot:
Day 6 measurement:
Day 7 decision:"""),
        },
    },
    {
        "name": "Job Search Application Tracker Pro",
        "slug": "job-search-application-tracker-pro",
        "price_usd": 9,
        "tagline": "Organize applications, follow-ups and interview preparation.",
        "target": "job seekers and career changers",
        "files": {
            "application-tracker.csv": "company,role,source,applied_date,status,next_action,next_date,contact,notes\nExample,Software Engineer,Job Board,2026-01-10,Applied,Follow up,2026-01-17,Recruiter,replace example\n",
            "interview-prep.md": md("""# Interview Prep
Role:
Top requirements:
Three relevant examples:
Questions to ask:
Technical topics to review:
Follow-up date:"""),
            "weekly-review.md": md("""# Weekly Review
Applications sent:
Responses:
Interviews:
Follow-ups due:
What changed?
Next week's target:"""),
            "quick-start.md": md("Track every application immediately, set the next action, and review the pipeline twice a week."),
        },
    },
    {
        "name": "AI Content Workflow Planner",
        "slug": "ai-content-workflow-planner",
        "price_usd": 12,
        "tagline": "Plan, produce and review repeatable AI-assisted content.",
        "target": "creators, marketers, solo businesses",
        "files": {
            "content-pipeline.csv": "item,channel,goal,status,draft_date,review_date,publish_date,performance_metric,notes\nExample,LinkedIn,Lead generation,Idea,2026-01-10,2026-01-11,2026-01-12,Clicks,replace example\n",
            "prompt-brief.md": md("""# Content Brief
Audience:
Goal:
Key claim:
Evidence/source:
Tone:
Call to action:
Human review checklist:"""),
            "quality-checklist.md": md("""# AI Content Quality Checklist
- [ ] Claims verified
- [ ] Sources checked
- [ ] No invented quotations
- [ ] Useful to target audience
- [ ] Human editor reviewed
- [ ] CTA matches goal"""),
            "weekly-review.md": md("""# Weekly Review
Pieces published:
Hours spent:
Best-performing item:
Weakest item:
What should be repeated?
What should be stopped?"""),
        },
    },
    {
        "name": "Client Onboarding Workflow Kit",
        "slug": "client-onboarding-workflow-kit",
        "price_usd": 12,
        "tagline": "Turn a new client into a tracked, repeatable onboarding workflow.",
        "target": "freelancers, agencies, consultants",
        "files": {
            "onboarding-tracker.csv": "client,start_date,contract_signed,intake_received,kickoff,assets_received,first_deliverable,status,next_action,notes\nExample,2026-01-05,yes,yes,2026-01-08,yes,2026-01-12,active,Send update,replace example\n",
            "intake-checklist.md": md("""# Client Intake Checklist
- [ ] Scope confirmed
- [ ] Billing/contact details confirmed
- [ ] Goals and success metric captured
- [ ] Access/assets received
- [ ] Kickoff scheduled
- [ ] First milestone agreed"""),
            "welcome-email.md": md("""# Welcome Email
Subject: Welcome — next steps for [Project]

Hi [Client], thanks for getting started. Here are the next steps, the information we need, and the date of our kickoff."""),
            "weekly-review.md": md("""# Weekly Review
New clients:
Blocked clients:
Assets outstanding:
Next milestones:
Process improvement:""),
        },
    },
    {
        "name": "Meeting Action Tracker",
        "slug": "meeting-action-tracker",
        "price_usd": 7,
        "tagline": "Convert meetings into owners, deadlines and visible follow-through.",
        "target": "small teams, project leads, freelancers",
        "files": {
            "action-log.csv": "meeting_date,meeting,action,owner,due_date,status,priority,notes\n2026-01-06,Weekly sync,Update landing page,Example,2026-01-09,open,high,replace example\n",
            "meeting-notes.md": md("""# Meeting Notes
Date:
Purpose:
Decisions:
Open questions:
Actions:
Next meeting:"""),
            "follow-up.md": md("""# Meeting Follow-Up
Subject: Actions from [Meeting]

Decisions:
1.

Actions:
- [Owner] — [Action] — due [Date]

Open questions:"""),
        },
    },
    {
        "name": "SOP Builder Starter Kit",
        "slug": "sop-builder-starter-kit",
        "price_usd": 11,
        "tagline": "Document repeatable business processes so work is easier to delegate.",
        "target": "small businesses, operators, team leads",
        "files": {
            "sop-template.md": md("""# Standard Operating Procedure
Process:
Owner:
Purpose:
Trigger:
Inputs:
Steps:
Quality checks:
Exceptions:
Output:
Review date:"""),
            "process-inventory.csv": "process,owner,frequency,customer_impact,risk,documented,last_review,next_review,priority\nExample,Operations,weekly,medium,medium,no,,,high\n",
            "review-checklist.md": md("""# SOP Review
- [ ] A new person can follow it
- [ ] Inputs and outputs are clear
- [ ] Exceptions are documented
- [ ] Owner is named
- [ ] Review date is scheduled"""),
        },
    },
    {
        "name": "Freelance Proposal Pipeline",
        "slug": "freelance-proposal-pipeline",
        "price_usd": 9,
        "tagline": "Track leads, proposals, follow-ups and outcomes in one lightweight pipeline.",
        "target": "freelancers, consultants, small agencies",
        "files": {
            "proposal-pipeline.csv": "lead,service,source,estimated_value,proposal_date,status,next_action,next_date,outcome,notes\nExample,Consulting,Referral,1000,2026-01-08,proposal,Follow up,2026-01-12,,replace example\n",
            "proposal-outline.md": md("""# Proposal Outline
Client:
Problem:
Desired outcome:
Scope:
Deliverables:
Timeline:
Price:
Assumptions:
Next step:"""),
            "follow-up-sequence.md": md("""# Follow-Up Sequence
Day 0: send proposal and confirm receipt.
Day 3: ask whether any questions remain.
Day 7: ask about decision timing.
Day 14: close the loop politely."""),
        },
    },
    {
        "name": "Simple Sales Pipeline Kit",
        "slug": "simple-sales-pipeline-kit",
        "price_usd": 10,
        "tagline": "Keep prospects, next actions and deal stages visible without a heavy CRM.",
        "target": "solo salespeople, freelancers, small businesses",
        "files": {
            "sales-pipeline.csv": "prospect,stage,value,probability,next_action,next_date,last_contact,source,notes\nExample,Proposal,1500,0.5,Call,2026-01-15,2026-01-10,Referral,replace example\n",
            "stage-definitions.md": md("""# Pipeline Stages
Lead → Qualified → Discovery → Proposal → Negotiation → Won/Lost

Define one clear exit condition for every stage."""),
            "weekly-review.md": md("""# Weekly Pipeline Review
New leads:
Qualified:
Proposals:
Deals won:
Deals lost:
Total open value:
Next actions:"""),
        },
    },
    {
        "name": "Creator Content Calendar Pro",
        "slug": "creator-content-calendar-pro",
        "price_usd": 9,
        "tagline": "Plan a consistent publishing cadence with reusable ideas and review checkpoints.",
        "target": "creators, newsletters, solo marketers",
        "files": {
            "content-calendar.csv": "publish_date,channel,topic,format,status,cta,owner,metric,notes\n2026-01-12,Newsletter,Example topic,Article,planned,Subscribe,Example,Open rate,replace example\n",
            "idea-bank.csv": "idea,content_pillar,audience_problem,source,priority,status,notes\nExample,Education,Common workflow mistake,Internal research,high,new,replace example\n",
            "monthly-review.md": md("""# Monthly Content Review
Published:
Top topic:
Top channel:
Best metric:
Ideas to repeat:
Ideas to stop:
Next month's experiment:"""),
        },
    },
    {
        "name": "Personal Finance Admin Tracker",
        "slug": "personal-finance-admin-tracker",
        "price_usd": 8,
        "tagline": "Organize recurring bills, subscriptions and financial admin tasks.",
        "target": "households, freelancers, busy professionals",
        "files": {
            "admin-tracker.csv": "item,category,amount,currency,due_date,frequency,autopay,review_date,status,notes\nExample,Subscription,10,USD,2026-01-15,monthly,yes,2026-02-01,active,replace example\n",
            "monthly-review.md": md("""# Monthly Review
Bills due:
Subscriptions to review:
Unexpected charges:
Admin tasks:
Next review:"""),
            "renewal-checklist.md": md("""# Renewal Checklist
- [ ] Confirm the service is still used
- [ ] Check current price
- [ ] Check renewal date
- [ ] Cancel or keep intentionally
- [ ] Record decision"""),
        },
    },
]

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def build_product(p):
    path = os.path.join(OUT, p["slug"])
    os.makedirs(path, exist_ok=True)
    meta = {
        "name": p["name"],
        "slug": p["slug"],
        "price_usd": p["price_usd"],
        "status": "active",
        "checkout_url": CHECKOUT_URLS.get(p["slug"]),
        "tagline": p["tagline"],
        "target_user": p["target"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": list(p["files"].keys()),
    }
    write(path + "/product.json", json.dumps(meta, ensure_ascii=False, indent=2))
    readme = "# " + p["name"] + "\n\n**" + p["tagline"] + "**\n\nDesigned for: " + p["target"] + ".\n\n## Included\n" + "".join("- " + x + "\n" for x in p["files"]) + "\n## Use\nDownload the files from the marketplace after purchase, replace the example rows/content, and run the workflow for one week.\n\n## Important\nThis is a practical template system, not a guarantee of results.\n\n## Suggested launch price\nUS$" + str(p["price_usd"]) + " one-time.\n\n## License\nFor purchaser personal or internal business use. No redistribution or resale.\n"
    write(path + "/README.md", readme)
    for filename, body in p["files"].items():
        write(path + "/" + filename, body)
    items = "".join("<li>" + x + "</li>" for x in p["files"])
    html = "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>" + p["name"] + "</title></head><body><h1>" + p["name"] + "</h1><p><strong>" + p["tagline"] + "</strong></p><p>For " + p["target"] + ".</p><h2>Included</h2><ul>" + items + "</ul><p><strong>US$" + str(p["price_usd"]) + " one-time</strong></p><p><a href='" + CHECKOUT_URLS[p["slug"]] + "' class='cta'>Buy now — US$" + str(p["price_usd"]) + "</a></p><p><a href='README.md'>Product details</a></p></body></html>"
    write(path + "/index.html", html)
    return meta

def main():
    os.makedirs(OUT, exist_ok=True)
    products = [build_product(p) for p in PRODUCTS]
    with open("site/products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    with open("site/checkout.json", "w", encoding="utf-8") as f:
        json.dump({
            "status": "active",
            "platforms": {
                "stripe": {"status": "active", "checkout_urls": CHECKOUT_URLS},
                "gumroad": {"status": "not_used", "checkout_url": None},
                "lemonsqueezy": {"status": "not_used", "checkout_url": None}
            },
            "note": "Stripe Payment Links supplied by the store owner are used as the live checkout for each catalog product."
        }, ensure_ascii=False, indent=2)
    print("Generated " + str(len(products)) + " catalog-ready products")

if __name__ == "__main__":
    main()
