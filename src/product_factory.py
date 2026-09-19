import json, os
from datetime import datetime, timezone

OUT = "site/products"

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

def text(*lines):
    return "\n".join(lines) + "\n"

PRODUCTS = [
    {
        "name": "AI Coding Productivity ROI Kit",
        "slug": "ai-coding-productivity-roi-kit",
        "price_usd": 12,
        "tagline": "Measure whether AI coding tools actually save you time.",
        "target": "developers, freelancers, small engineering teams",
        "files": {
            "quick-start.md": text("# Quick Start", "1. Pick 3-5 recurring coding tasks.", "2. Record baseline time.", "3. Track AI time, editing, review and rework.", "4. Compare total effort and quality."),
            "task-log.csv": text("date,task_id,task_type,baseline_minutes,ai_minutes,human_edit_minutes,review_minutes,rework_minutes,outcome,notes", "2026-01-01,T001,feature,60,20,25,10,5,completed,replace example"),
            "roi-calculator.csv": text("input,value,notes", "hours_saved_per_week,0,Measured hours saved", "hourly_value,50,Estimated value per hour", "weekly_value,0,Estimated weekly value", "annual_value,0,Simple annualized value", "tool_cost_per_month,0,Monthly AI/tool cost"),
        },
    },
    {
        "name": "Freelancer Invoice Follow-Up Kit",
        "slug": "freelancer-invoice-follow-up-kit",
        "price_usd": 9,
        "tagline": "A repeatable system for following up on unpaid invoices.",
        "target": "freelancers, consultants, small agencies",
        "files": {
            "quick-start.md": text("# Quick Start", "Import outstanding invoices.", "Assign a follow-up stage.", "Use neutral reminder templates.", "Review overdue amounts weekly."),
            "invoice-tracker.csv": text("client,invoice_id,amount,currency,due_date,status,last_contact,next_contact,notes", "Example,INV-001,500,USD,2026-01-15,overdue,2026-01-22,2026-01-29,replace example"),
            "follow-up-templates.md": text("# Follow-Up Templates", "Friendly reminder: Hi [Name], just a quick reminder that invoice [ID] for [Amount] was due on [Date].", "Second follow-up: Could you confirm the expected payment date?"),
        },
    },
    {
        "name": "Small Business Automation Audit Kit",
        "slug": "small-business-automation-audit-kit",
        "price_usd": 15,
        "tagline": "Find repetitive work worth automating before buying another tool.",
        "target": "solo businesses and small teams",
        "files": {
            "audit-sheet.csv": text("process,owner,frequency,minutes_per_run,monthly_runs,monthly_minutes,error_risk,customer_impact,automation_candidate,notes", "Example,Admin,weekly,60,4,240,medium,medium,yes,replace example"),
            "automation-scorecard.md": text("# Automation Scorecard", "Score each workflow from 1-5 for frequency, time cost, error risk, standardization and customer impact."),
            "pilot-plan.md": text("# 7-Day Automation Pilot", "Workflow:", "Current baseline:", "Success metric:", "Day 1-2 setup:", "Day 3-5 pilot:", "Day 6 measurement:", "Day 7 decision:"),
        },
    },
    {
        "name": "Job Search Application Tracker Pro",
        "slug": "job-search-application-tracker-pro",
        "price_usd": 9,
        "tagline": "Organize applications, follow-ups and interview preparation.",
        "target": "job seekers and career changers",
        "files": {
            "application-tracker.csv": text("company,role,source,applied_date,status,next_action,next_date,contact,notes", "Example,Software Engineer,Job Board,2026-01-10,Applied,Follow up,2026-01-17,Recruiter,replace example"),
            "interview-prep.md": text("# Interview Prep", "Role:", "Top requirements:", "Three relevant examples:", "Questions to ask:", "Technical topics to review:"),
            "weekly-review.md": text("# Weekly Review", "Applications sent:", "Responses:", "Interviews:", "Follow-ups due:", "Next week's target:"),
        },
    },
    {
        "name": "AI Content Workflow Planner",
        "slug": "ai-content-workflow-planner",
        "price_usd": 12,
        "tagline": "Plan, produce and review repeatable AI-assisted content.",
        "target": "creators, marketers, solo businesses",
        "files": {
            "content-pipeline.csv": text("item,channel,goal,status,draft_date,review_date,publish_date,performance_metric,notes", "Example,LinkedIn,Lead generation,Idea,2026-01-10,2026-01-11,2026-01-12,Clicks,replace example"),
            "prompt-brief.md": text("# Content Brief", "Audience:", "Goal:", "Key claim:", "Evidence/source:", "Tone:", "Call to action:", "Human review checklist:"),
            "quality-checklist.md": text("# AI Content Quality Checklist", "- Claims verified", "- Sources checked", "- No invented quotations", "- Human editor reviewed"),
        },
    },
    {
        "name": "Client Onboarding Workflow Kit",
        "slug": "client-onboarding-workflow-kit",
        "price_usd": 12,
        "tagline": "Turn a new client into a tracked, repeatable onboarding workflow.",
        "target": "freelancers, agencies, consultants",
        "files": {
            "onboarding-tracker.csv": text("client,start_date,contract_signed,intake_received,kickoff,assets_received,first_deliverable,status,next_action,notes", "Example,2026-01-05,yes,yes,2026-01-08,yes,2026-01-12,active,Send update,replace example"),
            "intake-checklist.md": text("# Client Intake Checklist", "- Scope confirmed", "- Billing/contact details confirmed", "- Goals and success metric captured", "- Access/assets received", "- Kickoff scheduled"),
            "welcome-email.md": text("# Welcome Email", "Subject: Welcome - next steps for [Project]", "Hi [Client], thanks for getting started. Here are the next steps and kickoff details."),
        },
    },
    {
        "name": "Meeting Action Tracker",
        "slug": "meeting-action-tracker",
        "price_usd": 7,
        "tagline": "Convert meetings into owners, deadlines and visible follow-through.",
        "target": "small teams, project leads, freelancers",
        "files": {
            "action-log.csv": text("meeting_date,meeting,action,owner,due_date,status,priority,notes", "2026-01-06,Weekly sync,Update landing page,Example,2026-01-09,open,high,replace example"),
            "meeting-notes.md": text("# Meeting Notes", "Date:", "Purpose:", "Decisions:", "Open questions:", "Actions:", "Next meeting:"),
            "follow-up.md": text("# Meeting Follow-Up", "Subject: Actions from [Meeting]", "Decisions:", "Actions:", "- [Owner] - [Action] - due [Date]", "Open questions:"),
        },
    },
    {
        "name": "SOP Builder Starter Kit",
        "slug": "sop-builder-starter-kit",
        "price_usd": 11,
        "tagline": "Document repeatable business processes so work is easier to delegate.",
        "target": "small businesses, operators, team leads",
        "files": {
            "sop-template.md": text("# Standard Operating Procedure", "Process:", "Owner:", "Purpose:", "Trigger:", "Inputs:", "Steps:", "Quality checks:", "Exceptions:", "Output:", "Review date:"),
            "process-inventory.csv": text("process,owner,frequency,customer_impact,risk,documented,last_review,next_review,priority", "Example,Operations,weekly,medium,medium,no,,,high"),
            "review-checklist.md": text("# SOP Review", "- A new person can follow it", "- Inputs and outputs are clear", "- Exceptions are documented", "- Owner is named", "- Review date is scheduled"),
        },
    },
    {
        "name": "Freelance Proposal Pipeline",
        "slug": "freelance-proposal-pipeline",
        "price_usd": 9,
        "tagline": "Track leads, proposals, follow-ups and outcomes in one lightweight pipeline.",
        "target": "freelancers, consultants, small agencies",
        "files": {
            "proposal-pipeline.csv": text("lead,service,source,estimated_value,proposal_date,status,next_action,next_date,outcome,notes", "Example,Consulting,Referral,1000,2026-01-08,proposal,Follow up,2026-01-12,,replace example"),
            "proposal-outline.md": text("# Proposal Outline", "Client:", "Problem:", "Desired outcome:", "Scope:", "Deliverables:", "Timeline:", "Price:", "Next step:"),
            "follow-up-sequence.md": text("# Follow-Up Sequence", "Day 0: send proposal and confirm receipt.", "Day 3: ask whether any questions remain.", "Day 7: ask about decision timing.", "Day 14: close the loop politely."),
        },
    },
    {
        "name": "Simple Sales Pipeline Kit",
        "slug": "simple-sales-pipeline-kit",
        "price_usd": 10,
        "tagline": "Keep prospects, next actions and deal stages visible without a heavy CRM.",
        "target": "solo salespeople, freelancers, small businesses",
        "files": {
            "sales-pipeline.csv": text("prospect,stage,value,probability,next_action,next_date,last_contact,source,notes", "Example,Proposal,1500,0.5,Call,2026-01-15,2026-01-10,Referral,replace example"),
            "stage-definitions.md": text("# Pipeline Stages", "Lead -> Qualified -> Discovery -> Proposal -> Negotiation -> Won/Lost", "Define one clear exit condition for every stage."),
            "weekly-review.md": text("# Weekly Pipeline Review", "New leads:", "Qualified:", "Proposals:", "Deals won:", "Deals lost:", "Total open value:", "Next actions:"),
        },
    },
    {
        "name": "Creator Content Calendar Pro",
        "slug": "creator-content-calendar-pro",
        "price_usd": 9,
        "tagline": "Plan a consistent publishing cadence with reusable ideas and review checkpoints.",
        "target": "creators, newsletters, solo marketers",
        "files": {
            "content-calendar.csv": text("publish_date,channel,topic,format,status,cta,owner,metric,notes", "2026-01-12,Newsletter,Example topic,Article,planned,Subscribe,Example,Open rate,replace example"),
            "idea-bank.csv": text("idea,content_pillar,audience_problem,source,priority,status,notes", "Example,Education,Common workflow mistake,Internal research,high,new,replace example"),
            "monthly-review.md": text("# Monthly Content Review", "Published:", "Top topic:", "Top channel:", "Best metric:", "Ideas to repeat:", "Ideas to stop:"),
        },
    },
    {
        "name": "Personal Finance Admin Tracker",
        "slug": "personal-finance-admin-tracker",
        "price_usd": 8,
        "tagline": "Organize recurring bills, subscriptions and financial admin tasks.",
        "target": "households, freelancers, busy professionals",
        "files": {
            "admin-tracker.csv": text("item,category,amount,currency,due_date,frequency,autopay,review_date,status,notes", "Example,Subscription,10,USD,2026-01-15,monthly,yes,2026-02-01,active,replace example"),
            "monthly-review.md": text("# Monthly Review", "Bills due:", "Subscriptions to review:", "Unexpected charges:", "Admin tasks:", "Next review:"),
            "renewal-checklist.md": text("# Renewal Checklist", "- Confirm the service is still used", "- Check current price", "- Check renewal date", "- Cancel or keep intentionally", "- Record decision"),
        },
    },
]

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

DELIVERY_BASE = "https://ldc-12.github.io/Chatgpt-business-automatic/delivery/"

def build_product(product):
    path = os.path.join(OUT, product["slug"])
    os.makedirs(path, exist_ok=True)
    checkout_url = CHECKOUT_URLS[product["slug"]]
    meta = {
        "name": product["name"],
        "slug": product["slug"],
        "price_usd": product["price_usd"],
        "status": "active",
        "checkout_url": checkout_url,\n        "delivery_url": DELIVERY_BASE + product["slug"] + "/",
        "tagline": product["tagline"],
        "target_user": product["target"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": list(product["files"].keys()),
    }
    write(path + "/product.json", json.dumps(meta, ensure_ascii=False, indent=2))
    readme = text(
        "# " + product["name"],
        "**" + product["tagline"] + "**",
        "Designed for: " + product["target"] + ".",
        "## Included",
        *["- " + name for name in product["files"]],
        "## Use",
        "Replace the example content with your own data and use the workflow for one week.",
        "## Important",
        "This is a practical template system, not a guarantee of results.",
        "## Price",
        "US$" + str(product["price_usd"]) + " one-time.",
        "## License",
        "For purchaser personal or internal business use. No redistribution or resale.",
    )
    write(path + "/README.md", readme)
    for filename, body in product["files"].items():
        write(path + "/" + filename, body)
    items = "".join("<li>" + name + "</li>" for name in product["files"])
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>" + product["name"] + "</title>"
        "<style>body{font-family:system-ui;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.6}"
        ".cta{display:inline-block;padding:12px 18px;border:1px solid #222;border-radius:9px;text-decoration:none;color:inherit;font-weight:700}</style>"
        "</head><body><h1>" + product["name"] + "</h1>"
        "<p><strong>" + product["tagline"] + "</strong></p>"
        "<p>For " + product["target"] + ".</p><h2>Included</h2><ul>" + items + "</ul>"
        "<p><strong>US$" + str(product["price_usd"]) + " one-time</strong></p>"
        "<p><a class='cta' href='" + checkout_url + "'>Buy now</a></p>"
        "<p><a href='README.md'>Product details</a></p></body></html>"
    )
    write(path + "/index.html", html)
    return meta

def main():
    os.makedirs(OUT, exist_ok=True)
    products = [build_product(product) for product in PRODUCTS]
    write("site/products.json", json.dumps(products, ensure_ascii=False, indent=2))
    write("site/checkout.json", json.dumps({
        "status": "active",
        "platforms": {
            "stripe": {"status": "active", "checkout_urls": CHECKOUT_URLS},
            "gumroad": {"status": "not_used", "checkout_url": None},
            "lemonsqueezy": {"status": "not_used", "checkout_url": None},
        },
        "note": "Stripe Payment Links supplied by the store owner are used as the live checkout for each catalog product.",
    }, ensure_ascii=False, indent=2))
    print("Generated " + str(len(products)) + " products with live Stripe checkout links")

if __name__ == "__main__":
    main()
