"""Build independent mainland Windows product-series ZIP packages.

The five series are disjoint and cover all business apps exactly once.
The all-in-one F package remains the main Phase 1 customer package.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import zipfile


PRODUCTS = {
    "file-organizer": ("文件整理助手 Pro", "MainlandFileOrganizerPro.exe", "01-文件整理助手Pro-用户说明书.md"),
    "image-tool": ("图片批量处理助手 Pro", "MainlandImageToolPro.exe", "02-图片批量处理助手Pro-用户说明书.md"),
    "pdf-tool": ("PDF 批量工具 Pro", "MainlandPDFToolPro.exe", "03-PDF批量工具Pro-用户说明书.md"),
    "freelancer": ("自由职业催款管理工具", "MainlandFreelancerTool.exe", "04-自由职业催款管理工具-用户说明书.md"),
    "sales": ("轻量销售客户跟进工具", "MainlandSalesFollowupTool.exe", "05-轻量销售客户跟进工具-用户说明书.md"),
    "jobs": ("求职申请管理 Pro", "MainlandJobTrackerPro.exe", "06-求职申请管理Pro-用户说明书.md"),
    "finance": ("小微企业经营收支管理", "MainlandSmallBusinessFinance.exe", "07-小微企业经营收支管理-用户说明书.md"),
    "meetings": ("会议行动项管理", "MainlandMeetingActions.exe", "08-会议行动项管理-用户说明书.md"),
    "sop": ("SOP 项目执行管理", "MainlandSOPManager.exe", "09-SOP项目执行管理-用户说明书.md"),
    "inventory": ("小店库存盘点助手", "MainlandInventoryAssistant.exe", "10-小店库存盘点助手-用户说明书.md"),
    "food-batch": ("食品批次与保质期追踪助手", "MainlandFoodBatchExpiryAssistant.exe", "19-食品批次与保质期追踪助手-用户说明书.md"),
    "food-safety-inspection": ("门店食品安全巡检与整改闭环助手", "MainlandFoodSafetyInspectionAssistant.exe", "21-门店食品安全巡检与整改闭环助手-用户说明书.md"),
    "purchase-compare": ("供应商采购比价助手", "MainlandPurchaseCompare.exe", "11-供应商采购比价助手-用户说明书.md"),
    "quotation": ("报价单生成器", "MainlandQuotationGenerator.exe", "12-报价单生成器-用户说明书.md"),
    "expense-reimbursement": ("费用报销管理助手", "MainlandExpenseReimbursement.exe", "13-费用报销管理助手-用户说明书.md"),
    "repair-work-order": ("售后维修工单管理助手", "MainlandRepairWorkOrderManager.exe", "14-售后维修工单管理助手-用户说明书.md"),
    "after-sales-evidence": ("售后纠纷证据链管理助手", "MainlandAfterSalesEvidenceAssistant.exe", "20-售后纠纷证据链管理助手-用户说明书.md"),
    "store-schedule": ("门店排班考勤助手", "MainlandStoreScheduleAssistant.exe", "15-门店排班考勤助手-用户说明书.md"),
    "contract-ledger": ("合同台账与到期提醒助手", "MainlandContractLedgerAssistant.exe", "16-合同台账与到期提醒助手-用户说明书.md"),
    "construction-settlement": ("装修工程签证与进度款管理助手", "MainlandConstructionSettlementAssistant.exe", "17-装修工程签证与进度款管理助手-用户说明书.md"),
    "rental-ledger": ("物业租金与押金管理助手", "MainlandRentalLedgerAssistant.exe", "18-物业租金与押金管理助手-用户说明书.md"),
    "renovation-materials": ("装修材料用量与预算核算助手", "MainlandRenovationMaterialsAssistant.exe", "26-装修材料用量与预算核算助手-用户说明书.md"),
    "equipment-maintenance": ("设备维保巡检与保养计划助手", "MainlandEquipmentMaintenanceAssistant.exe", "22-设备维保巡检与保养计划助手-用户说明书.md"),
    "vehicle-ledger": ("车辆维保与费用台账助手", "MainlandVehicleMaintenanceLedger.exe", "23-车辆维保与费用台账助手-用户说明书.md"),
    "store-cash-close": ("门店日结与收银差异核对助手", "MainlandStoreCashClose.exe", "24-门店日结与收银差异核对助手-用户说明书.md"),
    "store-membership": ("门店会员储值与积分台账助手", "MainlandStoreMembershipLedger.exe", "32-门店会员储值与积分台账助手-用户说明书.md"),
    "store-coupons": ("门店优惠券与活动核销助手", "MainlandStoreCouponRedemption.exe", "33-门店优惠券与活动核销助手-用户说明书.md"),
    "store-replenishment": ("门店采购补货与安全库存计划助手", "MainlandStoreReplenishmentPlanner.exe", "34-门店采购补货计划助手-用户说明书.md"),
    "store-receiving": ("门店收货验收与差异处理助手", "MainlandStoreReceivingDiscrepancy.exe", "35-门店收货验收与差异处理助手-用户说明书.md"),
    "business-compliance": ("经营证照与年报提醒助手", "MainlandBusinessComplianceReminder.exe", "36-经营证照与年报提醒助手-用户说明书.md"),
    "supplier-ap": ("供应商对账与应付账龄管理助手", "MainlandSupplierAPAging.exe", "25-供应商对账与应付账龄管理助手-用户说明书.md"),
    "xianyu-profit": ("闲鱼订单利润与售后成本核算助手", "MainlandXianyuProfitAssistant.exe", "27-闲鱼订单利润与售后成本核算助手-用户说明书.md"),
    "xianyu-used-pricing": ("闲鱼二手商品定价与议价助手", "MainlandXianyuUsedPricingAssistant.exe", "28-闲鱼二手商品定价与议价助手-用户说明书.md"),
    "xianyu-listing": ("闲鱼商品发布管理助手", "MainlandXianyuListingManager.exe", "29-闲鱼商品发布管理助手-用户说明书.md"),
    "xianyu-shipping": ("闲鱼发货与物流管理助手", "MainlandXianyuShippingAssistant.exe", "30-闲鱼发货与物流管理助手-用户说明书.md"),
    "xianyu-returns": ("闲鱼退货退款跟进助手", "MainlandXianyuReturnFollowup.exe", "31-闲鱼退货退款跟进助手-用户说明书.md"),
    "xianyu-pick-pack": ("闲鱼订单拣货与打包清单助手", "MainlandXianyuPickPackAssistant.exe", "37-闲鱼订单拣货与打包清单助手-用户说明书.md"),
    "xianyu-freight-calc": ("闲鱼运费试算与包装规格助手", "MainlandXianyuFreightCalculator.exe", "38-闲鱼运费试算与包装规格助手-用户说明书.md"),
}

SERIES = (
    {
        "code": "A",
        "slug": "office-efficiency",
        "title": "办公效率系列",
        "price": "29.9",
        "products": ("file-organizer", "image-tool", "pdf-tool", "meetings", "sop"),
        "summary": "文件归档、图片/PDF 批处理、会议行动项和 SOP 执行。",
    },
    {
        "code": "B",
        "slug": "store-operations",
        "title": "门店经营系列",
        "price": "29.9",
        "products": ("inventory", "food-batch", "food-safety-inspection", "purchase-compare", "repair-work-order", "after-sales-evidence", "store-schedule", "equipment-maintenance", "store-cash-close", "store-membership", "store-coupons", "store-replenishment", "store-receiving", "business-compliance"),
        "summary": "库存盘点、批次效期追踪、食品安全巡检整改闭环、采购比价、售后工单、纠纷证据归档、员工排班、设备维保计划、门店日结差异核对、会员储值和积分流水，以及优惠活动、券码发行、核销成本统计、基于销量的采购补货计划和到货验收差异跟踪、经营证照和年度报告等事项的本地期限管理。",
    },
    {
        "code": "C",
        "slug": "finance-trading",
        "title": "财务与交易系列",
        "price": "29.9",
        "products": ("freelancer", "finance", "quotation", "expense-reimbursement", "supplier-ap", "xianyu-profit", "xianyu-used-pricing", "xianyu-listing", "xianyu-shipping", "xianyu-returns", "xianyu-pick-pack", "xianyu-freight-calc"),
        "summary": "催款跟进、经营收支、报价、费用报销、供应商应付对账、账龄分析、闲鱼订单利润核算、二手商品定价、发布节奏、退货退款案件、订单拣货汇总、打包进度跟进及基于卖家自维护费率的运费试算。",
    },
    {
        "code": "D",
        "slug": "contract-project-property",
        "title": "合同工程物业系列",
        "price": "29.9",
        "products": ("contract-ledger", "construction-settlement", "rental-ledger", "renovation-materials"),
        "summary": "合同台账、装修工程签证进度款、租金押金管理、材料用量和预算核算。",
    },
    {
        "code": "E",
        "slug": "customer-personal",
        "title": "客户与个人事务系列",
        "price": "19.9",
        "products": ("sales", "jobs", "vehicle-ledger"),
        "summary": "客户跟进、求职申请进度及个人车辆维保费用记录。",
    },
)


def validate_catalog() -> None:
    seen = []
    for series in SERIES:
        if not series["products"]:
            raise ValueError(f"系列 {series['code']} 不能为空")
        for key in series["products"]:
            if key not in PRODUCTS:
                raise ValueError(f"系列 {series['code']} 引用了未知产品：{key}")
            seen.append(key)
    duplicates = sorted({key for key in seen if seen.count(key) > 1})
    missing = sorted(set(PRODUCTS) - set(seen))
    extra = sorted(set(seen) - set(PRODUCTS))
    if duplicates or missing or extra:
        raise ValueError(f"系列目录必须无重复并覆盖全部产品；重复={duplicates}，缺少={missing}，多余={extra}")


def render_series_note(series: dict) -> str:
    names = [PRODUCTS[key][0] for key in series["products"]]
    return (
        f"{series['code']}｜{series['title']}\n"
        f"建议售价：{series['price']} 元（待实际成交验证）\n"
        f"适用场景：{series['summary']}\n\n"
        "本系列包含：\n"
        + "".join(f"- {name}\n" for name in names)
        + "\n交付内容：每款软件 EXE、对应中文用户说明书、本系列说明。\n"
        "运行环境：Windows 10/11；本地运行，不依赖 VPN、ChatGPT 或外部 AI。\n"
        "数据默认保存在当前 Windows 用户的 %LOCALAPPDATA%\\MainlandBusinessTools。\n"
        "首次启动会显示设备码；每款产品需单独放入卖家提供的专属授权文件："
        "%LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\产品名.json。\n"
        "首次使用请先用测试数据验证保存、导入导出和备份恢复，再录入正式数据。\n"
    )


def render_catalog() -> str:
    validate_catalog()
    lines = [
        "# 大陆版 Windows 软件分类套餐目录",
        "",
        "五个分类系列 A–E 各自独立打包，38 款业务软件不重复、无遗漏。",
        "全系列 F 为主客户包：38 款业务软件 + 工具箱启动器；建议售价 39.9 元，本脚本不重复生成 F 包。",
        "价格均为待市场验证的建议价，不代表已发生的闲鱼成交。",
        "",
        "| 编号 | 系列 | 软件数量 | 建议售价 | 商品内容 |",
        "|---|---|---:|---:|---|",
    ]
    for series in SERIES:
        names = "、".join(PRODUCTS[key][0] for key in series["products"])
        lines.append(
            f"| {series['code']} | {series['title']} | {len(series['products'])} | "
            f"{series['price']} 元 | {names} |"
        )
    lines += [
        "",
        "## 独立商品结构",
        "",
        "- 单品：每个单品 ZIP 独立交付 EXE、README 和对应中文说明书。",
        "- A–E：按业务场景购买，避免用户为无关软件付费。",
        "- F：完整综合套餐，包含全部 38 款业务软件和工具箱启动器。",
        "",
        "所有软件均为本地 Windows 程序；首次运行的设备授权须在最终 Windows 验收后开放销售。",
        "",
    ]
    return "\n".join(lines)


def build_series_packages(release_dir: Path, manuals_dir: Path, output_dir: Path) -> list[Path]:
    validate_catalog()
    release_dir = Path(release_dir)
    manuals_dir = Path(manuals_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    required = {}
    for series in SERIES:
        for key in series["products"]:
            _, exe_name, manual_name = PRODUCTS[key]
            required[release_dir / exe_name] = f"EXE：{exe_name}"
            required[manuals_dir / manual_name] = f"说明书：{manual_name}"
    missing = [label for path, label in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("分类套餐缺少必要文件：" + "；".join(missing))

    outputs = []
    for series in SERIES:
        target = output_dir / f"{series['code']}-{series['title']}-{len(series['products'])}款.zip"
        fd, temp_name = tempfile.mkstemp(prefix=target.stem + ".", suffix=".tmp", dir=output_dir)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr("系列说明.txt", render_series_note(series))
                for key in series["products"]:
                    _, exe_name, manual_name = PRODUCTS[key]
                    archive.write(release_dir / exe_name, arcname=exe_name)
                    archive.write(manuals_dir / manual_name, arcname=f"说明书/{manual_name}")
            with zipfile.ZipFile(temp_path, "r") as archive:
                bad = archive.testzip()
                if bad is not None:
                    raise zipfile.BadZipFile(f"分类套餐 CRC 校验失败：{bad}")
                expected = 1 + 2 * len(series["products"])
                if len(archive.namelist()) != expected:
                    raise ValueError(f"{target.name} 文件数异常：{len(archive.namelist())} != {expected}")
            os.replace(temp_path, target)
            outputs.append(target)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    (output_dir / "系列套餐目录.md").write_text(render_catalog(), encoding="utf-8")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="构建大陆版 Windows 分类系列套餐")
    parser.add_argument("--release-dir", type=Path, required=True, help="包含已构建 EXE 的目录")
    parser.add_argument("--manuals-dir", type=Path, default=Path("docs/manuals"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    outputs = build_series_packages(args.release_dir, args.manuals_dir, args.output_dir)
    for path in outputs:
        print(f"SERIES_PACKAGE_OK {path} {path.stat().st_size} bytes")
    print(f"SERIES_CATALOG_OK {args.output_dir / '系列套餐目录.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
