import base64,datetime as dt,json,tempfile
from pathlib import Path
from src import license as lic

def test_device_id_is_stable():
    a=lic.device_id("demo-product")
    assert len(a)==24 and a==lic.device_id("demo-product")

def test_signed_license_roundtrip(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    private=Ed25519PrivateKey.generate()
    public=private.public_key()
    old=lic.PUBLIC_KEY_PEM
    lic.PUBLIC_KEY_PEM=public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    try:
        payload={"license_id":"LIC-TEST","product":"demo-product","customer":"test","device_hash":lic.device_id("demo-product"),"issued_at":dt.date.today().isoformat(),"expires_at":"2099-12-31"}
        sig=private.sign(lic._canonical(payload))
        p=tmp_path/"license.json"
        p.write_text(json.dumps({"payload":payload,"signature":base64.b64encode(sig).decode()}),encoding="utf-8")
        got=lic.verify_license("demo-product",p)
        assert got["license_id"]=="LIC-TEST"
    finally:
        lic.PUBLIC_KEY_PEM=old

def test_wrong_device_rejected(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    private=Ed25519PrivateKey.generate(); public=private.public_key()
    old=lic.PUBLIC_KEY_PEM
    lic.PUBLIC_KEY_PEM=public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    try:
        payload={"license_id":"LIC-TEST","product":"demo-product","customer":"","device_hash":"WRONGDEVICE12345678901234","issued_at":"2026-01-01","expires_at":"2099-12-31"}
        sig=private.sign(lic._canonical(payload))
        p=tmp_path/"license.json"; p.write_text(json.dumps({"payload":payload,"signature":base64.b64encode(sig).decode()}),encoding="utf-8")
        try: lic.verify_license("demo-product",p)
        except lic.LicenseError as e: assert "其他电脑" in str(e)
        else: raise AssertionError("wrong device accepted")
    finally: lic.PUBLIC_KEY_PEM=old
