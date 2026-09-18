import json, os, re
from datetime import datetime, timezone

REPORT = "data/opportunities.json"
OUT = "site/products"

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70] or "micro-product"

def build_product(item, index):
    title = item["idea"].replace("Micro-tool for: ", "").strip()
    s = slug(title)
    # Convert a source signal into a concrete validation offer.\n    product = {
        "name": f"{title} — Action Kit",
        "slug": s,
        "description": f"A 7-day experiment kit to test whether {title.lower()} solves a measurable workflow problem.",
        "source": item.get("source", ""),
        "score": item.get("score", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price": 0,
        "status": "free_validation",\n        "validation_question": "Would a user save enough time, money, or errors to pay for a deeper version?"
    }
    path = f"{OUT}/{s}"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/product.json", "w", encoding="utf-8") as f:
        json.dump(product, f, ensure_ascii=False, indent=2)
    workflow = ["Define the outcome and current baseline.", "Choose one repeatable workflow to improve.", "Run it for 7 days and record time, quality, and exceptions.", "Review the measurements and keep only changes that improve the baseline."]
    checklist = ["Write the desired outcome in one sentence.", "Record the current process before changing it.", "Set one measurable success metric.", "Run a small pilot before wider rollout.", "Document the final repeatable process."]
    template = "Goal:\nCurrent process:\nBaseline metric:\nChange tested:\nResult after 7 days:\nDecision:\nNext experiment:"
    with open(f"{path}/action-kit.md", "w", encoding="utf-8") as f:
        f.write(f"# {product['name']}\n\n{product['description']}\n\n## 7-day workflow\n")
        f.write("".join(f"{i+1}. {x}\n" for i, x in enumerate(workflow)))
        f.write("\n## Checklist\n" + "".join(f"- [ ] {x}\n" for x in checklist))
        f.write(f"\n## Experiment template\n\n{template}\n\nSource: {product['source']}\n\nValidation mode: free.\n")
    with open(f"{path}/index.html", "w", encoding="utf-8") as f:
        f.write(f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{product['name']}</title></head><body><h1>{product['name']}</h1><p>{product['description']}</p><p>7-day workflow · checklist · experiment template</p><p><a href='action-kit.md'>Open the Action Kit</a></p><small>Free validation edition · <a href='{product['source']}'>Source</a></small></body></html>")
    return product

def main():
    if not os.path.exists(REPORT):
        raise SystemExit("Opportunity report not found")
    with open(REPORT, encoding="utf-8") as f:
        report = json.load(f)
    products = [build_product(x, i) for i, x in enumerate(report.get("opportunities", [])[:5])]
    os.makedirs("site", exist_ok=True)
    with open("site/products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"Generated {len(products)} validation products")

if __name__ == "__main__":
    main()
