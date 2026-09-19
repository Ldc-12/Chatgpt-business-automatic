import hashlib
import hmac
import time

from stripe_webhook import verify_signature


def test_verify_signature_accepts_valid_signature():
    payload = b'{"type":"checkout.session.completed"}'
    timestamp = int(time.time())
    secret = "whsec_test"
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    assert verify_signature(payload, signature, secret)


def test_verify_signature_rejects_invalid_signature():
    payload = b'{"type":"checkout.session.completed"}'
    timestamp = int(time.time())
    assert not verify_signature(payload, f"t={timestamp},v1=bad", "whsec_test")
