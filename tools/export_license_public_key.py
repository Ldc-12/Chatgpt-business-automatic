"""Export only the public key corresponding to a local seller private key.

Run this on the seller's trusted Windows PC. The private key is read locally,
never printed, written, uploaded, or transmitted.
"""
import argparse
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def export_public_key(private_key_path):
    private_key = serialization.load_pem_private_key(
        Path(private_key_path).read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("private key must be an Ed25519 PEM key")

    public_key = private_key.public_key()
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    fingerprint = hashlib.sha256(public_der).hexdigest().upper()
    return public_pem, fingerprint


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="在本机从卖家私钥导出公钥 PEM 和 SHA256 指纹；不会输出私钥。"
    )
    parser.add_argument("--private-key", required=True, help="卖家本地 Ed25519 私钥 PEM 路径")
    args = parser.parse_args(argv)

    try:
        public_pem, fingerprint = export_public_key(args.private_key)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))

    print("PUBLIC_KEY_PEM_BEGIN")
    print(public_pem, end="")
    print("PUBLIC_KEY_PEM_END")
    print(f"SHA256={fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
