"""Write per-product mainland README files as UTF-8 for Windows delivery."""
import argparse
from pathlib import Path


def render_mainland_readme(product):
    product_note = ""
    if product == "食品批次与保质期追踪助手":
        product_note = (
            "批次专业功能：按商品与批次管理生产/到期日期、供应商、库位和数量；"
            "FEFO 按最早到期批次优先分配出库，过期库存自动排除；"
            "入库、出库、调整、作废均保留批次流水，可按批次追溯去向和原因。\n"
            "效期按已过期、3 日内、4–7 日、8–30 日和正常分层；CSV 导入整批校验，备份包含完整库存流水。\n"
        )
    if product == "门店食品安全巡检与整改闭环助手":
        product_note = (
            "食品安全巡检专业功能：版本化 17 项门店检查清单、风险加权内部管理分、90 天重复问题识别、"
            "不合格责任人/期限约束、整改复查闭环及 SHA256 哈希链审计；CSV 导入会校验完整清单和规则版本。\\n"
            "清单为日常管理参考，不是完整法规数据库；温度阈值须按食品类别和当地适用要求确认，结果不构成监管合规结论。\\n"
        )
    if product == "售后纠纷证据链管理助手":
        product_note = (
            "售后专业功能：按案件管理平台、订单、纠纷类型和响应期限；归档聊天/订单/物流等本地文件并记录 SHA256；"
            "案件更新、状态变更和证据添加会追加哈希链事件，并绑定案件字段快照 SHA256；可导出仅含当前案件的证据包并校验完整性。\n"
            "哈希链仅用于发现本地记录变化，不证明来源、形成时间或法律效力；不自动连接或抓取交易平台。\n"
        )
    if product == "合同台账与到期提醒助手":
        product_note = (
            "合同专业功能：本地批量读取可搜索 PDF/DOCX/TXT/MD，生成待人工复核 CSV 草稿；"
            "规则集 CN-CONTRACT-2026.11.1 检查明确标注的总金额冲突、付款比例合计、日期冲突、"
            "保证金返还、违约金计算细节和自动续约通知窗口。风险明细附规则编号、原文行号和复核建议。\n"
            "识别草稿不会自动写入正式台账；复杂表格、扫描件和特殊条款仍须人工核对，结果不构成法律意见。\n"
        )
    return (
        f"{product}\n"
        "Windows 单机版｜大陆版\n\n"
        "首次启动会显示本机设备码，需由卖家签发该产品专属授权后才能使用。"
        "请把授权文件放入 %LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\产品名.json。"
        "数据默认保存在当前用户的 %LOCALAPPDATA%\\MainlandBusinessTools 目录。\n"
        f"{product_note}"
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
