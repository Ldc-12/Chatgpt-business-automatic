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
            "不合格责任人/期限约束、整改复查闭环及 SHA256 哈希链审计；CSV 导入校验完整清单和规则版本。\n"
            "清单仅作日常管理参考，温度阈值须按食品类别和当地适用要求确认；结果不构成监管合规结论。\n"
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
    if product == "供应商对账与应付账龄管理助手":
        product_note = (
            "供应商应付专业功能：按供应商与发票号管理应付单据、到期日期和分笔付款；"
            "自动计算未付余额及未到期、逾期 1–30/31–60/61–90/90 天以上账龄；"
            "导入供应商对账单 CSV 后核对发票号、日期、金额和供应商名称，并导出差异清单。\n"
            "付款需手工关联到单据；对账仅作本地数据比对，不连接银行或供应商系统，不自动付款。\n"
        )
    if product == "装修材料用量与预算核算助手":
        product_note = (
            "装修材料专业功能：按项目、房间和材料编码建立清单，按净用量、损耗率、包装规格和单价计算计划用量，并向上取整到整包装后估算采购量和预算；"
            "录入实际采购金额后比较预算差额；提供瓷砖片数/整箱数和乳胶漆升数计算器。\n"
            "计算结果依赖用户复尺、产品包装和厂家涂布率；异形铺贴、施工图工程量、现场损耗及合同计价仍须人工复核，不代替专业施工人员复核，也不构成造价鉴定。\n"
        )
    if product == "闲鱼订单利润与售后成本核算助手":
        product_note = (
            "闲鱼卖家专业功能：按订单/SKU核算买家实付、退款、商品与包装成本、发货/退货运费、推广费和售后补偿；"
            "平台费率/固定费用仅作可配置估算，填写实际平台费用后优先采用实际值；提供月度利润、SKU 汇总和保本售价计算。\n"
            "不连接闲鱼账号、不抓取订单、不代表平台收费政策；请以本单实际账单和卖家录入数据为准。\\n"
        )
    if product == "闲鱼二手商品定价与议价助手":
        product_note = (
            "闲鱼二手定价专业功能：规则集 XY-USED-PRICE-2026.11 按品类和购入月数应用折旧系数，"
            "结合成色、配件/瑕疵扣减及卖家手工录入的同类成交中位价；同时计算含平台费、整备、包装运费和售后预留的最低接受价，"
            "并按议价空间生成建议标价。支持复制基础上架文案、品类汇总、CSV、SHA256 备份恢复。\n"
            "折旧系数仅为透明的初始参考规则，不是实时行情或平台估价；同类成交价需卖家手工核实，不连接或抓取闲鱼。\\n"
        )
    if product == "设备维保巡检与保养计划助手":
        product_note = (
            "设备维保专业功能：按设备类别提供可调整的周期提醒默认值，维护设备台账、保修到期、"
            "例行保养/故障维修/巡检记录、验收状态、停机时长和费用；自动计算下次保养日期，"
            "按逾期、14 天内到期、待验收和设备状态生成可解释风险清单。\n"
            "周期默认值不是法定检验要求或厂家标准；软件不连接设备、不作安全鉴定，消防/电梯等专业项目须按规定委托合格人员。\n"
        )
    if product == "闲鱼商品发布管理助手":
        product_note = (
            "闲鱼发布管理专业功能：本地维护商品编号、SKU、成色、标价、最低接受价、库存和发布状态；"
            "按实际上架/最后刷新日期及自设间隔计算待刷新清单，支持草稿、待上架、在售、暂停、售出和下架状态流转；"
            "生成不含最低接受价和内部备注的发布文案，支持安全 CSV 和 SHA256 备份恢复。\\n"
            "不连接或抓取闲鱼，不自动发布、改价、刷新或联系买家；刷新提醒仅为本地日期计算。\\n"
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
