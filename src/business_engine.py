import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

RSS_URL = "https://hnrss.org/newest?q=productivity"

KEYWORDS = (
    "template", "automation", "productivity", "invoice", "resume",
    "analytics", "workflow", "developer", "small business", "ai"
)

FALLBACK_OPPORTUNITIES = [
    {
        "idea": "Freelancer Invoice Follow-up Kit",
        "source": "https://hnrss.org/",
        "score": 10,
        "target_user": "freelancers and small agencies",
        "promise": "Reduce unpaid-invoice follow-up work with a repeatable 15-minute weekly workflow.",
    },
    {
        "idea": "AI Coding Task Time-Tracker",
        "source": "https://news.ycombinator.com/",
        "score": 9,
        "target_user": "software developers using AI coding tools",
        "promise": "Measure whether AI actually saves time by tracking task duration, rework, and review time.",
    },
    {
        "idea": "Small Business Automation Audit",
        "source": "https://news.ycombinator.com/",
        "score": 9,
        "target_user": "solo businesses and small teams",
        "promise": "Find three repetitive workflows that are candidates for automation and estimate their weekly time cost.",
    },
]

def fetch_trends(limit=20):
    req = Request(RSS_URL, headers={"User-Agent": "business-automatic/1.1"})
    with urlopen(req, timeout=20) as response:
        root = ET.fromstring(response.read())
    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "url": link})
    return items

def score(title):
    text = title.lower()
    return sum(2 for keyword in KEYWORDS if keyword in text)

def main():
    error = None
    try:
        trends = fetch_trends()
        opportunities = [
            {
                "idea": f"Micro-tool for: {item['title']}",
                "source": item["url"],
                "score": score(item["title"]),
            }
            for item in trends
        ]
        opportunities.sort(key=lambda item: item["score"], reverse=True)
        status = "live"
    except Exception as exc:
        opportunities = FALLBACK_OPPORTUNITIES
        status = f"fallback: {type(exc).__name__}"
        error = str(exc)

    if not opportunities:
        opportunities = FALLBACK_OPPORTUNITIES
        status = "fallback: empty_feed"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "opportunities": opportunities[:10],
        "error": error,
        "next_step": "Generate, publish, and validate small digital products before enabling paid deployment or payments.",
    }

    os.makedirs("data", exist_ok=True)
    with open("data/opportunities.json", "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
