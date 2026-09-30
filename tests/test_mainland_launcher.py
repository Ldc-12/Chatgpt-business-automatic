from pathlib import Path
def test_launcher_inventory():
    p=Path("apps/实用效率工具箱.py").read_text(encoding="utf-8")
    assert "MainlandFileOrganizerPro.exe" in p
    assert "MainlandImageToolPro.exe" in p
    assert "MainlandPDFToolPro.exe" in p
