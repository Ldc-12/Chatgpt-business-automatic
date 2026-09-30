from pathlib import Path
import importlib.util, tempfile
from pypdf import PdfWriter, PdfReader

def load():
    spec=importlib.util.spec_from_file_location("pdf_tool",Path("apps/PDF批量工具Pro.py"))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_merge_split():
    m=load()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); src=p/"a.pdf"; w=PdfWriter(); w.add_blank_page(300,400); w.add_blank_page(300,400)
        with open(src,"wb") as h:w.write(h)
        out=p/"merged.pdf"; m.merge([src],out); assert len(PdfReader(out).pages)==2
        assert len(m.split(src,p/"parts"))==2
