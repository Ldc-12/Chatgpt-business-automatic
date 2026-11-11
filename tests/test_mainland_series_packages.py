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


def test_series_catalog_covers_all_18_products_once():
    MODULE.validate_catalog()
    assigned = [key for series in MODULE.SERIES for key in series["products"]]
    assert len(MODULE.PRODUCTS) == 19
    assert len(assigned) == 19
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
    assert "19 款业务软件 + 工具箱启动器" in catalog



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
