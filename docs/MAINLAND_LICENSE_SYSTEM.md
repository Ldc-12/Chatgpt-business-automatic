# Mainland Windows License System

The nine standalone mainland Windows EXEs enforce a signed offline license tied to the Windows machine. The launcher is only a menu; each product EXE performs its own license check before opening.

Protected products (the product name must match exactly when issuing a license):
- 文件整理助手 Pro
- 图片批量处理助手 Pro
- PDF批量工具 Pro
- 自由职业催款管理工具
- 轻量销售客户跟进工具
- 求职申请管理Pro
- 小微企业经营收支管理
- 会议行动项管理
- SOP项目执行管理

## Customer flow

1. Customer starts the individual EXE.
2. Without a valid license, the EXE displays a product-specific device code.
3. Seller generates a signed `license.json` for that exact product and device code.
4. Customer places it at `%LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\<产品名>.json`.
5. The EXE verifies signature, product name, device binding and expiry before opening.

A copied EXE without its matching license cannot be used, and a copied license fails on another computer. The EXE contains only the public Ed25519 key. The seller private key must be stored offline and must never be committed to GitHub.

## Verify the seller key before issuing

The signer now compares the seller private key's derived public key with the public key embedded in `src/license.py`. If they differ, it refuses to create a license and prints both SHA256 fingerprints. This prevents the seller from accidentally issuing a file that the shipped EXE cannot verify.

On the seller's trusted Windows PC, run the following from a local copy of the project:

```powershell
py tools/export_license_public_key.py --private-key "C:\secure\seller-private.pem"
```

The command prints a public PEM and a `SHA256=` fingerprint. Send only the fingerprint (or public PEM) for comparison. **Never send, upload, or commit the private key.** The private key is read locally and is not transmitted.

Current reference fingerprints (SHA256 of DER-encoded SubjectPublicKeyInfo):
- Client embedded key in `src/license.py`: `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`
- Separate file `config/mainland_license_public_key.pem`: `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`

These are different keys. The client currently verifies with the embedded key only; the config file is not an automatic fallback. Do not replace either key until the seller's actual public-key fingerprint is confirmed and a deliberate key-rotation plan is agreed.

## Issue a license

Use `tools/issue_license.py` on a trusted computer with the seller's private key file. The signer will stop if the private key does not match the embedded client key. Create the `licenses` folder under `%LOCALAPPDATA%\\MainlandBusinessTools` on the customer's PC, then place each product's license file there using the product-specific filename (for example, `文件整理助手 Pro.json`):

```powershell
py tools/issue_license.py --private-key "C:\secure\seller-private.pem" --product "文件整理助手 Pro" --device-id "CUSTOMER_DEVICE_CODE" --customer "订单备注" --expires 2099-12-31 --out "文件整理助手 Pro.json"
```

Replace the product, device code, customer note and expiry with the actual order details. Deliver the generated file only to that buyer and that device. Never ask customers to send passwords, ID documents or other unnecessary sensitive information.

This is anti-sharing protection, not unbreakable DRM. A future server-backed activation service can add revocation and automated fulfillment.
