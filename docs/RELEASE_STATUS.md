# 第一批大陆版发布状态

## 最近一次可复现构建（2026-11-03 20:46，中国标准时间）

- 主分支构建提交：`58016ae270f00dc9a488d5edfc5fbd81393395f9`（PR #9 合并提交）。
- 授权防错 PR：[#9 Guard license issuance with embedded-key match and add public-key export](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/9)，已合并。
- Mainland Windows EXE Actions：[#151](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41638303845)，结论：`success`。
- 10/10 个 Windows 矩阵任务的 job 结论均为 success；但 2026-11-04 对冻结 EXE 日志复核发现旧冒烟检查存在假阳性（见下方更正），不能据此认定 EXE 可运行。
- 总套餐打包 job：成功；Autonomous Business Engine：[#346](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41638303726)，build/deploy 均成功。
- 客户套餐 artifact：`mainland-phase1-customer-package`，ID：`13231977373`，artifact 大小：129,594,654 bytes。
- 下载后外层 artifact ZIP 包含最终客户 ZIP 和大陆版 README；内层客户 ZIP：129,558,555 bytes。
- 内层客户 ZIP SHA256：`1e2f23fe687cb63ce33a18641e61eaf8b155a08f0ed2a2b30ec54c8e3821075c`；与 manifest artifact `13232056237` 中的 SHA256、字节数完全一致。
- ZIP 完整性检查：通过（`ZipFile.testzip() = None`）。内容为 10 个 EXE、10 份产品用户说明书、1 份说明书索引 README、1 份大陆版 README、1 份套餐说明 TXT；共 25 个条目（23 个文件、2 个目录）。
- 分片清单 artifact：`mainland-phase1-package-manifest`，ID：`13232056237`；7 个 20 MiB 分片 artifact 均上传成功。
- 客户 ZIP 内文件时间戳：2026-11-03 12:46:18 UTC；artifact 创建时间：12:46:25 UTC；工作流完成时间：12:46:38 UTC（中国标准时间 20:46:38）。

## 冒烟检查范围

旧版 CI 只检查 PyInstaller one-file 父进程存活 5 秒，未验证子进程启动是否成功；该检查已证明存在假阳性，不能作为 EXE 可启动证据。修复后将用 MAINLAND_EXE_SELF_TEST 环境变量启动冻结程序，等待其在 30 秒内真实退出，并要求退出码为 0。即使新检查通过，也不等于所有 GUI 页面和真实授权激活均已验收。

## 授权系统状态：代码侧已加防错，真实卖家密钥仍待确认

- `src/license.py` 内嵌公钥 SHA256 指纹：`B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`。
- `config/mainland_license_public_key.pem` SHA256 指纹：`7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。
- 两份文件均可解析为 Ed25519 公钥，但指纹不同；客户端只使用 `src/license.py` 内嵌公钥，不会自动回退到 config 文件。
- PR #9 已增加签发前公钥比对：`tools/issue_license.py` 会从卖家私钥派生公钥，与客户端内嵌公钥逐字节比较；不匹配即拒绝签发，并仅报告公钥 SHA256 指纹，不输出私钥。
- 新增 `tools/export_license_public_key.py`，可在卖家可信 Windows 电脑本地导出公钥 PEM 和 SHA256 指纹。私钥只在本地读取，不会上传或打印。
- 回归测试覆盖：9 款受保护产品的独立授权路径、签名/客户端格式兼容、错误设备码、过期授权、篡改签名，以及不匹配密钥时拒绝签发。测试使用一次性临时测试密钥，不代表真实卖家密钥已匹配。
- 卖家私钥不在仓库中。不得上传、提交或发送卖家私钥，也不得猜测、替换或新造密钥覆盖现有公钥。

**唯一待用户操作：**在可信 Windows 电脑的项目目录运行：

```powershell
py tools/export_license_public_key.py --private-key "C:\你的私钥路径\seller-private.pem"
```

只把输出的 `SHA256=` 指纹（或公钥 PEM）发回用于比对；不要发送私钥。预期客户端指纹为上面 `src/license.py` 的 `B646...`。如果不一致，签发工具会拒绝生成客户授权，必须先确认密钥归属，再制定明确的密钥轮换方案。

## 上架前剩余验收

1. 卖家本地导出公钥指纹与客户端内嵌公钥匹配。
2. 在真实 Windows 电脑验证实际签发、产品名、设备码、到期日、签名校验、激活和重启后仍有效。
3. 验证无授权、错误签名、错误产品、错误设备及过期授权均被拒绝。
4. 逐款检查首次运行、重启后数据保留、CSV 导入/导出和备份恢复；目前销售客户跟进工具的 JSON 备份/恢复说明最完整，其他业务工具仍需逐款补齐备份恢复验收和中文说明。
5. 完成真实 Windows 终端验收后，再发布闲鱼商品。

## 当前结论

此前 10 款 Windows EXE 的 CI 构建与 ZIP 结构检查曾通过，但冻结程序的实际启动检查存在假阳性。**旧版客户包不能作为已验证可运行的软件交付；须先通过修复后的冻结 EXE 自测，再重新下载验收。真实授权激活也仍待最终验收。**


## 第二阶段新增产品：小店库存盘点助手（开发中，待 CI 验收）

- 新增源码：`apps/小店库存盘点助手.py`，产品授权 ID：`小店库存盘点助手`。
- 功能：本地商品台账、商品编码唯一性检查、库存数量/预警下限、关键词搜索、CSV 追加导入/导出、JSON 备份与恢复。
- 数据保存在 `%LOCALAPPDATA%\\MainlandBusinessTools\\inventory.json`；无需 VPN、ChatGPT、云端 AI 或外部 API。
- CSV 导入遇到重复编码、缺字段或非法数字时整批拒绝，不覆盖现有数据。
- 新增回归测试：保存重载、编辑、CSV 往返、重复导入原子拒绝、错误 CSV 保留原数据、备份恢复及错误备份拒绝。
- 已加入 Mainland Windows EXE 矩阵及客户套餐，新增中文说明书，并把授权路径加入独立产品 ID 测试。
- 当前分支：`feat/inventory-counting-assistant`。此版本尚未通过 GitHub Actions Windows 构建与实际 Windows GUI 验收，不能作为可交付成品；卖家私钥匹配阻塞仍保持独立。


## 2026-11-04 CI 复核更正：冻结 EXE 曾因缺少 src.license 而启动失败

- PR #10 Windows 工作流 run #160：[#41749730335](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41749730335)，head：`91f9c41947b8055dec6e31d9c89db125cc162149`。
- 该 run 的 11 个 Windows build job 与客户套餐 job 全部显示 success；13 个 check run（含安全扫描）全部 success。
- inventory job #126311803673、jobs #126311803038、finance #126311803471、sales #126311804421 的实际日志均出现 `ModuleNotFoundError: No module named 'src'`。旧 PowerShell 检查只看 one-file 父进程 5 秒仍存活，错误地判为成功。
- 根因：PyInstaller 命令未显式将仓库根目录加入分析路径，也未显式收集 `src.license`；one-file 父进程的存活不代表子进程成功。
- 已在 PR #10 分支修复：构建增加 `--paths . --hidden-import src.license`；冻结 EXE 自测通过 `MAINLAND_EXE_SELF_TEST=1` 触发，并要求 30 秒内退出且退出码必须为 0；增加回归测试防止该假阳性再次出现。
- PR #10 run #160 的客户套餐 artifact ID：`13285216933`。已实际下载并检查：外层 artifact 140,742,092 bytes；内层 ZIP 140,702,964 bytes，SHA256 `899bcba088d002b710b73c0d32ffb0bb632dae87dc20f77ccea0e283fe73026c`；ZIP CRC 完整，27 个条目，其中 11 个 EXE、11 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。ZIP 时间戳为 2026-11-04 08:51:58（中国标准时间）。
- **该 artifact 结构完整但 EXE 启动缺陷尚未修复，因此明确不作为客户交付包。** 修复后的 PR 构建与 artifact 尚待重新验收；不得用该包或旧 run #151 包上架。

## 2026-11-04 Autonomous Business Engine 最新检查

- 最新 scheduled run #355：[#41785613998](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41785613998)，main 提交仍为 `b7d8ba8557326d0dcc7c50d42004651f93b98b32`，结论 success。
- build/deploy 两个 job 均 success；测试日志显示 `37 passed`，product_factory 生成 12 个产品页面，xianyu_factory 执行成功。
- Pages artifact ID：`13301385443`，48,842 bytes。该工作流成功不代表 Windows EXE 已通过实际启动验收。


## 2026-11-04 冻结 EXE 修复后套餐分片失败与修复

- Mainland Windows EXE run #164：[#41819541286](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41819541286)。11/11 个 Windows build job 全部 success；冻结 EXE 自测均在 30 秒内退出且退出码为 0。inventory/job/finance/sales 日志明确出现 `FROZEN_EXE_SELF_TEST_OK`，对应 pytest 分别为 19、14、14、18 项通过。
- 客户套餐 job 在最后的分片数量限制处失败：`Package exceeds the supported 7 x 20 MiB chunk size.`，不是 EXE 编译或自测失败。
- 客户包 artifact ID：`13316700617`。已下载核验：外层 ZIP 176,860,994 bytes，SHA256 `e3e1c1acd723881dc80086125e71a792ceba71e862de37663109fed4dd0355ed`；内层客户 ZIP 176,810,956 bytes，SHA256 `46b5725a3466ce183ddf0325a9354f78526119367d3ea72a7fd51129b9be64f7`。CRC 完整，27 个条目（25 个文件、2 个目录），包含 11 个 EXE、11 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明；ZIP 文件时间戳为 2026-11-04 19:15:50（中国标准时间）。
- 已把分片容量提高到 9 × 20 MiB，并新增第 07、08 分片上传步骤及回归测试。下一次 CI 必须验证完整 package job 和 9 个分片 artifact，不能把 run #164 的失败状态改写成成功。
- **run #164 的 ZIP 结构完整，但工作流整体失败；仍不是正式发布包。** 授权私钥匹配与真实 Windows 授权激活继续待最终验收。


## 2026-11-04 PR #10 修复后成功构建与客户包验收（run #167）

- Mainland Windows EXE run #167：[#41820028863](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41820028863)，提交 `ad10090eda883b88cbd85db79e454b31746cc2c7`，结论 success。
- 11/11 个 Windows build job 全部 success，客户套餐 job success；13/13 check runs success，无失败项。
- 每款产品的回归测试均通过：finance 15、file organizer 18、meetings 15、PDF 15、jobs 15、launcher 15、inventory 20、SOP 15、image 15、sales 19、freelancer 17。11/11 个冻结 EXE 的日志均有 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`，无 `ModuleNotFoundError` 或 traceback。
- 客户套餐 artifact：`mainland-phase1-customer-package`，ID `13316323052`，外层 artifact ZIP 176,855,187 bytes，SHA256 `72c10fecebbbc76f7d837de449bb54188d6a06da1b3af4de82c1a8169f8896dd`。
- 已实际下载并检查内层 `Phase1-Mainland-Windows-Tools.zip`：176,805,147 bytes，SHA256 `8f4da15af5a45b6d34ef747864f0bfc8316460ba3dacf15b1d1c34329ead0e7a`；`ZipFile.testzip() = None`。共 27 个条目（25 文件、2 目录）：11 个 EXE、11 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。套餐说明文件时间戳：2026-11-04 19:22:28（中国标准时间）。
- manifest artifact ID `13316627154`，记录的 ZIP 字节数和 SHA256 与实际下载内层 ZIP 完全一致，`parts=9`。9 个分片 artifact：00 `13316771754`、01 `13317805361`、02 `13317925288`、03 `13316442708`、04 `13316188755`、05 `13317940298`、06 `13316821742`、07 `13316677163`、08 `13317380068`。
- **结论：** 新版 11 款 Windows EXE 已通过 CI 冻结模块导入与非交互退出码自测，客户 ZIP 和 manifest 已下载核验；仍未完成卖家私钥匹配及真实 Windows 授权签发/激活/重启验收，故标记为“待最终验收”，不是已可正式销售。


## 2026-11-04 PR #10 已合并及主线复核

- PR #10（小店库存盘点助手）已 squash 合并：主线提交 `ee9164a6c4bede161834d1d51a31f3015f48e2d9`。当前没有未完成 PR。
- 合并前 PR head 的 Mainland Windows EXE run #170：[#41821090496](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821090496)，11/11 个 Windows build job 与客户套餐 job 全部 success；每款冻结 EXE 自测退出码为 0。客户包 artifact ID `13317706559`，manifest artifact ID `13317191946`。
- 合并触发的 main push run #169 被 PR synchronize 事件 run #170 的共享 concurrency group 取消；run #170 验证的是相同的已合并源码树。文档提交后将再触发 main push 构建，单独确认 main 分支。
- Autonomous Business Engine run #356：[#41821071255](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821071255)，main 合并提交上 build/deploy 均 success；完整测试 `45 passed`，product_factory 生成 12 个产品页面，xianyu_factory 执行成功；Pages artifact ID `13317615142`，48,830 bytes。


## 2026-11-04 main 分支最终复核：run #171

- main commit：`cb50ad35f2dc76e0e70de85a8e5881dee4f89688`；Mainland Windows EXE run #171：[#41821589374](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821589374)，整体 success，11/11 Windows build jobs 与客户套餐 job 全部 success。
- 11 款冻结 EXE 均通过非交互自测（退出码 0），11 份产品回归测试全部通过；各 job 测试数：jobs 15、SOP 15、PDF 15、sales 19、launcher 15、file organizer 18、meetings 15、inventory 20、finance 15、freelancer 17、image 15。
- main 客户套餐 artifact ID `13317801473`，外层 ZIP 176,862,637 bytes，SHA256 `50fd5d3a0b9a2af2bab4fd35c91947666b931937a62b99a27acb3996783fc7dd`；内层 ZIP 176,812,698 bytes，SHA256 `6e77236f61acbff1db5204c622cc5cc5ace0c26ec9685457c4fa2bbdfd73a104`。已下载，CRC 完整；27 个条目、25 个文件：11 EXE、11 产品说明书、1 说明书索引、1 大陆版 README、1 套餐说明。套餐说明时间戳：2026-11-04 19:33:00（中国标准时间）。
- manifest artifact ID `13317012167`，SHA256 与实际内层 ZIP 一致，字节数 176,812,698，分片数 9。9 个分片 artifact 全部上传成功。
- 最新 Autonomous Business Engine run #357：[#41821589355](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821589355)，build/deploy success，`45 passed`，生成 12 个产品页面；Pages artifact ID `13317861698`，48,821 bytes。
- **发布状态仍为待最终验收：** 以上证明 11 款 EXE 的构建、冻结模块导入自测和套餐内容通过 CI；未完成卖家私钥指纹匹配及真实 Windows 设备的授权签发、激活、重启验证，不能标记为可直接销售的正式授权版。


## 2026-11-04 本轮复验与第三阶段产品开发

- 本轮重新检查 main 最新提交 `6b74b803012cd40fadf05b0f984a0c02875209b0`、开放 PR（0 个），并复核 Mainland Windows EXE run #171：[#41821589374](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821589374)。
- 11/11 Windows build jobs、套餐 job 全部 success。小店库存盘点助手 job #126545796209：`20 passed`，冻结 EXE 日志出现 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`，artifact `mainland-inventory-windows` ID `13317751830`。
- Autonomous Business Engine run #357：[#41821589355](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41821589355)，build/deploy success；测试 `45 passed`，product_factory 生成 12 个产品页面，xianyu_factory 执行成功；Pages artifact ID `13317861698`。
- 本轮实际下载客户包 artifact ID `13317801473`（外层 176,862,637 bytes，SHA256 `50fd5d3a0b9a2af2bab4fd35c91947666b931937a62b99a27acb3996783fc7dd`），解出内层 ZIP 176,812,698 bytes，SHA256 `6e77236f61acbff1db5204c622cc5cc5ace0c26ec9685457c4fa2bbdfd73a104`。`ZipFile.testzip() = None`；27 个条目，11 个 EXE、11 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。套餐说明时间戳 2026-11-04 19:33:00（中国标准时间）。
- manifest artifact ID `13317012167` 已下载，记录字节数 `176812698`、SHA256 `6e77236f61acbff1db5204c622cc5cc5ace0c26ec9685457c4fa2bbdfd73a104`、分片数 9，与实际内层 ZIP 完全一致。
- 新增开发产品：`供应商采购比价助手`，源码 `apps/供应商采购比价助手.py`，测试 `tests/test_mainland_purchase_compare.py`，中文说明书 `docs/manuals/11-供应商采购比价助手-用户说明书.md`。采用 Decimal 计算含税到货单位成本，过期报价不参与推荐；支持供应商多报价、搜索、CSV 原子追加导入/导出、JSON 备份恢复和本地持久化。
- 已将新产品加入独立授权路径回归测试、冻结 EXE 自测矩阵、套餐和说明书索引；客户 ZIP 分片上限从 9 提升到 12 × 20 MiB，以覆盖新增 EXE 后的包体增长。
- 当前新产品分支：`feat/purchase-price-comparison-assistant`。只有 PR 的 Windows Actions、冻结 EXE 自测及客户套餐下载核验全部通过后，才可标记为可交付。
- 授权阻塞未改变：两份仓库公钥指纹不同，卖家私钥不在仓库（且不应上传）；真实卖家公钥匹配及真实 Windows 授权激活/重启测试仍待最终验收。


## 2026-11-04 PR #11 供应商采购比价助手：Windows 构建与客户包验收通过

- PR #11：[#Add offline supplier purchase price comparison assistant](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/11)，分支 `feat/purchase-price-comparison-assistant`。
- Mainland Windows EXE run #186：[#41824361112](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41824361112)，PR head `fc0f40a871f388b24cf3b2871dfa2a77101fff7b`，结论 `success`。12/12 Windows build jobs 与客户套餐 job 全部 success。
- 12 个产品 pytest 结果：jobs 15、freelancer 17、inventory 20、finance 15、purchase-compare 25、PDF 15、file-organizer 18、image-tool 15、meetings 15、launcher 15、SOP 15、sales 19；所有冻结 EXE 均通过 `FROZEN_EXE_SELF_TEST_OK`，退出码 0。日志未发现失败、Traceback 或 `ModuleNotFoundError`。
- 新产品 purchase-compare job ID `126555587234`，`25 passed in 0.78s`；EXE `MainlandPurchaseCompare.exe` 构建成功，冻结 EXE 自测通过；单品 artifact `mainland-purchase-compare-windows` ID `13318034217`，29,520,205 bytes。
- 客户套餐 artifact `mainland-phase1-customer-package` ID `13317478725`，外层 ZIP 191,618,390 bytes，SHA256 `3f7816d588696f29da2669543d37b62baeeb5eae6a008b9ee9f1ae7c3781ed24`。已实际下载并解出内层客户 ZIP：191,564,121 bytes，SHA256 `3f5bd56739c9957b3c39f4fdf14d32ae46ef70b70567d879b3ce363886ce7c71`；外层、内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 29 个条目（27 个文件、2 个目录）：12 个 EXE、12 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。新增文件 `MainlandPurchaseCompare.exe` 和 `11-供应商采购比价助手-用户说明书.md` 均存在。套餐说明时间戳 2026-11-04 19:54:00（中国标准时间）。
- manifest artifact `mainland-phase1-package-manifest` ID `13318790929` 已实际下载，声明 bytes `191564121`、SHA256 `3f5bd56739c9957b3c39f4fdf14d32ae46ef70b70567d879b3ce363886ce7c71`、parts `12`；与实际内层 ZIP 字节数和 SHA256 完全一致。
- 12 个分片 artifact 已上传：00 `13319215248`、01 `13317324002`、02 `13317473666`、03 `13317309033`、04 `13317684342`、05 `13317789292`、06 `13318511454`、07 `13317694413`、08 `13318815914`、09 `13317358968`、10 `13317784389`、11 `13317598466`。10、11 为补齐固定 12 段格式的空分片（仅 ZIP 封装开销），有效数据已包含在 00–09。
- **交付状态：** 供应商采购比价助手已通过 GitHub Windows 源码测试、PyInstaller 构建、冻结 EXE 非交互启动/退出码检查，以及客户套餐 ZIP/manifest 下载核验；代码与构建层面可交付。整个产品线仍标记“待最终验收”：真实卖家私钥指纹匹配、真实 Windows 授权签发/激活/重启测试尚未完成，不能称为正式授权销售版。


## 2026-11-04 PR #11 合并后 main 验收记录

- PR #11 已在 PR run #188 完成 12/12 Windows EXE 构建、12/12 产品回归测试、12/12 冻结 EXE 自测及客户套餐 job；PR run：[#41825269055](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41825269055)，结论 success。
- PR #11 已 squash 合并至 main，合并提交：`a8dc205e3f231e10b2545df80bb116e915613196`。合并后开放 PR 数为 0。
- run #188 客户包 artifact ID `13319735280` 已下载核验：外层 ZIP 191,622,642 bytes，SHA256 `84e2dea108ffb6c12bcdd257f2412fa45eea58962d2e31a53e98aa8d2190e8eb`；内层 ZIP 191,568,534 bytes，SHA256 `73c48b0a9d9a4ebecfe27ff349bcced679ce88a215c2939d619c094b262769dc`。外层和内层 CRC 均通过，内层 29 个条目（27 文件、2 目录），包含 12 个 EXE、12 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明；新增比价助手 EXE 和说明书均在包内。ZIP 时间戳 2026-11-04 20:01:16（中国标准时间）。
- run #188 manifest artifact ID `13319455772`，声明 bytes `191568534`、SHA256 `73c48b0a9d9a4ebecfe27ff349bcced679ce88a215c2939d619c094b262769dc`、parts `12`，与实际内层 ZIP 完全一致。
- run #188 的 12/12 Windows build jobs 和 package job 均 success；新产品测试 `25 passed`，冻结 EXE 自测退出码 0。
- 当前最新主线合并提交为 `a8dc205e3f231e10b2545df80bb116e915613196`。此文档更新将触发 main push 的独立构建；最终 main 客户包应以该 main push run 的 artifact 为准，而非 PR artifact。
- **授权最终验收仍未完成：** 两份仓库公钥指纹仍不同；卖家私钥不得上传。真实卖家公钥匹配和 Windows 授权激活/重启测试待用户本地公钥指纹确认。


## 2026-11-04 main 最新发布复核：Mainland Windows EXE run #190

- 本轮检查时 main 最新提交：`968b0e9377285b5e2782208147da8e66b4c03053`（提交信息：Record merged purchase comparison release and PR validation）。PR #10（小店库存盘点助手）与 PR #11（供应商采购比价助手）均已合并；当前 open PR 查询无未完成 PR。
- PR #11 合并产品提交：`a8dc205e3f231e10b2545df80bb116e915613196`；PR #10 产品提交：`ee9164a6c4bede161834d1d51a31f3015f48e2d9`。
- Mainland Windows EXE run #190：[#41826304168](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41826304168)，main commit `968b0e9377285b5e2782208147da8e66b4c03053`，结论 success。12/12 个 Windows build matrix jobs 与 Phase 1 customer delivery package job 全部 success。
- 供应商采购比价助手 job #126562100511：25 passed；PyInstaller EXE build success；冻结 EXE self-test 日志出现 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`；单品 artifact ID `13318549486`。
- 小店库存盘点助手 job #126562100330：20 passed；PyInstaller EXE build success；冻结 EXE self-test 日志出现 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`；单品 artifact ID `13319257929`。
- 总套餐打包 job #126562675814：success，创建 12 个 20 MiB 分片位及 SHA256 manifest。客户套餐 artifact ID `13319502172`（artifact 大小 191,620,629 bytes）；manifest artifact ID `13319791615`。
- 已实际下载 artifact `13319502172` 与 manifest `13319791615`。外层 artifact ZIP 完整，含内层客户 ZIP 和大陆版 README。内层 `Phase1-Mainland-Windows-Tools.zip`：191,566,548 bytes，SHA256 `1552614666657163397921944fe2168435674cedae1b1ca7507d182786a97ef7`；与 manifest 中字节数、SHA256 完全一致；`ZipFile.testzip() = None`。
- 内层客户 ZIP 共 29 个条目（27 个文件、2 个目录）：12 个 EXE、12 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。套餐说明与 README 的文件时间戳为 2026-11-04 12:07 UTC（中国标准时间 20:07）；工作流于 12:08:19 UTC（20:08:19）完成。
- 分片 artifact 00–09 为有效数据分片；part-10 与 part-11 是空分片（artifact ZIP 各 196 bytes），拼接时不影响原文件，但后续应优化分片脚本，按实际 split 结果上传而不是固定上传空分片。
- 最近 100 条 Actions runs 中发现的非 success 项均为并发更新触发的 cancelled，另有 Mainland run #164 package job failure。#164 失败日志已复核：失败步骤为 chunk 数量限制（旧逻辑限制 7×20MiB），不是 EXE 构建；后续已扩容分片并在 #190 完成套餐构建。run #189 因新 push 的 concurrency cancel-in-progress 被取消，最终 run #190 成功。
- Autonomous Business Engine run #360：[#41826304325](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41826304325)，同一 main commit，build/deploy 两个 job 均 success；Pages artifact ID `13319018081`。

**当前交付判断：** 12 款 EXE 已在 GitHub Windows runner 上完成回归测试、PyInstaller 构建及非交互冻结 EXE 退出码自测；最新客户 ZIP 已实际下载、校验 CRC、条目数量及 manifest SHA256。它仍不是完成真实 Windows GUI 使用与卖家授权激活验收的正式销售版。卖家私钥不在仓库，`src/license.py` 内嵌公钥与 config 公钥指纹不同；不得猜测或更换密钥。必须由卖家在可信 Windows 电脑本地导出公钥 SHA256 指纹后比对，随后进行真实签发、设备绑定、到期日、签名、激活与重启测试。


## 第二阶段产品：报价单生成器（PR #12 已合并，Windows CI 通过，待终端授权验收）

- 分支：`feat/local-quotation-generator`；新增 `apps/报价单生成器.py`，授权产品 ID：`报价单生成器`。
- 功能：客户与报价信息管理、多行报价明细、数量×单价自动计算、税率与含税总计、中文 PDF 报价单、CSV 多明细分组导入/导出、本地 JSON 持久化、备份与恢复。
- PDF 使用 ReportLab 内置 STSong-Light 中文 CID 字体；依赖已加入 requirements。冻结 EXE 自测会实际生成 PDF，避免只验证导入模块；仅报价单 EXE 收集 ReportLab 子模块，避免给其他产品增加体积。
- CSV 导入遇到重复报价单号、缺字段、非法数量/日期或同一报价单元数据不一致时整批拒绝；备份恢复先验证格式和全部记录，再写入。
- 新增回归测试覆盖金额/税额、日期/数量验证、持久化、重复编号、CSV 多行分组与原子拒绝、备份恢复、报价单号生成及 PDF 生成。
- 已加入 13 款 Windows 构建矩阵、独立授权路径测试、客户套餐与中文说明书索引；分片改为 18 MiB 并在 manifest 记录实际分片数。PR #12 的 13/13 Windows job、报价单 25 项回归测试、源代码自测、冻结 EXE PDF 生成自测及套餐打包均通过；主线 run #206 再次通过。代码与构建层面已进入待终端验收状态。
- 本分支不修改任何生产公钥或卖家私钥。真实卖家密钥匹配和 Windows 授权激活仍待最终验收。


## 2026-11-04 PR #12 合并及 main run #206 客户包验收

- PR #12：[#12 Add offline Chinese quotation generator with PDF export](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/12)，已 squash 合并；合并提交：`9f2d98f29f4efec6abdd61e974b20f46ff71848d`。合并前 head：`12ed8fe6fc5aca9152013a9be74f021ff05d5d6e`。当前 open PR 查询为 0。
- PR #12 的最终 Mainland Windows EXE run #205：[#41831072576](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41831072576)，13/13 Windows build jobs 与 package job success；code scanning run #51 success。早期 run #203 曾因 packaging 回归测试仍断言旧的 `parts[@]` 条件而失败（13 个 job 都在测试阶段失败，24/25 或 15/16 passed）；已修正测试断言匹配 `parts_count` 后 run #205 全绿。run #204 是 push/PR 双触发竞争中的取消项，不代表最终失败。
- 报价单生成器 job #126578729258：25 passed；source self-test success；ReportLab 专用 PyInstaller build success；冻结 EXE self-test 生成中文 PDF 后在 30 秒内以退出码 0 结束；产品 artifact ID `13322133686`。PR 客户套餐 artifact ID `13321529563`，manifest artifact ID `13321704461`。PR 包已实际下载检查：13 个 EXE、13 份产品说明书、说明书索引、README 和套餐说明均存在，ZIP CRC 与 manifest SHA256 一致。
- 合并后 main 最新提交：`9f2d98f29f4efec6abdd61e974b20f46ff71848d`。Mainland Windows EXE run #206：[#41831887166](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41831887166)，13/13 Windows build jobs 与 customer package job 全部 success。报价单生成器 main job #126580865534：25 passed；冻结 EXE self-test 日志有 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`；main 单品 artifact ID `13322374488`。
- main 客户套餐 artifact `mainland-phase1-customer-package` ID：`13323183619`，大小 219,317,595 bytes；manifest artifact ID `13322093954`。已实际下载：外层 artifact ZIP CRC 完整，包含内层 ZIP 和 README；内层客户 ZIP 219,255,426 bytes，SHA256 `f63cf9cea9e80d594e7f765f2b3ac0d984a8ab3193b986fef7a90c92e209e1ab`，与 manifest 的 bytes、SHA256 完全一致；`ZipFile.testzip() = None`。
- 内层 ZIP 共 31 个条目（29 个文件、2 个目录）：13 个 EXE、13 份产品用户说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT；报价单生成器 EXE 与 `12-报价单生成器-用户说明书.md` 均已纳入。README/套餐说明文件时间戳：2026-11-04 12:46:18 UTC（中国标准时间 20:46:18）。
- manifest 声明 `parts=12`、`part_size=18MiB`；12 个分片 artifact 均为非空数据块，最后一块 11,635,735 bytes，其余每块 18,874,564 bytes。该版不再出现空分片。
- Autonomous Business Engine run #362：[#41831887218](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41831887218)，main commit 同上，build/deploy success；Pages artifact ID `13322828940`（48,833 bytes）。

**当前交付判断：** 13 款 Windows EXE 已通过 GitHub Windows runner 回归测试、PyInstaller 编译及冻结 EXE 非交互自测；报价单生成器还通过了真实 PDF 文件生成自测。最新 main 客户 ZIP 已下载并核验文件数量、CRC、manifest SHA256 和版本时间。仍需真实 Windows 用户环境检查 GUI 与实际业务流程；更关键的是卖家私钥尚未确认与 `src/license.py` 内嵌公钥匹配，真实签发/设备绑定/激活/重启验收未完成。**所有产品继续标记为待最终验收，不能宣称已完成正式授权销售。**


## 2026-11-05 本轮基线复核与第四阶段产品开发

- 本轮 main 最新提交检查：`cabab2e9a10ea84898be25557ec28526584c7dab`（记录 PR #12 合并与 main run #206 验收）；open PR 查询为 0。
- 本轮可读取的最近 main Mainland Windows EXE run #206：[#41831887166](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41831887166)。14 个 job（13 个产品构建任务 + customer package）全部 success；未发现失败 job，因此没有失败日志需要修复。报价单 job #126580865534 与财务 job #126580865127 日志均显示冻结 EXE self-test 成功；套餐 job #126581570284 成功上传分片。
- Autonomous Business Engine run #362：[#41831887218](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41831887218)，build/deploy 均 success；build 执行 pytest、business_engine、product_factory、xianyu_factory 并成功上传 Pages artifact。
- 已实际下载 run #206 客户套餐 artifact `13323183619`（外层 ZIP 219,317,595 bytes，SHA256 `4caa80a04233a5bae130c3e54c97b1a8ae423daeb94773180d81e46f6ba4b660`）及 manifest artifact `13322093954`。外层 ZIP CRC 通过；内层客户 ZIP 219,255,426 bytes，SHA256 `f63cf9cea9e80d594e7f765f2b3ac0d984a8ab3193b986fef7a90c92e209e1ab`，与 manifest 声明字节数和 SHA256 完全一致，`ZipFile.testzip() = None`。
- 内层包共 31 个条目（29 文件、2 目录）：13 个 EXE、13 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。套餐说明 ZIP 时间戳为 2026-11-04 20:46:18（中国标准时间）。这是 run #206 的真实下载验收结果，不代表其后 main docs commit 有新的 push run 已被本轮工具确认。
- 新增产品：`费用报销管理助手`，分支 `feat/expense-reimbursement-manager`。支持报销单号自动生成、日期/金额校验、费用分类、发票与付款状态、月份/类别/状态/关键词筛选、Decimal 精确汇总、CSV UTF-8 BOM 导入导出、JSON 备份恢复及本地持久化。
- CSV 导入采用严格表头、追加模式和整批校验；重复单号、非法日期/金额或无效状态会整批拒绝。写盘失败时回滚内存状态；新增回归测试覆盖数据重载、ID、金额四舍五入、状态规则、CSV 原子导入、备份恢复、筛选汇总和写盘失败回滚。
- 同步修复工具箱只显示最初 9 款工具的问题：现将 13 款业务 EXE 全部列入启动器，并加入启动器数量/唯一性自测。
- 新产品已加入授权产品 ID 路径测试、冻结 EXE 构建矩阵、中文说明书索引和套餐；客户包调整为 14 个 EXE，并把分片容量上限扩展到 15 × 18 MiB。
- 当前分支的 Windows Actions 与客户包下载验收尚未完成；此新产品不得标记为可交付。卖家私钥仍未匹配，真实 Windows 授权激活仍待最终验收。
