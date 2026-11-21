import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tools" / "write_mainland_readme.py"
spec = importlib.util.spec_from_file_location("mainland_readme", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_mainland_readme_contains_real_chinese_and_local_paths():
    text = module.render_mainland_readme("MainlandSalesFollowupTool")
    assert "Windows 单机版｜大陆版" in text
    assert "%LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\产品名.json" in text
    assert "本工具无需 ChatGPT、VPN 或外部 AI 服务。" in text
    assert "å" not in text


APP_ENTRYPOINTS = [
    "文件整理助手Pro.py",
    "图片批量处理助手Pro.py",
    "PDF批量工具Pro.py",
    "自由职业催款管理工具.py",
    "轻量销售客户跟进工具.py",
    "求职申请管理Pro.py",
    "小微企业经营收支管理.py",
    "会议行动项管理.py",
    "SOP项目执行管理.py",
    "实用效率工具箱.py",
    "小店库存盘点助手.py",
    "食品批次与保质期追踪助手.py",
    "门店食品安全巡检与整改闭环助手.py",
    "供应商采购比价助手.py",
    "报价单生成器.py",
    "费用报销管理助手.py",
    "售后维修工单管理助手.py",
    "售后纠纷证据链管理助手.py",
    "门店排班考勤助手.py",
    "合同台账与到期提醒助手.py",
    "装修工程签证与进度款管理助手.py",
    "物业租金与押金管理助手.py",
    "设备维保巡检与保养计划助手.py",
    "车辆维保与费用台账助手.py",
    "门店日结与收银差异核对助手.py",
    "门店会员储值与积分台账助手.py",
    "门店优惠券与活动核销助手.py",
    "门店采购补货计划助手.py",
    "供应商对账与应付账龄管理助手.py",
    "闲鱼订单利润与售后成本核算助手.py",
    "闲鱼二手商品定价与议价助手.py",
    "闲鱼商品发布管理助手.py",
    "闲鱼发货与物流管理助手.py",
    "闲鱼退货退款跟进助手.py",
    "装修材料用量与预算核算助手.py",
]


def test_all_frozen_apps_support_noninteractive_exe_smoke_mode():
    apps_dir = Path(__file__).resolve().parents[1] / "apps"
    for filename in APP_ENTRYPOINTS:
        source = (apps_dir / filename).read_text(encoding="utf-8")
        entrypoint = source.rsplit('if __name__', 1)[-1]
        assert 'MAINLAND_EXE_SELF_TEST' in entrypoint, filename
        assert 'os._exit(0)' in entrypoint, filename


def test_frozen_exe_build_includes_license_module_and_checks_real_exit_code():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "--paths ." in workflow
    assert "--hidden-import src.license" in workflow
    assert 'EnvironmentVariables["MAINLAND_EXE_SELF_TEST"] = "1"' in workflow
    assert "WaitForExit(30000)" in workflow
    assert "$p.ExitCode -ne 0" in workflow
    assert "FROZEN_EXE_SELF_TEST_OK" in workflow


def test_package_chunking_uses_tested_bounded_splitter_and_uploads_only_actual_parts():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    chunker = (root / "tools" / "split_mainland_package.py").read_text(encoding="utf-8")
    assert "tools/split_mainland_package.py" in workflow
    max_chunks = next(
        line.split("=", 1)[1].strip()
        for line in chunker.splitlines()
        if line.startswith("MAX_CHUNKS = ")
    )
    assert max_chunks.isdigit()
    assert f"--max-chunks {max_chunks}" in workflow
    assert "CHUNK_SIZE_BYTES = 20 * 1024 * 1024" in chunker
    assert f"MAX_CHUNKS = {max_chunks}" in chunker
    assert "chunk_count(size_bytes" in chunker
    assert "sha256=" in chunker
    assert "name: mainland-phase1-package-parts" in workflow
    assert "path: release/Phase1-Mainland-Windows-Tools.zip.part-*" in workflow
    assert "for part in 00 01 02" not in workflow
    assert "mainland-phase1-package-part-14" not in workflow


def test_quotation_product_is_in_build_matrix_and_reportlab_is_declared():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    assert "报价单生成器" in workflow
    assert "MainlandQuotationGenerator" in workflow
    assert "reportlab" in requirements


def test_expense_reimbursement_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'key: expense-reimbursement' in workflow
    assert 'product: "费用报销管理助手"' in workflow
    assert "tests/test_mainland_expense_reimbursement.py" in workflow
    assert "MainlandExpenseReimbursement" in workflow
    assert "35 款 Windows EXE（34 款业务工具及工具箱启动器）" in workflow
    assert "费用报销管理助手.json" in workflow


def test_mainland_windows_workflow_runs_push_builds_only_on_main():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'push:\n    branches: [main]' in workflow
    assert "pull_request:" in workflow


def test_internal_release_status_updates_do_not_trigger_windows_rebuilds():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    triggers = workflow.split("jobs:", 1)[0]
    assert '"docs/RELEASE_STATUS.md"' not in triggers


def test_repair_work_order_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'key: repair-work-order' in workflow
    assert 'product: "售后维修工单管理助手"' in workflow
    assert "tests/test_mainland_repair_work_orders.py" in workflow
    assert "MainlandRepairWorkOrderManager" in workflow
    assert "35 款 Windows EXE（34 款业务工具及工具箱启动器）" in workflow
    assert "售后维修工单管理助手.json" in workflow
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    assert "MainlandRepairWorkOrderManager.exe" in launcher
    assert "assert len(TOOLS) == 34" in launcher


def test_mainland_windows_build_concurrency_is_scoped_per_ref():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "group: mainland-windows-exe-${{ github.ref }}" in workflow


def test_store_schedule_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'key: store-schedule' in workflow
    assert 'product: "门店排班考勤助手"' in workflow
    assert "tests/test_mainland_store_schedule.py" in workflow
    assert "MainlandStoreScheduleAssistant" in workflow
    assert "35 款 Windows EXE（34 款业务工具及工具箱启动器）" in workflow
    assert "门店排班考勤助手.json" in workflow
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    assert "MainlandStoreScheduleAssistant.exe" in launcher
    assert "assert len(TOOLS) == 34" in launcher


def test_contract_ledger_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    assert "key: contract-ledger" in workflow
    assert 'product: "合同台账与到期提醒助手"' in workflow
    assert "tests/test_mainland_contract_ledger.py" in workflow
    assert "MainlandContractLedgerAssistant" in workflow
    assert "合同台账与到期提醒助手.json" in workflow
    assert "MainlandContractLedgerAssistant.exe" in launcher
    assert len(APP_ENTRYPOINTS) == 35



def test_construction_settlement_product_is_in_build_matrix_launcher_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    assert "key: construction-settlement" in workflow
    assert 'product: "装修工程签证与进度款管理助手"' in workflow
    assert "tests/test_mainland_construction_project.py" in workflow
    assert "MainlandConstructionSettlementAssistant" in workflow
    assert "装修工程签证与进度款管理助手.json" in workflow
    assert "MainlandConstructionSettlementAssistant.exe" in launcher
    assert "assert len(TOOLS) == 34" in launcher
    assert "35 款 Windows EXE（34 款业务工具及工具箱启动器）" in workflow
    assert "34 款业务工具 + 工具箱启动器" in workflow
    assert len(APP_ENTRYPOINTS) == 35


def test_rental_ledger_product_is_in_build_matrix_launcher_license_and_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    assert "key: rental-ledger" in workflow
    assert 'product: "物业租金与押金管理助手"' in workflow
    assert "tests/test_mainland_rental_ledger.py" in workflow
    assert "MainlandRentalLedgerAssistant" in workflow
    assert "物业租金与押金管理助手.json" in workflow
    package_description = workflow.split("系列 D", 1)[1]
    assert "物业租金与押金管理助手" in package_description
    assert "MainlandRentalLedgerAssistant.exe" in launcher
    assert "物业租金与押金管理助手" in license_tests
    assert "35 款 Windows EXE（34 款业务工具及工具箱启动器）" in workflow
    assert "全部 34 款业务工具 + 工具箱启动器" in workflow
    assert len(APP_ENTRYPOINTS) == 35


def test_every_standalone_delivery_zip_has_its_matching_chinese_manual():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    manual_names = [
        line.strip().split("manual: ", 1)[1]
        for line in workflow.splitlines()
        if line.strip().startswith("manual: ")
    ]
    assert len(manual_names) == 35
    assert len(set(manual_names)) == 35
    for name in manual_names:
        assert (root / "docs" / "manuals" / name).is_file(), name
    assert "z.write('docs/manuals/${{ matrix.manual }}','说明书/${{ matrix.manual }}')" in workflow


def test_food_batch_readme_discloses_offline_fefo_and_traceability():
    text = module.render_mainland_readme("食品批次与保质期追踪助手")
    assert "FEFO" in text
    assert "过期库存自动排除" in text
    assert "批次流水" in text


def test_xianyu_pricing_readme_discloses_versioned_manual_comparables_and_floor():
    text = module.render_mainland_readme("闲鱼二手商品定价与议价助手")
    assert "XY-USED-PRICE-2026.11" in text
    assert "同类成交中位价" in text
    assert "不连接或抓取闲鱼" in text


def test_contract_readme_discloses_versioned_offline_review_scope():
    text = module.render_mainland_readme("合同台账与到期提醒助手")
    assert "CN-CONTRACT-2026.11.1" in text
    assert "PDF/DOCX/TXT/MD" in text
    assert "原文行号" in text
    assert "不会自动写入正式台账" in text
    assert "不构成法律意见" in text


def test_food_batch_product_is_in_build_matrix_launcher_license_and_store_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert 'key: food-batch' in workflow
    assert 'product: "食品批次与保质期追踪助手"' in workflow
    assert "tests/test_mainland_food_batch.py" in workflow
    assert "MainlandFoodBatchExpiryAssistant" in workflow
    assert "19-食品批次与保质期追踪助手-用户说明书.md" in workflow
    assert "MainlandFoodBatchExpiryAssistant.exe" in launcher
    assert "食品批次与保质期追踪助手" in license_tests
    assert '"food-batch"' in series_builder


def test_after_sales_evidence_readme_discloses_hash_chain_limits():
    text = module.render_mainland_readme("售后纠纷证据链管理助手")
    assert "SHA256" in text
    assert "案件字段快照 SHA256" in text
    assert "哈希链仅用于发现本地记录变化" in text
    assert "不自动连接或抓取交易平台" in text


def test_after_sales_evidence_product_is_in_build_matrix_launcher_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: after-sales-evidence" in workflow
    assert "tests/test_mainland_after_sales_evidence.py" in workflow
    assert "MainlandAfterSalesEvidenceAssistant" in workflow
    assert "20-售后纠纷证据链管理助手-用户说明书.md" in workflow
    assert "MainlandAfterSalesEvidenceAssistant.exe" in launcher
    assert "售后纠纷证据链管理助手" in license_tests
    assert '"after-sales-evidence"' in series_builder


def test_food_safety_inspection_readme_discloses_versioned_rules_and_audit_chain():
    text = module.render_mainland_readme("门店食品安全巡检与整改闭环助手")
    assert "版本化 17 项门店检查清单" in text
    assert "SHA256 哈希链审计" in text
    assert "不构成监管合规结论" in text


def test_food_safety_inspection_product_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: food-safety-inspection" in workflow
    assert "tests/test_mainland_food_safety_inspection.py" in workflow
    assert "MainlandFoodSafetyInspectionAssistant" in workflow
    assert "21-门店食品安全巡检与整改闭环助手-用户说明书.md" in workflow
    assert "MainlandFoodSafetyInspectionAssistant.exe" in launcher
    assert "门店食品安全巡检与整改闭环助手" in license_tests
    assert '"food-safety-inspection"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_customer_zip_inspection_runs_before_artifact_upload_and_is_retained():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    inspection_step = workflow.index("Inspect customer ZIP contents, CRC and SHA256")
    customer_upload = workflow.index("name: mainland-phase1-customer-package")
    assert inspection_step < customer_upload
    assert "tools/inspect_mainland_package.py" in workflow
    assert "--expected-exes 35" in workflow
    assert "--expected-manuals 35" in workflow
    report = "release/Phase1-Mainland-Windows-Tools.inspection.json"
    assert workflow.count(report) >= 2
    assert "tests/test_mainland_package_inspection.py" in workflow


def test_uploaded_customer_package_is_downloaded_and_reinspected_before_manifest():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    upload = workflow.index("name: mainland-phase1-customer-package")
    redownload = workflow.index("Re-download uploaded customer package artifact")
    reinspection = workflow.index("POST_UPLOAD_PACKAGE_REDOWNLOAD_OK")
    manifest = workflow.index("Create bounded download chunks and checksum manifest")
    assert upload < redownload < reinspection < manifest
    assert "actions/download-artifact@v4" in workflow[redownload:reinspection]
    assert "release/downloaded-artifact/Phase1-Mainland-Windows-Tools.zip" in workflow
    assert "original[field] != downloaded[field]" in workflow



def test_equipment_maintenance_product_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: equipment-maintenance" in workflow
    assert "tests/test_mainland_equipment_maintenance.py" in workflow
    assert "MainlandEquipmentMaintenanceAssistant" in workflow
    assert "22-设备维保巡检与保养计划助手-用户说明书.md" in workflow
    assert "设备维保巡检与保养计划助手.json" in workflow
    assert "MainlandEquipmentMaintenanceAssistant.exe" in launcher
    assert "设备维保巡检与保养计划助手" in license_tests
    assert '"equipment-maintenance"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35



def test_equipment_maintenance_readme_discloses_internal_reminder_limits():
    text = module.render_mainland_readme("设备维保巡检与保养计划助手")
    assert "可调整的周期提醒默认值" in text
    assert "不是法定检验要求或厂家标准" in text
    assert "待验收" in text
    assert "不作安全鉴定" in text


def test_vehicle_ledger_product_is_in_build_matrix_launcher_license_and_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    assert "key: vehicle-ledger" in workflow
    assert "tests/test_mainland_vehicle_ledger.py" in workflow
    assert "MainlandVehicleMaintenanceLedger" in workflow
    assert "23-车辆维保与费用台账助手-用户说明书.md" in workflow
    assert "MainlandVehicleMaintenanceLedger.exe" in launcher
    assert "车辆维保与费用台账助手" in license_tests
    assert "--expected-exes 35" in workflow
    assert "--expected-manuals 35" in workflow


def test_store_cash_close_product_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: store-cash-close" in workflow
    assert "tests/test_mainland_store_cash_close.py" in workflow
    assert "MainlandStoreCashClose" in workflow
    assert "24-门店日结与收银差异核对助手-用户说明书.md" in workflow
    assert "MainlandStoreCashClose.exe" in launcher
    assert "门店日结与收银差异核对助手" in license_tests
    assert '"store-cash-close"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_supplier_ap_product_is_in_build_matrix_launcher_license_and_finance_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: supplier-ap" in workflow
    assert "tests/test_mainland_supplier_ap.py" in workflow
    assert "MainlandSupplierAPAging" in workflow
    assert "25-供应商对账与应付账龄管理助手-用户说明书.md" in workflow
    assert "供应商对账与应付账龄管理助手.json" in workflow
    assert "MainlandSupplierAPAging.exe" in launcher
    assert "供应商对账与应付账龄管理助手" in license_tests
    assert '"supplier-ap"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_supplier_ap_readme_discloses_aging_and_reconciliation_limits():
    text = module.render_mainland_readme("供应商对账与应付账龄管理助手")
    assert "分笔付款" in text
    assert "逾期 1–30/31–60/61–90/90 天以上账龄" in text
    assert "不连接银行或供应商系统" in text



def test_renovation_material_takeoff_readme_discloses_measurement_and_budget_limits():
    text = module.render_mainland_readme("装修材料用量与预算核算助手")
    assert "向上取整到整包装" in text
    assert "瓷砖片数/整箱数" in text
    assert "乳胶漆升数" in text
    assert "不代替专业施工人员复核" in text


def test_renovation_material_takeoff_product_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: renovation-materials" in workflow
    assert "tests/test_mainland_renovation_materials.py" in workflow
    assert "MainlandRenovationMaterialsAssistant" in workflow
    assert "26-装修材料用量与预算核算助手-用户说明书.md" in workflow
    assert "MainlandRenovationMaterialsAssistant.exe" in launcher
    assert "装修材料用量与预算核算助手" in license_tests
    assert '"renovation-materials"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_xianyu_profit_product_is_in_build_matrix_launcher_license_and_finance_series():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (Path(__file__).resolve().parents[1] / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (Path(__file__).resolve().parent / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (Path(__file__).resolve().parents[1] / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: xianyu-profit" in workflow
    assert "tests/test_mainland_xianyu_profit.py" in workflow
    assert "MainlandXianyuProfitAssistant" in workflow
    assert "27-闲鱼订单利润与售后成本核算助手-用户说明书.md" in workflow
    assert "MainlandXianyuProfitAssistant.exe" in launcher
    assert "闲鱼订单利润与售后成本核算助手" in license_tests
    assert '"xianyu-profit"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_manual_index_lists_all_individual_manuals_before_delivery_rules():
    root = Path(__file__).resolve().parents[1]
    manuals_dir = root / "docs" / "manuals"
    index = (manuals_dir / "README.md").read_text(encoding="utf-8")
    table, marker, delivery_rules = index.partition("## 交付规则")
    assert marker, "manual index must contain a delivery rules section"
    listed = [
        line.split("|")[1].strip()
        for line in table.splitlines()
        if line.startswith("| ") and "-用户说明书.md" in line
    ]
    actual = sorted(path.name for path in manuals_dir.glob("*-用户说明书.md"))
    assert sorted(listed) == actual
    assert len(listed) == len(set(listed))
    assert all("-用户说明书.md" not in line for line in delivery_rules.splitlines())


def test_xianyu_listing_product_is_in_build_matrix_launcher_license_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: xianyu-listing" in workflow
    assert "tests/test_mainland_xianyu_listing.py" in workflow
    assert "MainlandXianyuListingManager" in workflow
    assert "29-闲鱼商品发布管理助手-用户说明书.md" in workflow
    assert "MainlandXianyuListingManager.exe" in launcher
    assert "闲鱼商品发布管理助手" in license_tests
    assert '"xianyu-listing"' in series_builder
    assert "--expected-exes 35" in workflow
    assert "--expected-manuals 35" in workflow


def test_xianyu_listing_readme_discloses_offline_refresh_and_private_floor():
    text = module.render_mainland_readme("闲鱼商品发布管理助手")
    assert "XY-LISTING-2026.11" in text
    assert "不连接或抓取闲鱼" in text
    assert "最低接受价" in text


def test_xianyu_shipping_product_is_in_build_matrix_launcher_license_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: xianyu-shipping" in workflow
    assert "tests/test_mainland_xianyu_shipping.py" in workflow
    assert "MainlandXianyuShippingAssistant" in workflow
    assert "30-闲鱼发货与物流管理助手-用户说明书.md" in workflow
    assert "MainlandXianyuShippingAssistant.exe" in launcher
    assert "闲鱼发货与物流管理助手" in license_tests
    assert '"xianyu-shipping"' in series_builder
    assert "--expected-exes 35" in workflow
    assert "--expected-manuals 35" in workflow


def test_xianyu_shipping_readme_discloses_manual_tracking_and_no_network():
    text = module.render_mainland_readme("闲鱼发货与物流管理助手")
    assert "XY-SHIPPING-2026.11" in text
    assert "不连接闲鱼或快递公司" in text
    assert "不自动通知买家" in text



def test_xianyu_return_followup_readme_discloses_offline_scope_and_manual_deadlines():
    text = module.render_mainland_readme("闲鱼退货退款跟进助手")
    assert "XY-RETURN-2026.11" in text
    assert "不连接或抓取闲鱼" in text
    assert "处理截止日期由卖家依据实际页面手工填写" in text


def test_xianyu_return_followup_product_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: xianyu-returns" in workflow
    assert 'product: "闲鱼退货退款跟进助手"' in workflow
    assert "tests/test_mainland_xianyu_returns.py" in workflow
    assert "MainlandXianyuReturnFollowup" in workflow
    assert "31-闲鱼退货退款跟进助手-用户说明书.md" in workflow
    assert "MainlandXianyuReturnFollowup.exe" in launcher
    assert "闲鱼退货退款跟进助手" in license_tests
    assert '"xianyu-returns"' in series_builder


def test_store_membership_product_is_in_build_matrix_launcher_license_and_store_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: store-membership" in workflow
    assert "tests/test_mainland_store_membership.py" in workflow
    assert "MainlandStoreMembershipLedger" in workflow
    assert "32-门店会员储值与积分台账助手-用户说明书.md" in workflow
    assert "门店会员储值与积分台账助手.json" in workflow
    assert "MainlandStoreMembershipLedger.exe" in launcher
    assert "门店会员储值与积分台账助手" in license_tests
    assert '"store-membership"' in series_builder
    assert len(APP_ENTRYPOINTS) == 35


def test_store_coupon_product_is_in_build_matrix_launcher_license_and_store_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: store-coupons" in workflow
    assert 'product: "门店优惠券与活动核销助手"' in workflow
    assert "tests/test_mainland_store_coupon.py" in workflow
    assert "MainlandStoreCouponRedemption" in workflow
    assert "33-门店优惠券与活动核销助手-用户说明书.md" in workflow
    assert "MainlandStoreCouponRedemption.exe" in launcher
    assert "门店优惠券与活动核销助手" in license_tests
    assert '"store-coupons"' in series_builder


def test_store_replenishment_planner_is_in_build_matrix_launcher_license_and_series():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    license_tests = (root / "tests" / "test_mainland_license.py").read_text(encoding="utf-8")
    series_builder = (root / "tools" / "build_mainland_series_packages.py").read_text(encoding="utf-8")
    assert "key: store-replenishment" in workflow
    assert "tests/test_mainland_store_replenishment.py" in workflow
    assert "34-门店采购补货计划助手-用户说明书.md" in workflow
    assert "MainlandStoreReplenishmentPlanner.exe" in launcher
    assert "门店采购补货与安全库存计划助手" in license_tests
    assert '"store-replenishment"' in series_builder
