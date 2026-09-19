import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PRODUCT_BY_PAYMENT_LINK = {
    # Fill with Payment Link IDs when configuring the webhook.
}

def verify_signature(payload: bytes, signature: str, secret: str, tolerance: int = 300) -> bool:
    parts = {}
    for item in signature.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)

    timestamps = parts.get("t", [])
    signatures = parts.get("v1", [])
    if not timestamps or not signatures:
        return False

    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False

    if abs(int(time.time()) - timestamp) > tolerance:
        return False

    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/stripe/webhook":
            self.send_json(404, {"error": "not_found"})
            return

        secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            self.send_json(500, {"error": "missing_webhook_secret"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        signature = self.headers.get("Stripe-Signature", "")

        if not verify_signature(payload, signature, secret):
            self.send_json(400, {"error": "invalid_signature"})
            return

        event = json.loads(payload.decode("utf-8"))
        event_type = event.get("type")

        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            if session.get("payment_status") != "paid":
                self.send_json(200, {"received": True, "fulfilled": False})
                return

            metadata = session.get("metadata", {})
            product_slug = metadata.get("product_slug")
            if not product_slug:
                self.send_json(200, {"received": True, "fulfilled": False, "reason": "missing_product_slug"})
                return

            # Production implementation should create a short-lived, single-use
            # download token or send a delivery email here. Do not expose Stripe
            # secrets or grant access based only on a client-supplied session ID.
            print(json.dumps({
                "event": "paid_order",
                "session_id": session.get("id"),
                "product_slug": product_slug,
                "customer_email": session.get("customer_details", {}).get("email"),
            }, ensure_ascii=False))
            self.send_json(200, {"received": True, "fulfilled": True})
            return

        self.send_json(200, {"received": True})

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
