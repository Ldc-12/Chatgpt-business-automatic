import base64, datetime as dt, hashlib, json, os, platform, sys
from pathlib import Path
PUBLIC_KEY_PEM = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAOYI/eZX4VQ8loFYOyz9qyha/3fGtGPkIELoQIHz6HRE=\n-----END PUBLIC KEY-----\n"
DEFAULT_LICENSE_PATH = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "MainlandBusinessTools" / "license.json"
class LicenseError(Exception): pass
def machine_id():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
        except Exception: pass
    return platform.node().strip() or "unknown-device"
def device_id(product):
    return hashlib.sha256((product + "|" + machine_id()).encode("utf-8")).hexdigest()[:24].upper()
def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
def _verify(payload, signature):
    try:
        from cryptography.hazmat.primitives import serialization
        pub = serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode("ascii"))
        pub.verify(base64.b64decode(signature), _canonical(payload))
        return True
    except Exception: return False
def verify_license(product, path=None):
    p=Path(path or DEFAULT_LICENSE_PATH)
    if not p.exists(): raise LicenseError(f"未找到授权文件。\n设备码：{device_id(product)}\n授权文件：{p}")
    try:
        data=json.loads(p.read_text(encoding="utf-8")); payload=data["payload"]; signature=data["signature"]
    except Exception as exc: raise LicenseError(f"授权文件格式无效：{exc}")
    if payload.get("product") != product: raise LicenseError("该授权文件不属于此产品。")
    if payload.get("device_hash") != device_id(product): raise LicenseError(f"该授权已绑定其他电脑。\n本机设备码：{device_id(product)}")
    expires=str(payload.get("expires_at","2099-12-31"))
    try:
        if dt.date.today() > dt.date.fromisoformat(expires): raise LicenseError(f"授权已于 {expires} 到期。")
    except ValueError: raise LicenseError("授权到期日期无效。")
    if not _verify(payload, signature): raise LicenseError("授权签名验证失败，文件可能被修改。")
    return payload
def activation_message(product):
    return f"首次使用需要激活。\n\n产品：{product}\n设备码：{device_id(product)}\n\n请将设备码提供给卖家，卖家会生成专属授权文件。\n授权文件放入：%LOCALAPPDATA%\\MainlandBusinessTools\\license.json"
def require_license(product):
    if "--self-test" in sys.argv or os.getenv("LICENSE_SELF_TEST")=="1": return {"product":product,"self_test":True}
    try: return verify_license(product)
    except LicenseError as exc:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk(); root.withdraw(); messagebox.showerror("产品未激活",str(exc)+"\n\n"+activation_message(product)); root.destroy()
        except Exception: print(str(exc),file=sys.stderr)
        raise SystemExit(2)
