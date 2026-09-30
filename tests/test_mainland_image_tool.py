from pathlib import Path
import importlib.util, tempfile
from PIL import Image

def load():
    spec=importlib.util.spec_from_file_location("image_tool",Path("apps/图片批量处理助手Pro.py"))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_process():
    m=load()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); src=p/"a.png"; Image.new("RGB",(2000,1000),"white").save(src)
        out=m.process(src,p/"out",800,80,"JPEG")
        assert out.exists() and Image.open(out).width<=800
