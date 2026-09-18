import json, os
from datetime import datetime, timezone

OUT = "site/products"
PRODUCTS = [
{"name":"AI Coding Productivity ROI Kit","slug":"ai-coding-productivity-roi-kit","price_usd":12,"tagline":"Measure whether AI coding tools actually save you time.","target":"developers, freelancers, small engineering teams","files":{"quick-start.md":"# Quick Start\n\n1. Pick 3–5 recurring coding tasks.\n2. Record normal baseline time.\n3. Track AI time, editing, review and rework for 7 days.\n4. Compare total effort and quality.\n5. Keep only workflows that improve your chosen metric.\n","task-log.csv":"date,task_id,task_type,baseline_minutes,ai_minutes,human_edit_minutes,review_minutes,rework_minutes,outcome,notes\n2026-01-01,T001,feature,60,20,25,10,5,completed,replace example row\n","roi-calculator.csv":"input,value,notes\nhours_saved_per_week,0,Measured hours saved\nhourly_value,50,Your estimated value per hour\nweekly_value,=B2*B3,Estimated weekly value\nannual_value,=B4*52,Simple annualized value\ntool_cost_per_month,0,Monthly AI/tool cost\nannual_tool_cost,=B6*12,Annualized cost\nnet_annual_value,=B5-B7,Estimated net annual value\n","weekly-review.md":"# Weekly Review\n\nBaseline total minutes:\nAI-assisted total minutes:\nReview minutes:\nRework minutes:\n\nWhat improved?\nWhat got worse?\nWhat will you change next week?\n","team-rollup.csv":"week,developer,tasks_completed,total_baseline_minutes,total_ai_work_minutes,total_rework_minutes,estimated_hours_saved\n2026-W01,Example,5,300,240,20,1\n"}},
{"name":"Freelancer Invoice Follow-Up Kit","slug":"freelancer-invoice-follow-up-kit","price_usd":9,"tagline":"A repeatable system for following up on unpaid invoices.","target":"freelancers, consultants, small agencies","files":{"quick-start.md":"# Quick Start\n\n1. Import outstanding invoices.\n2. Assign each invoice a follow-up stage.\n3. Use neutral reminder templates.\n4. Record response and payment dates.\n5. Review overdue amounts every Friday.\n","invoice-tracker.csv":"client,invoice_id,amount,currency,due_date,status,last_contact,next_contact,notes\nExample,INV-001,500,USD,2026-01-15,overdue,2026-01-22,2026-01-29,replace example\n","follow-up-templates.md":"# Follow-Up Templates\n\n## Friendly reminder\nHi [Name], just a quick reminder that invoice [ID] for [Amount] was due on [Date]. Please let me know if you need anything from me to process it. Thanks!\n\n## Second follow-up\nHi [Name], following up on invoice [ID]. Could you confirm the expected payment date? Thank you.\n","weekly-review.md":"# Weekly Review\n\nOutstanding amount:\nInvoices due this week:\nFollow-ups sent:\nPayments received:\nNext action:\n"}},
{"name":"Small Business Automation Audit Kit","slug":"small-business-automation-audit-kit","price_usd":15,"tagline":"Find repetitive work worth automating before buying another tool.","target":"solo businesses and small teams","files":{"audit-sheet.csv":"process,owner,frequency,minutes_per_run,monthly_runs,monthly_minutes,error_risk,customer_impact,automation_candidate,notes\nExample,Admin,weekly,60,4,240,medium,medium,yes,replace example\n","automation-scorecard.md":"# Automation Scorecard\n\nScore each workflow from 1–5 for frequency, time cost, error risk, standardization, and customer impact.\n","quick-start.md":"# Quick Start\n\n1. List 10 recurring processes.\n2. Estimate monthly time spent.\n3. Score repeatability and error risk.\n4. Select the top 3 candidates.\n5. Test one small automation.\n","pilot-plan.md":"# 7-Day Automation Pilot\n\nWorkflow:\nCurrent baseline:\nChange tested:\nSuccess metric:\nRisks:\nDay 1–2 setup:\nDay 3–5 pilot:\nDay 6 measurement:\nDay 7 decision:\n"}},
{"name":"Job Search Application Tracker Pro","slug":"job-search-application-tracker-pro","price_usd":9,"tagline":"Organize applications, follow-ups and interview preparation.","target":"job seekers and career changers","files":{"application-tracker.csv":"company,role,source,applied_date,status,next_action,next_date,contact,notes\nExample,Software Engineer,Job Board,2026-01-10,Applied,Follow up,2026-01-17,Recruiter,replace example\n","interview-prep.md":"# Interview Prep\n\nRole:\nTop requirements:\nThree relevant examples:\nQuestions to ask:\nTechnical topics to review:\nFollow-up date:\n","weekly-review.md":"# Weekly Review\n\nApplications sent:\nResponses:\nInterviews:\nFollow-ups due:\nWhat changed?\nNext week's target:\n","quick-start.md":"# Quick Start\n\nTrack every application immediately, set the next action, and review the pipeline twice a week.\n"}},
{"name":"AI Content Workflow Planner","slug":"ai-content-workflow-planner","price_usd":12,"tagline":"Plan, produce and review repeatable AI-assisted content.","target":"creators, marketers, solo businesses","files":{"content-pipeline.csv":"item,channel,goal,status,draft_date,review_date,publish_date,performance_metric,notes\nExample,LinkedIn,Lead generation,Idea,2026-01-10,2026-01-11,2026-01-12,Clicks,replace example\n","prompt-brief.md":"# Content Brief\n\nAudience:\nGoal:\nKey claim:\nEvidence/source:\nTone:\nCall to action:\nHuman review checklist:\n","quality-checklist.md":"# AI Content Quality Checklist\n\n- [ ] Claims verified\n- [ ] Sources checked\n- [ ] No invented quotations\n- [ ] Useful to target audience\n- [ ] Human editor reviewed\n- [ ] CTA matches goal\n","weekly-review.md":"# Weekly Review\n\nPieces published:\nHours spent:\nBest-performing item:\nWeakest item:\nWhat should be repeated?\nWhat should be stopped?\n"}}
]

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def build_product(p):
    path = os.path.join(OUT, p["slug"])
    os.makedirs(path, exist_ok=True)
    meta = {"name":p["name"],"slug":p["slug"],"price_usd":p["price_usd"],"status":"ready_for_sale","tagline":p["tagline"],"target_user":p["target"],"generated_at":datetime.now(timezone.utc).isoformat(),"files":list(p["files"].keys())}
    write(path+"/product.json", json.dumps(meta, ensure_ascii=False, indent=2))
    readme = "# "+p["name"]+"\n\n**"+p["tagline"]+"**\n\nDesigned for: "+p["target"]+".\n\n## Included\n"+"".join("- "+x+"\n" for x in p["files"])+"\n## Use\nDownload the files, replace the example rows/content, and run the workflow for one week.\n\n## Important\nThis is a practical template system, not a guarantee of results.\n\n## Suggested launch price\nUS$"+str(p["price_usd"])+" one-time.\n\n## License\nFor purchaser personal or internal business use. No redistribution or resale.\n"
    write(path+"/README.md", readme)
    for filename, body in p["files"].items():
        write(path+"/"+filename, body)
    items = "".join("<li>"+x+"</li>" for x in p["files"])
    html = "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+p["name"]+"</title></head><body><h1>"+p["name"]+"</h1><p><strong>"+p["tagline"]+"</strong></p><p>For "+p["target"]+".</p><h2>Included</h2><ul>"+items+"</ul><p><strong>US$"+str(p["price_usd"])+" one-time</strong></p><p>Ready for marketplace listing.</p><p><a href='README.md'>Product details</a></p></body></html>"
    write(path+"/index.html", html)
    return meta

def main():
    os.makedirs(OUT, exist_ok=True)
    products = [build_product(p) for p in PRODUCTS]
    with open("site/products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print("Generated "+str(len(products))+" paid-ready products")

if __name__ == "__main__":
    main()
