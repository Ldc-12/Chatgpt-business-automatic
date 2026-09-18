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

def fetch_trends(limit=20):
    req = Request(RSS_URL, headers={"User-Agent": "business-automatic/1.0"})
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
        error = None
    except Exception as exc:
        opportunities, status = [], f"feed_error: {type(exc).__name__}"
        error = str(exc)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "opportunities": opportunities[:10],
        "error": error,
        "next_step": (
            "Generate and test a small digital product. Paid deployment, "
            "payments, and external credentials remain gated."
        ),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/opportunities.json", "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
