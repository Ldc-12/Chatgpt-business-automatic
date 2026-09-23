import argparse,base64,datetime as dt,json,uuid
from pathlib import Path
from cryptography.hazmat.primitives import serialization
def canonical(p): return json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
ap=argparse.ArgumentParser()
ap.add_argument("--private-key",required=True); ap.add_argument("--product",required=True); ap.add_argument("--device-id",required=True)
ap.add_argument("--customer",default=""); ap.add_argument("--license-id",default=""); ap.add_argument("--expires",default="2099-12-31"); ap.add_argument("--out",default="license.json")
a=ap.parse_args()
private=serialization.load_pem_private_key(Path(a.private_key).read_bytes(),password=None)
payload={"license_id":a.license_id or "LIC-"+uuid.uuid4().hex[:12].upper(),"product":a.product,"customer":a.customer,"device_hash":a.device_id.strip().upper(),"issued_at":dt.date.today().isoformat(),"expires_at":a.expires}
sig=private.sign(canonical(payload))
Path(a.out).write_text(json.dumps({"payload":payload,"signature":base64.b64encode(sig).decode()},ensure_ascii=False,indent=2),encoding="utf-8")
print("LICENSE_CREATED",a.out)
