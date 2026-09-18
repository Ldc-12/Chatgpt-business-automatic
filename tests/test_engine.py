from src.business_engine import score
from src.product_factory import PRODUCTS

def test_score():
    assert score("automation productivity workflow") > 0

def test_paid_catalog_is_valid():
    assert len(PRODUCTS) >= 5
    slugs = [p["slug"] for p in PRODUCTS]
    assert len(slugs) == len(set(slugs))
    for product in PRODUCTS:
        assert product["price_usd"] > 0
        assert product["tagline"]
        assert product["target"]
        assert product["files"]
        assert "README.md" not in product["files"]
        for filename, body in product["files"].items():
            assert filename
            assert body.strip()
