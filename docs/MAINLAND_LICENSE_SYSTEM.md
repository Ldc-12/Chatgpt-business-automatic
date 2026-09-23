# Mainland Windows License System

The six mainland Windows EXEs now use a signed offline license tied to the Windows machine.

Customer flow:
1. Start the EXE.
2. The EXE displays a product-specific device code.
3. Seller generates a signed license.json for that device.
4. Customer places it at %LOCALAPPDATA%\\MainlandBusinessTools\\license.json.
5. The EXE verifies signature, product, device binding and expiry before opening.

A copied EXE without its matching license cannot be used, and a copied license fails on another computer.

The EXE contains only the public Ed25519 key. The seller private key must never enter GitHub.

This is anti-sharing protection, not unbreakable DRM. A future server-backed activation service can add revocation and automated fulfillment.
