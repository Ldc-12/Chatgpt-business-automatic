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


def test_default_license_paths_are_product_specific():
    first = lic.default_license_path("文件整理助手 Pro")
    second = lic.default_license_path("PDF批量工具 Pro")
    assert first != second
    assert first.parent.name == "licenses"
    assert first.name == "文件整理助手 Pro.json"
    assert second.name == "PDF批量工具 Pro.json"

def test_issue_license_cli_roundtrip_with_ephemeral_test_key(tmp_path, monkeypatch):
    """Exercise the real CLI against the client using a throwaway test key.

    This verifies signer/client format compatibility only. It does NOT verify
    that the seller's offline private key matches the production embedded key.
    """
    import subprocess
    import sys

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "temporary-test-only.pem"
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    product = "文件整理助手 Pro"
    device_code = lic.device_id(product)
    output_path = tmp_path / "issued" / "license.json"
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    result = subprocess.run(
        [
            sys.executable,
            "tools/issue_license.py",
            "--private-key", str(private_path),
            "--product", product,
            "--device-id", device_code,
            "--customer", "临时测试",
            "--license-id", "LIC-CLI-ROUNDTRIP",
            "--expires", "2099-12-31",
            "--out", str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output_path.is_file()

    monkeypatch.setattr(lic, "PUBLIC_KEY_PEM", public_pem)
    payload = lic.verify_license(product, output_path)
    assert payload["license_id"] == "LIC-CLI-ROUNDTRIP"
    assert payload["product"] == product
    assert payload["device_hash"] == device_code
    assert payload["expires_at"] == "2099-12-31"


def test_issue_license_cli_rejects_malformed_device_code(tmp_path):
    import subprocess
    import sys

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "temporary-test-only.pem"
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "tools/issue_license.py",
            "--private-key", str(private_path),
            "--product", "demo-product",
            "--device-id", "NOT-A-DEVICE-CODE",
            "--out", str(tmp_path / "should-not-exist.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "24-character hexadecimal device code" in result.stderr
    assert not (tmp_path / "should-not-exist.json").exists()
