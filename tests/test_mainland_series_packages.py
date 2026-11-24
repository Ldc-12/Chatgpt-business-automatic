from pathlib import Path
import importlib.util
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_mainland_series_packages.py"
SPEC = importlib.util.spec_from_file_location("mainland_series_packages", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _make_inputs(tmp_path):
    release = tmp_path / "release"
    manuals = tmp_path / "manuals"
    output = tmp_path / "series"
    release.mkdir()
    manuals.mkdir()
    for _, exe_name, manual_name in MODULE.PRODUCTS.values():
        (release / exe_name).write_bytes(b"test-exe:" + exe_name.encode("utf-8"))
        (manuals / manual_name).write_text(f"# {manual_name}\n中文说明书", encoding="utf-8")
    return release, manuals, output


def test_series_catalog_covers_all_36_products_once():
    MODULE.validate_catalog()
    assigned = [key for series in MODULE.SERIES for key in series["products"]]
    assert len(MODULE.PRODUCTS) == 36
    assert len(assigned) == 36
    assert set(assigned) == set(MODULE.PRODUCTS)
    assert len(assigned) == len(set(assigned))


def test_builder_creates_five_independent_zips_with_matching_manuals(tmp_path):
    release, manuals, output = _make_inputs(tmp_path)
    packages = MODULE.build_series_packages(release, manuals, output)
    assert len(packages) == 5
    assert (output / "系列套餐目录.md").is_file()

    for series, package in zip(MODULE.SERIES, packages):
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == 1 + 2 * len(series["products"])
            assert "系列说明.txt" in names
            expected_exes = {MODULE.PRODUCTS[key][1] for key in series["products"]}
            expected_manuals = {
                f"说明书/{MODULE.PRODUCTS[key][2]}" for key in series["products"]
            }
            assert expected_exes.issubset(set(names))
            assert expected_manuals.issubset(set(names))
            note = archive.read("系列说明.txt").decode("utf-8")
            assert series["title"] in note
            assert "不依赖 VPN、ChatGPT 或外部 AI" in note


def test_missing_manual_fails_before_any_series_zip_is_written(tmp_path):
    release, manuals, output = _make_inputs(tmp_path)
    missing = MODULE.PRODUCTS["contract-ledger"][2]
    (manuals / missing).unlink()
    try:
        MODULE.build_series_packages(release, manuals, output)
    except FileNotFoundError as exc:
        assert missing in str(exc)
    else:
        raise AssertionError("missing manual should be rejected")
    assert not list(output.glob("*.zip"))


def test_catalog_names_all_five_series_and_full_package():
    catalog = MODULE.render_catalog()
    for series in MODULE.SERIES:
        assert series["title"] in catalog
    assert "全系列 F" in catalog
    assert "36 款业务软件 + 工具箱启动器" in catalog



def test_windows_workflow_builds_and_publishes_the_series_packages():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "tests/test_mainland_series_packages.py" in workflow
    assert "tools/build_mainland_series_packages.py" in workflow
    assert "mainland-phase1-series-packages" in workflow
    assert "docs/MAINLAND_SERIES_PACKAGES.md" in workflow


def test_store_series_contains_food_batch_expiry_assistant():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "food-batch" in store_series["products"]
    assert MODULE.PRODUCTS["food-batch"][1] == "MainlandFoodBatchExpiryAssistant.exe"


def test_store_series_contains_after_sales_evidence_chain_assistant():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "after-sales-evidence" in store_series["products"]
    assert MODULE.PRODUCTS["after-sales-evidence"][1] == "MainlandAfterSalesEvidenceAssistant.exe"
    assert MODULE.PRODUCTS["after-sales-evidence"][2] == "20-售后纠纷证据链管理助手-用户说明书.md"


def test_store_series_contains_food_safety_inspection_closure_assistant():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "food-safety-inspection" in store_series["products"]
    assert MODULE.PRODUCTS["food-safety-inspection"][1] == "MainlandFoodSafetyInspectionAssistant.exe"
    assert MODULE.PRODUCTS["food-safety-inspection"][2] == "21-门店食品安全巡检与整改闭环助手-用户说明书.md"



def test_store_series_contains_equipment_maintenance_planner():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "equipment-maintenance" in store_series["products"]
    assert MODULE.PRODUCTS["equipment-maintenance"][1] == "MainlandEquipmentMaintenanceAssistant.exe"
    assert MODULE.PRODUCTS["equipment-maintenance"][2] == "22-设备维保巡检与保养计划助手-用户说明书.md"


def test_personal_series_contains_vehicle_maintenance_ledger():
    personal = next(item for item in MODULE.SERIES if item["code"] == "E")
    assert "vehicle-ledger" in personal["products"]
    assert MODULE.PRODUCTS["vehicle-ledger"][1] == "MainlandVehicleMaintenanceLedger.exe"
    assert MODULE.PRODUCTS["vehicle-ledger"][2] == "23-车辆维保与费用台账助手-用户说明书.md"


def test_store_series_contains_cash_close_reconciliation():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "store-cash-close" in store_series["products"]
    assert MODULE.PRODUCTS["store-cash-close"][1] == "MainlandStoreCashClose.exe"
    assert MODULE.PRODUCTS["store-cash-close"][2] == "24-门店日结与收银差异核对助手-用户说明书.md"


def test_finance_series_contains_supplier_ap_aging_assistant():
    finance = next(item for item in MODULE.SERIES if item["code"] == "C")
    assert "supplier-ap" in finance["products"]
    assert MODULE.PRODUCTS["supplier-ap"][1] == "MainlandSupplierAPAging.exe"
    assert MODULE.PRODUCTS["supplier-ap"][2] == "25-供应商对账与应付账龄管理助手-用户说明书.md"



def test_contract_project_series_contains_renovation_material_takeoff():
    project_series = next(item for item in MODULE.SERIES if item["code"] == "D")
    assert "renovation-materials" in project_series["products"]
    assert MODULE.PRODUCTS["renovation-materials"][1] == "MainlandRenovationMaterialsAssistant.exe"
    assert MODULE.PRODUCTS["renovation-materials"][2] == "26-装修材料用量与预算核算助手-用户说明书.md"


def test_finance_series_contains_xianyu_used_goods_pricing_assistant():
    finance = next(item for item in MODULE.SERIES if item["code"] == "C")
    assert "xianyu-used-pricing" in finance["products"]
    assert MODULE.PRODUCTS["xianyu-used-pricing"][1] == "MainlandXianyuUsedPricingAssistant.exe"
    assert MODULE.PRODUCTS["xianyu-used-pricing"][2] == "28-闲鱼二手商品定价与议价助手-用户说明书.md"


def test_finance_series_contains_xianyu_order_profit_assistant():
    finance = next(item for item in MODULE.SERIES if item["code"] == "C")
    assert "xianyu-profit" in finance["products"]
    assert MODULE.PRODUCTS["xianyu-profit"][1] == "MainlandXianyuProfitAssistant.exe"
    assert MODULE.PRODUCTS["xianyu-profit"][2] == "27-闲鱼订单利润与售后成本核算助手-用户说明书.md"


def test_finance_series_contains_xianyu_listing_lifecycle_manager():
    finance = next(item for item in MODULE.SERIES if item["code"] == "C")
    assert "xianyu-listing" in finance["products"]
    assert "xianyu-shipping" in finance["products"]
    assert MODULE.PRODUCTS["xianyu-shipping"][1] == "MainlandXianyuShippingAssistant.exe"
    assert MODULE.PRODUCTS["xianyu-shipping"][2] == "30-闲鱼发货与物流管理助手-用户说明书.md"
    assert MODULE.PRODUCTS["xianyu-listing"][1] == "MainlandXianyuListingManager.exe"
    assert MODULE.PRODUCTS["xianyu-listing"][2] == "29-闲鱼商品发布管理助手-用户说明书.md"




def test_store_series_contains_business_compliance_reminder():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "business-compliance" in store_series["products"]
    assert MODULE.PRODUCTS["business-compliance"][1] == "MainlandBusinessComplianceReminder.exe"
    assert MODULE.PRODUCTS["business-compliance"][2] == "36-经营证照与年报提醒助手-用户说明书.md"
    assert len(store_series["products"]) == 14

def test_static_series_catalog_lists_each_business_product_once():
    catalog_path = Path(__file__).resolve().parents[1] / "docs" / "MAINLAND_SERIES_PACKAGES.md"
    catalog = catalog_path.read_text(encoding="utf-8")
    for name, _, _ in MODULE.PRODUCTS.values():
        assert catalog.count(f"- {name}\n") == 1, name
    assert "| C | 财务与交易系列 | 10 |" in catalog
    assert "| F | 全系列综合套餐 | 36 款业务软件 + 工具箱启动器 |" in catalog



def test_finance_series_contains_xianyu_return_refund_followup_assistant():
    finance = next(item for item in MODULE.SERIES if item["code"] == "C")
    assert "xianyu-returns" in finance["products"]
    assert MODULE.PRODUCTS["xianyu-returns"][1] == "MainlandXianyuReturnFollowup.exe"
    assert MODULE.PRODUCTS["xianyu-returns"][2] == "31-闲鱼退货退款跟进助手-用户说明书.md"



def test_store_series_contains_member_stored_value_and_points_ledger():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "store-membership" in store_series["products"]
    assert len(store_series["products"]) == 14
    assert MODULE.PRODUCTS["store-membership"][1] == "MainlandStoreMembershipLedger.exe"
    assert MODULE.PRODUCTS["store-membership"][2] == "32-门店会员储值与积分台账助手-用户说明书.md"


def test_store_series_contains_coupon_campaign_redemption_assistant():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "store-coupons" in store_series["products"]
    assert MODULE.PRODUCTS["store-coupons"][1] == "MainlandStoreCouponRedemption.exe"
    assert MODULE.PRODUCTS["store-coupons"][2] == "33-门店优惠券与活动核销助手-用户说明书.md"
    assert len(store_series["products"]) == 14


def test_store_series_contains_replenishment_planner():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "store-replenishment" in store_series["products"]
    assert MODULE.PRODUCTS["store-replenishment"][1] == "MainlandStoreReplenishmentPlanner.exe"
    assert MODULE.PRODUCTS["store-replenishment"][2] == "34-门店采购补货计划助手-用户说明书.md"
    assert len(store_series["products"]) == 14


def test_store_series_contains_receiving_discrepancy_assistant():
    store_series = next(item for item in MODULE.SERIES if item["code"] == "B")
    assert "store-receiving" in store_series["products"]
    assert MODULE.PRODUCTS["store-receiving"][1] == "MainlandStoreReceivingDiscrepancy.exe"
    assert MODULE.PRODUCTS["store-receiving"][2] == "35-门店收货验收与差异处理助手-用户说明书.md"
    assert len(store_series["products"]) == 14
