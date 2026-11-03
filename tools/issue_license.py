"""Issue an Ed25519 product-bound license file.

The seller private key must remain on the seller's trusted machine. This tool
never writes or uploads the private key; it only reads the path supplied by
the seller and emits a signed JSON license. Before signing, it verifies that
the private key matches the public key embedded in the client.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def public_key_der(public_key):
    return public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def public_key_fingerprint(public_key):
    return hashlib.sha256(public_key_der(public_key)).hexdigest().upper()


def build_payload(product, device_id, customer="", license_id="", expires="2099-12-31"):
    product = product.strip()
    device_id = device_id.strip().upper()
    if not product:
        raise ValueError("product must not be empty")
    if not re.fullmatch(r"[0-9A-F]{24}", device_id):
        raise ValueError("device-id must be the 24-character hexadecimal device code")
    try:
        expires = dt.date.fromisoformat(expires).isoformat()
    except ValueError as exc:
        raise ValueError("expires must be a valid ISO date (YYYY-MM-DD)") from exc

    return {
        "license_id": license_id.strip() or "LIC-" + uuid.uuid4().hex[:12].upper(),
        "product": product,
        "customer": customer,
        "device_hash": device_id,
        "issued_at": dt.date.today().isoformat(),
        "expires_at": expires,
    }


def issue_license(private_key_path, product, device_id, customer="", license_id="", expires="2099-12-31"):
    private_key = serialization.load_pem_private_key(
        Path(private_key_path).read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("private key must be an Ed25519 PEM key")

    # Validate the request first, then fail closed if the seller key cannot
    # produce signatures accepted by the shipped client.
    payload = build_payload(product, device_id, customer, license_id, expires)

    from src import license as client_license

    client_public_key = serialization.load_pem_public_key(
        client_license.PUBLIC_KEY_PEM.encode("ascii")
    )
    seller_public_key = private_key.public_key()
    client_fingerprint = public_key_fingerprint(client_public_key)
    seller_fingerprint = public_key_fingerprint(seller_public_key)
    if public_key_der(client_public_key) != public_key_der(seller_public_key):
        raise ValueError(
            "卖家私钥与客户端内嵌公钥不匹配，已拒绝签发。"
            f"卖家公钥 SHA256={seller_fingerprint}；"
            f"客户端公钥 SHA256={client_fingerprint}。"
            "请勿替换客户端公钥，也不要上传或发送私钥。"
        )

    signature = private_key.sign(canonical(payload))
    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="为指定产品和设备码签发离线授权文件")
    parser.add_argument("--private-key", required=True, help="卖家本地 Ed25519 私钥 PEM 路径")
    parser.add_argument("--product", required=True, help="必须与客户端产品名完全一致")
    parser.add_argument("--device-id", required=True, help="客户端显示的 24 位设备码")
    parser.add_argument("--customer", default="")
    parser.add_argument("--license-id", default="")
    parser.add_argument("--expires", default="2099-12-31", help="到期日 YYYY-MM-DD")
    parser.add_argument("--out", default="license.json")
    args = parser.parse_args(argv)

    try:
        license_data = issue_license(
            args.private_key,
            args.product,
            args.device_id,
            args.customer,
            args.license_id,
            args.expires,
        )
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(license_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))

    print(f"LICENSE_CREATED {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
