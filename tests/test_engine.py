from src.business_engine import score

def test_score():
    assert score("automation productivity workflow") > 0
