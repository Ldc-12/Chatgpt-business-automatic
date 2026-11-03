"""Write the per-product README as UTF-8, avoiding Windows PowerShell 5.1 code-page conversion."""
import argparse
from pathlib import Path


def render_mainland_readme(product):
    return (
        f"{product}\n"
        "Windows 单机版｜大陆版\n\n"
        "首次启动会显示本机设备码，需由卖家签发该产品专属授权后才能使用。"
        "请把授权文件放入 %LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\产品名.json。"
        "数据默认保存在当前用户的 %LOCALAPPDATA%\\MainlandBusinessTools 目录。\n"
        "本工具无需 ChatGPT、VPN 或外部 AI 服务。\n"
        "首次使用建议：先添加一条测试数据，确认保存、编辑、删除和 CSV 导出正常，再录入正式数据。\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True)
    parser.add_argument("--output", default="dist/README-mainland.txt")
    args = parser.parse_args(argv)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    content = render_mainland_readme(args.product)
    output.write_text(content, encoding="utf-8-sig", newline="")
    verified = output.read_text(encoding="utf-8-sig")
    if "Windows 单机版" not in verified or "本工具无需 ChatGPT" not in verified:
        raise SystemExit("README UTF-8 content verification failed")
    if "å" in verified or "Ã" in verified:
        raise SystemExit("README contains likely mojibake")
    print(f"README_UTF8_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
