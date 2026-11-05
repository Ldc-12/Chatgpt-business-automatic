import base64
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import license as lic
from tools.export_license_public_key import export_public_key
from tools.issue_license import issue_license


def _write_private_key(path, private):
    path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _public_pem(private):
    return private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def test_device_id_is_stable():
    value = lic.device_id("demo-product")
    assert len(value) == 24
    assert value == lic.device_id("demo-product")


def test_signed_license_roundtrip(tmp_path):
    private = Ed25519PrivateKey.generate()
    old = lic.PUBLIC_KEY_PEM
    lic.PUBLIC_KEY_PEM = _public_pem(private)
    try:
        payload = {
            "license_id": "LIC-TEST",
            "product": "demo-product",
            "customer": "test",
            "device_hash": lic.device_id("demo-product"),
            "issued_at": dt.date.today().isoformat(),
            "expires_at": "2099-12-31",
        }
        signature = private.sign(lic._canonical(payload))
        path = tmp_path / "license.json"
        path.write_text(
            json.dumps(
                {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}
            ),
            encoding="utf-8",
        )
        result = lic.verify_license("demo-product", path)
        assert result["license_id"] == "LIC-TEST"
    finally:
        lic.PUBLIC_KEY_PEM = old


def test_wrong_device_rejected(tmp_path):
    private = Ed25519PrivateKey.generate()
    old = lic.PUBLIC_KEY_PEM
    lic.PUBLIC_KEY_PEM = _public_pem(private)
    try:
        payload = {
            "license_id": "LIC-TEST",
            "product": "demo-product",
            "customer": "",
            "device_hash": "WRONGDEVICE12345678901234",
            "issued_at": "2026-01-01",
            "expires_at": "2099-12-31",
        }
        signature = private.sign(lic._canonical(payload))
        path = tmp_path / "license.json"
        path.write_text(
            json.dumps({"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}),
            encoding="utf-8",
        )
        try:
            lic.verify_license("demo-product", path)
        except lic.LicenseError as exc:
            assert "其他电脑" in str(exc)
        else:
            raise AssertionError("wrong device accepted")
    finally:
        lic.PUBLIC_KEY_PEM = old


def test_default_license_paths_match_all_protected_product_ids():
    products = [
        "文件整理助手 Pro",
        "图片批量处理助手 Pro",
        "PDF批量工具 Pro",
        "自由职业催款管理工具",
        "轻量销售客户跟进工具",
        "求职申请管理Pro",
        "小微企业经营收支管理",
        "会议行动项管理",
        "SOP项目执行管理",
        "小店库存盘点助手",
        "供应商采购比价助手",
        "报价单生成器",
        "费用报销管理助手",
    ]
    paths = [lic.default_license_path(product) for product in products]
    assert len(set(paths)) == len(products)
    assert all(path.parent.name == "licenses" for path in paths)
    assert [path.name for path in paths] == [f"{product}.json" for product in products]


def test_issue_license_signer_client_roundtrip_with_ephemeral_test_key(tmp_path, monkeypatch):
    """Test signer/client format compatibility with a disposable test-only key."""
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "temporary-test-only.pem"
    _write_private_key(private_path, private)
    monkeypatch.setattr(lic, "PUBLIC_KEY_PEM", _public_pem(private))

    product = "文件整理助手 Pro"
    device_code = lic.device_id(product)
    issued = issue_license(
        private_path,
        product,
        device_code,
        customer="临时测试",
        license_id="LIC-CLI-ROUNDTRIP",
        expires="2099-12-31",
    )
    output_path = tmp_path / "issued" / "license.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_text(json.dumps(issued, ensure_ascii=False), encoding="utf-8")

    payload = lic.verify_license(product, output_path)
    assert payload["license_id"] == "LIC-CLI-ROUNDTRIP"
    assert payload["product"] == product
    assert payload["device_hash"] == device_code
    assert payload["expires_at"] == "2099-12-31"


def test_issue_license_cli_rejects_mismatched_seller_key(tmp_path):
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "temporary-test-only.pem"
    _write_private_key(private_path, private)
    output_path = tmp_path / "should-not-exist.json"

    result = subprocess.run(
        [
            sys.executable,
            "tools/issue_license.py",
            "--private-key", str(private_path),
            "--product", "文件整理助手 Pro",
            "--device-id", lic.device_id("文件整理助手 Pro"),
            "--out", str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    # ASCII marker is stable across Windows console encodings.
    assert "LICENSE_KEY_MISMATCH" in result.stderr
    assert "SHA256=" in result.stderr
    assert not output_path.exists()


def test_issue_license_cli_rejects_malformed_device_code(tmp_path):
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "temporary-test-only.pem"
    _write_private_key(private_path, private)
    output_path = tmp_path / "should-not-exist.json"

    result = subprocess.run(
        [
            sys.executable,
            "tools/issue_license.py",
            "--private-key", str(private_path),
            "--product", "demo-product",
            "--device-id", "NOT-A-DEVICE-CODE",
            "--out", str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "24-character hexadecimal device code" in result.stderr
    assert not output_path.exists()


def test_export_public_key_outputs_public_pem_and_der_fingerprint(tmp_path):
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "seller-test-only.pem"
    _write_private_key(private_path, private)

    public_pem, fingerprint = export_public_key(private_path)
    public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert public_pem == _public_pem(private)
    assert fingerprint == hashlib.sha256(der).hexdigest().upper()
    assert "PRIVATE KEY" not in public_pem


def test_expired_signed_license_is_rejected(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "PUBLIC_KEY_PEM", _public_pem(private))
    product = "demo-product"
    payload = {
        "license_id": "LIC-EXPIRED",
        "product": product,
        "customer": "",
        "device_hash": lic.device_id(product),
        "issued_at": "2020-01-01",
        "expires_at": "2000-01-01",
    }
    signature = base64.b64encode(private.sign(lic._canonical(payload))).decode("ascii")
    path = tmp_path / "expired.json"
    path.write_text(
        json.dumps({"payload": payload, "signature": signature}),
        encoding="utf-8",
    )
    try:
        lic.verify_license(product, path)
    except lic.LicenseError as exc:
        assert "到期" in str(exc)
    else:
        raise AssertionError("expired license was accepted")


def test_tampered_signature_is_rejected(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "PUBLIC_KEY_PEM", _public_pem(private))
    product = "demo-product"
    payload = {
        "license_id": "LIC-TAMPER",
        "product": product,
        "customer": "",
        "device_hash": lic.device_id(product),
        "issued_at": dt.date.today().isoformat(),
        "expires_at": "2099-12-31",
    }
    signature = bytearray(private.sign(lic._canonical(payload)))
    signature[0] ^= 0x01
    path = tmp_path / "tampered.json"
    path.write_text(
        json.dumps(
            {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}
        ),
        encoding="utf-8",
    )
    try:
        lic.verify_license(product, path)
    except lic.LicenseError as exc:
        assert "签名验证失败" in str(exc)
    else:
        raise AssertionError("tampered signature was accepted")
