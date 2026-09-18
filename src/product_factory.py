import json, os, re
from datetime import datetime, timezone

REPORT="data/opportunities.json"
OUT="site/products"

def slug(text):
    return re.sub(r"[^a-z0-9]+","-",text.lower()).strip("-")[:70] or "micro-product"

def build_product(item, index):
    title=item["idea"].replace("Micro-tool for: ","").strip()
    s=slug(title)
    product={
        "name": f"{title} — Quickstart Kit",
        "slug": s,
        "description": f"A practical starter kit inspired by: {title}. Includes a concise workflow, checklist, and reusable templates.",
        "source": item.get("source",""),
        "score": item.get("score",0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price": 0,
        "status": "free_validation"
    }
    os.makedirs(f"{OUT}/{s}",exist_ok=True)
    with open(f"{OUT}/{s}/product.json","w",encoding="utf-8") as f:
        json.dump(product,f,ensure_ascii=False,indent=2)
    with open(f"{OUT}/{s}/README.md","w",encoding="utf-8") as f:
        f.write(f"# {product['name']}\n\n{product['description']}\n\n## What is included\n- 1-page workflow\n- Action checklist\n- Reusable template\n- Validation notes\n\n**Validation mode:** free. Payment is intentionally disabled until a provider is configured.\n")
    return product

def main():
    if not os.path.exists(REPORT):
        raise SystemExit("Opportunity report not found")
    with open(REPORT,encoding="utf-8") as f:
        report=json.load(f)
    products=[build_product(x,i) for i,x in enumerate(report.get("opportunities",[])[:5])]
    os.makedirs("site",exist_ok=True)
    with open("site/products.json","w",encoding="utf-8") as f:
        json.dump(products,f,ensure_ascii=False,indent=2)
    print(f"Generated {len(products)} validation products")

if __name__=="__main__":
    main()
