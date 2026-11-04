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
