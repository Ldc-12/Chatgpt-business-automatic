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


## 2026-11-05 PR #13 费用报销管理助手：Windows 构建与套餐验收

- PR #13：[#13 Add offline expense reimbursement manager for Windows](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/13)，分支 `feat/expense-reimbursement-manager`。本轮继续在该 PR 中修复工具箱冻结版定位路径，并优化分片 artifact 上传。
- 费用报销管理助手功能：本地报销台账、自动编号、日期与 Decimal 金额校验、费用类别/发票/付款状态、月份/状态/类别/关键词筛选、精确汇总、CSV UTF-8 BOM 导入导出、JSON 备份恢复和原子写盘。数据位于 `%LOCALAPPDATA%\\MainlandBusinessTools\\reimbursements.json`。
- 费用报销产品回归测试 38 passed；冻结 EXE self-test 生成临时数据、CSV 与备份文件，并在 30 秒内以退出码 0 退出。
- 工具箱启动器修复：PyInstaller one-file 下 `__file__` 指向临时解包目录，原实现会到错误目录查找同套餐 EXE。现冻结模式改用 `Path(sys.executable).resolve().parent`，源码模式仍用源码目录；新增两种路径行为测试。工具箱回归测试 21 passed，冻结 EXE self-test 通过。工具箱中文说明书已更新为 13 款业务工具完整列表，并明确所有 EXE 应保持在同一目录。
- 分片 artifact 修复：PR #13 首次构建 run #225 虽成功，但旧脚本上传了两个 196-byte 空分片（part-13、part-14）。run #228 的新增回归测试先捕获到未删除的填充循环，四个矩阵任务因此在测试阶段失败；已移除填充循环并改为单个通配符 artifact，仅上传 split 实际生成的分片。
- 最终 PR Windows 构建 run #229：[#42024528968](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42024528968)，head `060cd733f17cd0cf05ee36b0cb8a9db8e8f10f8f`。14/14 Windows build matrix jobs 与 customer package job 全部 success；没有失败 job。费用报销测试 38 passed，工具箱测试 21 passed；两款冻结 EXE 均出现 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`。
- PR #13 客户套餐 artifact `mainland-phase1-customer-package` ID：`13413526110`，234,078,771 bytes，artifact SHA256 `4e59dda08ce48f13b4385d0bab200453975ba0077a2e1b78205c043c769e68f1`；manifest artifact ID `13413526119`。已实际下载两个 artifact 并检查外层 ZIP CRC。
- 内层客户 ZIP：234,012,455 bytes，SHA256 `00e847833c34a167a1e2fe057e1baad0e903fc1c343d2733d74dbb2266f9be39`，与 manifest 字节数和 SHA256 完全一致；`ZipFile.testzip() = None`。
- 内层 ZIP 共 33 个条目（31 个文件、2 个目录）：14 个 EXE（13 款业务工具 + 工具箱）、14 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。新 EXE `MainlandExpenseReimbursement.exe` 和说明书 `13-费用报销管理助手-用户说明书.md` 均存在。README 明确写明无需 ChatGPT/VPN/外部 AI；套餐说明为 A 19.9 元、B 29.9 元、C 39.9 元建议价。
- 版本时间：内层 ZIP 所有文件时间戳为 2026-11-05 12:09:24 UTC（中国标准时间 20:09:24）。
- 分片 artifact `mainland-phase1-package-parts` ID：`13413710796`，已实际下载检查，外层 CRC 完整，恰有 13 个非空分片（00–12），前 12 块各 18,874,368 bytes，最后一块 7,520,039 bytes；无空分片。manifest 记录 `parts=13`。
- 费用报销 PR 的代码与 Windows runner 构建层面通过；PR 尚未合并，当前包是 PR 验证候选包，不是 main 正式发布包。真实 Windows GUI 业务验收、卖家私钥与客户端公钥匹配、真实签发/设备绑定/激活/重启测试仍待最终验收。没有修改或生成任何生产密钥。


## 2026-11-05 PR #13 最终回归 run #232 与候选包复核

- 为避免内部发布记录每次更新都重复执行 14 个 Windows EXE 构建，已从 Mainland Windows EXE 的 push/pull_request 路径过滤中移除 `docs/RELEASE_STATUS.md`；产品说明书、源码、测试和工作流仍会触发构建。新增回归测试验证此规则。
- run #231 曾因首次只移除一个触发路径而被新增测试正确拦截：14 个矩阵 job 在 pytest 阶段失败，原因是 push 路径过滤中仍残留 `docs/RELEASE_STATUS.md`。已从两个路径过滤块全部移除，未改动产品测试断言。
- 最终 Mainland Windows EXE run #232：[#42026125804](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42026125804)，head `b8d431f41043fc2eff1ad292cebc6467a498d71e`；14/14 Windows build job 与 customer package job 全部 success，无失败 job。
- run #232 客户套餐 artifact ID：`13413104087`，234,077,783 bytes，外层 artifact SHA256 `8614282d7d795a01453962b5be9a07f614dee388147787f8fbcc7267f90a2f90`；manifest artifact ID：`13413064505`；分片 artifact ID：`13413628121`。
- 已实际下载 run #232 的客户包、manifest 和分片 artifact。外层 ZIP CRC 全部通过；内层客户 ZIP 234,011,381 bytes，SHA256 `6f7cfbcbbaac135886d2210997d4f750adf0f302d5cb9054a832157aa51f8814`，与 manifest 中的 bytes、SHA256 完全一致，`ZipFile.testzip() = None`。
- 内层 ZIP 仍为 33 个条目（31 文件、2 目录）：14 个 EXE、14 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。新费用报销 EXE、说明书和工具箱 13 款入口均存在；套餐建议价为 A 19.9 元、B 29.9 元、C 39.9 元。
- 分片 artifact 恰有 13 个非空文件，前 12 块各 18,874,368 bytes，最后一块 7,518,965 bytes；无空分片。manifest 记录 `parts=13`。
- 内层 ZIP 文件时间戳：2026-11-05 12:21:08 UTC（中国标准时间 20:21:08）。
- PR #13 的代码、回归测试、Windows 冻结 EXE 自测与客户套餐结构均已通过 PR run #232。此包是 PR 验证候选包，PR 合并后的 main push 构建仍需单独记录；不得把 PR artifact 误称为 main 最新 artifact。
- 最终终端验收仍未完成：未在真实用户 Windows 环境完成 GUI/业务流程测试，卖家私钥仍未与客户端内嵌公钥匹配确认，真实授权签发、设备绑定、激活和重启测试待用户本地公钥指纹比对。未更改、生成或索取任何生产私钥。

## 2026-11-05 PR #13 合并状态更正
- PR #13 已于 2026-11-05 12:24:07 UTC squash 合并：https://github.com/Ldc-12/Chatgpt-business-automatic/pull/13；main 合并提交：`128b3dde3b6ac76a0117c692d3bf38d038e862fb`。本轮复核 main 最新提交为该 SHA，open PR 查询为 0。
- PR run #232 已对合并前同一代码树完成 14/14 Windows 构建与客户套餐构建；真实下载验收的候选包 SHA256 为 `6f7cfbcbbaac135886d2210997d4f750adf0f302d5cb9054a832157aa51f8814`，artifact ID `13413104087`，manifest `13413064505`，分片 `13413628121`。
- **主线发布包状态：** PR 合并已完成，但本轮无法从当前可用的 Actions 记录接口确认 merge commit 对应的 main push Mainland Windows EXE run 与其 artifact；因此上述 run #232 包仍标记为“合并前 PR 验证包”，不能冒称为 merge commit 的 main 最新包。下一次复核应以 main push workflow 对应的 mainland-phase1-customer-package artifact 为准，并重新下载核验 ZIP/manifest。
- Autonomous Business Engine 最近可直接复核的记录仍为 run #362（build/deploy success，67 passed，Pages artifact `13322828940`）。merge commit 之后的 push/scheduled run 本轮未能确认，不虚构 run 编号或结果。
- 正式销售验收继续待真实 Windows GUI/业务流程、卖家私钥公钥指纹匹配，以及真实授权签发/设备绑定/激活/重启测试。


## 2026-11-05 main 正式套餐 run #234 下载验收

- 本轮检查 main 最新提交：`54ef3dd82e96e8a9706686003e478a988dec98dd`（发布状态文档更新）；当时 open PR 查询为 0。
- 与 main 当前产品代码树对应的 Mainland Windows EXE run #234：[#42026812901](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42026812901)，构建代码提交 `128b3dde3b6ac76a0117c692d3bf38d038e862fb`。14/14 产品矩阵 job 与 customer package job 全部 success；14 个 EXE 均通过各自回归测试、源码自测和冻结 EXE self-test，customer package job 成功，无失败 job。
- 最新 Autonomous Business Engine run #367：[#42026956213](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42026956213)，build/deploy 均 success；pytest、business_engine、product_factory、xianyu_factory 与 Pages 上传/部署步骤均成功。Pages artifact ID：`13414476929`。
- 已下载 run #234 的客户套餐 artifact ID `13414696728`（234,072,962 bytes，外层 SHA256 `a7526bbeb92d6c4e5222bfa2b0bb31ae7135a86ba8249afecd928739e4ed5e3e`）、manifest artifact ID `13414292652`、分片 artifact ID `13414806378`。三个外层 ZIP 的 CRC 均通过。
- 内层客户 ZIP：234,006,576 bytes，SHA256 `7ce567c8fbd0131fbdd67832ccb8ec6cb2fcb58c480ed4adff716bc044991555`，与 manifest 的 bytes/SHA256 完全一致，`ZipFile.testzip() = None`。共 33 个条目（31 文件、2 目录）：14 个 EXE、14 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。所有内层文件时间戳为 2026-11-05 12:26:38 UTC（中国标准时间 20:26:38）。
- 分片 artifact 恰有 13 个非空分片（00–12），前 12 个各 18,874,368 bytes，最后一个 7,514,160 bytes；拼接后 SHA256 与内层 ZIP 一致。套餐建议价仍为 A 19.9 元、B 29.9 元、C 39.9 元。
- 这是 main push run #234 的正式主线构建包，不是 PR 候选包。main HEAD `54ef3dd...` 仅更新发布记录，没有产品源码变更；对应产品代码树已由 run #234 构建。

## 新增产品：售后维修工单管理助手（PR 开发中，待 Windows CI）

- 新增本地 Windows/Tkinter 产品：`apps/售后维修工单管理助手.py`，产品 ID `售后维修工单管理助手`，数据保存于 `%LOCALAPPDATA%\\MainlandBusinessTools\\repair_orders.json`。
- 功能：工单自动编号、客户/电话/设备/故障记录、待检测/待报价/维修中/待取件/已完成/已取消状态、预约取件与完工日期、预计费用与实收金额、月份/状态/关键词筛选、CSV UTF-8 BOM 导入导出、JSON 备份恢复。
- CSV 使用严格字段校验和追加模式；重复工单号或任一无效记录会整批拒绝。金额使用 Decimal 精确到分，写盘失败回滚内存状态；完成状态必须填写完工日期。
- 新增回归测试覆盖保存重载、自动编号、日期与金额校验、状态约束、重复 ID、编辑删除、CSV 往返/BOM/整批拒绝、备份恢复、筛选汇总和写盘失败回滚。
- 已加入授权产品路径测试、工具箱启动器、Windows 构建矩阵、客户套餐、中文说明书索引。预计套餐调整为 15 个 EXE（14 款业务工具 + 启动器），仍需实际构建核对分片容量。
- 当前分支：`feat/repair-work-order-manager`。PR Windows 构建、artifact 下载验收和真实 Windows GUI 测试尚未完成；不得标记为可交付。卖家私钥/内嵌公钥匹配及真实激活仍是独立待最终验收项。


## 2026-11-06 最新 main 套餐复核与第六阶段产品开发

### 已验证的 main 发布包（2026-11-05 构建）

- 本轮检查时 main 最新提交：`02ed7cf28199f1a1b160cb44e612cfc6f777c6a2`（Add offline repair work-order manager）；未完成 PR：0。
- Mainland Windows EXE run #248：[#42030635353](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42030635353)，head 为上述 main commit，整体 `success`。15/15 个产品构建 job 与 Phase 1 customer delivery package job 全部 success；产品测试、源码自测、PyInstaller 构建和冻结 EXE 自测均通过。维修工单 job #127255885217：`36 passed`，冻结 EXE 日志出现 `FROZEN_EXE_SELF_TEST_OK`；报价单生成器 job #127255885411：`30 passed`，冻结 EXE 自测退出码 0。
- 客户套餐 artifact：`mainland-phase1-customer-package`，ID `13415098998`，artifact 大小 248,828,480 bytes；创建时间 2026-11-05 12:53:04 UTC（北京时间 20:53:04）。已实际下载外层 artifact：SHA256 `6d9276746fa03752b34f4963412a365a83d6665c53e597c0f4fef9edde0838d2`，外层 CRC 检查通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：248,758,240 bytes，SHA256 `7ee643b172398502ea97e72e121bf94812512f1c0f4cc2c482d95e68f936f75d`；与 manifest artifact ID `13416680725` 的字节数和 SHA256 完全一致，manifest 声明 14 个分片。内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 35 个条目（33 个文件、2 个目录）：15 个 EXE、15 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。README 声明 15 款 Windows EXE（14 款业务工具及工具箱启动器）；套餐说明 C 也是全部 14 款业务工具 + 工具箱启动器，与该 run 的 15 个 EXE 数量一致。下一次加入门店排班考勤助手的构建将更新为 16 款 EXE（15 款业务工具及工具箱启动器）。所有文件时间戳为 2026-11-05 12:52:42 UTC（北京时间 20:52:42）。
- 最新 Autonomous Business Engine scheduled run #372：[#42177016070](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42177016070)，build/deploy 均 success；测试 `112 passed`；Pages artifact ID `13483851199`，47,818 bytes。
- 近期失败 PR 检查 run #246（[#42029549866](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42029549866)）失败于过时的 workflow-trigger 字符串断言；run #231（[#42025824630](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42025824630)）失败于过时的分片脚本断言。两者均为 PR 头部测试配置断言，后续 main run #248 已通过完整构建与打包；没有把这些失败记录改写为成功。

### 新产品：门店排班考勤助手（PR #15 已合并，main run #251 验收通过）

- PR #15：`feat/store-scheduling-attendance-assistant`，已 squash 合并到 main；合并提交 `f7bb4e2f615fcd8616126971a391ee05fce9ae20`，父提交为 `02ed7cf28199f1a1b160cb44e612cfc6f777c6a2`。
- 新增源码：`apps/门店排班考勤助手.py`；产品授权 ID：`门店排班考勤助手`。
- 功能：员工每日排班登记、出勤/休息/请假/缺勤状态、跨午夜班次、休息分钟扣除后的工时统计、同员工同日重复检查、跨日班次冲突检测、关键词/月度/状态筛选。
- 支持 UTF-8 BOM CSV 追加导入/筛选结果导出，以及带版本标记的 JSON 备份/恢复；导入和恢复验证失败时保持原数据不变，磁盘写入失败时回滚内存状态。
- 数据本地保存到 `%LOCALAPPDATA%\\MainlandBusinessTools\\store_schedule.json`；不连接云端，不依赖 VPN、ChatGPT 或外部 AI。
- 已新增中文说明书、回归测试、独立授权路径测试，并集成工具箱启动器及 16 款 EXE 构建/客户套餐矩阵。PR run #250 与合并后的 main run #251 均已通过 16/16 Windows 构建 job 和客户套餐 job；main run #251 下载包验收见下方记录。
- 授权最终验收仍独立待办：两份仓库公钥指纹不同，卖家私钥不在仓库；不得上传私钥。需用户仅提供本地导出的公钥或 SHA256 指纹，之后再做真实 Windows 签发/激活/重启测试。


## 2026-11-06 PR #15 合并与 main run #251 正式发布验收

- PR #15（Add offline store scheduling and attendance assistant）已于 2026-11-06 squash 合并，merge commit：`f7bb4e2f615fcd8616126971a391ee05fce9ae20`。合并后 open PR 查询为 0。
- PR Mainland Windows EXE run #250：[#42214308900](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42214308900)，结论 `success`；16/16 Windows build jobs 与 package job 全部 success，17/17 check runs success。新产品 job #127880760934：`37 passed`，冻结 EXE 自测输出 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`；单品 artifact ID `13499463866`，已下载检查，包含 `MainlandStoreScheduleAssistant.exe` 和单品 ZIP，嵌套 ZIP 含 EXE 与 UTF-8 README，CRC 通过。
- PR run #249 曾失败于新产品测试中把 480 分钟休息误标为无效（实际 9 小时班次允许 480 分钟休息）；日志确认是测试数据错误，不是程序逻辑错误。已把测试改为 540 分钟（等于班次总时长）和 721 分钟（超过上限），run #250 随后通过。未掩盖 run #249 的失败记录。
- 合并后的 main Mainland Windows EXE run #251：[#42214811702](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42214811702)，head `f7bb4e2f615fcd8616126971a391ee05fce9ae20`，整体 `success`；16/16 产品构建 job 与 Phase 1 customer delivery package job 全部 success。门店排班考勤助手 main job #127882063062：`37 passed`，冻结 EXE 自测退出码 0；单品 artifact ID `13501320173`。
- main 客户套餐 artifact：`mainland-phase1-customer-package` ID `13500702853`，外层大小 263,583,620 bytes，外层 SHA256 `af144bceefdd0d95f82afddc6afed2c6ce901a299c44969c893001426657859a`。已实际下载，外层 CRC 通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：263,509,056 bytes，SHA256 `9c40d6377f2638459f4687e5793e1da47dcd049aa3e23af063eeccf31dad2aee`；manifest artifact ID `13500896334` 的 bytes、SHA256 完全一致，manifest 记录 14 个分片；分片 artifact ID `13501430214`。内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 37 个条目（35 个文件、2 个目录）：16 个 EXE、16 份产品说明书（15 款业务工具 + 工具箱）、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。新产品 EXE、说明书、授权文件名示例和工具箱入口均已存在；套餐 C 为全部 15 款业务工具 + 工具箱启动器。内层文件时间戳为 2026-11-06 12:05:28 UTC（北京时间 20:05:28）。
- 最新 Autonomous Business Engine main run #373：[#42214811677](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42214811677)，build/deploy 均 success；完整测试 `129 passed`；Pages artifact ID `13499049754`，47,764 bytes。
- **交付状态：** 门店排班考勤助手已完成代码、回归测试、PyInstaller EXE、冻结 EXE 非交互自测、PR 构建、main 构建及客户套餐下载/manifest 核验；代码和 CI 构建层面可交付。整个产品线仍标记“待最终验收”：卖家真实私钥与客户端公钥匹配、真实 Windows 设备签发/激活/重启、真实 GUI 业务流程测试尚未完成；不得宣称已完成正式授权销售验收。


## 2026-11-07 PR #16 合并、17 款 EXE 主线构建与客户包核验

### 合同台账与到期提醒助手

- PR #16（[Add offline contract ledger and expiry reminder assistant](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/16)）已 squash 合并；merge commit：`ffb6fb33ae0e89116aaf57ec650742f39fe7b16e`。合并后 open PR 查询为 0。
- 新增源码：`apps/合同台账与到期提醒助手.py`；产品授权 ID：`合同台账与到期提醒助手`；数据保存在 `%LOCALAPPDATA%\\MainlandBusinessTools\\contracts.json`。
- 主要功能：合同编号/名称、甲乙方、签订/生效/到期日期、金额、负责人、联系方式、状态、提前续约天数；到期/逾期状态、搜索筛选、待提醒筛选；UTF-8 BOM CSV 追加导入和筛选导出；版本化 JSON 备份与恢复。
- 本轮代码加固：恢复前严格校验 JSON 根对象、整数版本号（拒绝布尔值）、contracts 数组和每条记录对象；损坏 JSON、缺少列表、错误类型或非法行均拒绝恢复，保留原内存和磁盘数据。新增回归测试覆盖这些异常输入。
- PR Mainland Windows EXE run #252（[#42334422717](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42334422717)）曾失败：17 个 Windows 产品矩阵 job 的共同原因是 `tests/test_mainland_packaging.py` 仍断言旧的 16 EXE/15 业务工具数量；合同台账加入后实际应为 17 EXE/16 业务工具。日志显示每个产品的构建步骤在测试阶段即停止，未生成 PR 客户包。该失败没有被隐藏。
- 修复包括更新套餐数量断言、把合同台账加入冻结 EXE 入口回归清单、更新启动器 EXE 列表断言和工具箱中文说明书（16 款业务工具）。PR Mainland Windows EXE run #255（[#42367823147](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42367823147)）最终 18/18 checks success；17 个产品/启动器构建 job + 1 个客户套餐 job 全部成功。合同台账 job：30 passed，冻结 EXE 自测退出码 0；启动器 job：26 passed，冻结 EXE 自测退出码 0。
- PR 候选包 artifact ID `13572023880` 已下载核验：外层 278,345,652 bytes，SHA256 `30a8a7d399a65701121fa6165349ed363c4673ca2b513e038ac30be249853a8f`；内层 ZIP 278,267,126 bytes，SHA256 `40ecab061a92c26ff620a1e168145769116cf092cb3c0a27e5949bde25c5fbe7`；manifest artifact ID `13571864538` 的 bytes/SHA256 完全匹配，parts artifact ID `13572038893`。外层与内层 CRC 均通过。候选包有 17 EXE、17 份产品说明书、1 份说明书索引、README 和套餐说明。

### 合并后的 main 正式构建与客户套餐

- main 发布代码提交：`ffb6fb33ae0e89116aaf57ec650742f39fe7b16e`（PR #16 merge commit）；其后 main 提交均为发布状态文档记录，不改变产品代码；未完成 PR：0。
- Mainland Windows EXE main run #256（[#42368069913](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42368069913)）：整体 success，18/18 jobs 成功（17 个产品/启动器构建 + 客户套餐 job）。合同台账 main job #128390264509：30 passed，冻结 EXE 自测输出 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`；启动器 job #128390264486：26 passed，冻结 EXE 自测退出码 0。
- main 客户套餐 artifact `mainland-phase1-customer-package` ID `13572059403`，外层 278,350,620 bytes，SHA256 `62abdb8d6992101546eead1f3d549d9a26c5f3e4089f0a5086296e6c1ca5ae53`；已实际下载，外层 ZIP CRC 通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：278,271,976 bytes，SHA256 `95f5e61a4057b873bc44de559d39cbb0bcfb2d3161bfbc31bb0e2bb4889b5784`；manifest artifact ID `13572154354` 中的 bytes/SHA256 完全匹配；分片 artifact ID `13572159266`，manifest 记录 15 个 18 MiB 分片。内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 39 个条目（37 个文件、2 个目录）：17 个 EXE（16 款业务工具 + 工具箱启动器）、17 份产品说明书（16 款业务工具 + 工具箱）、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。README 数量、套餐 C 产品数量与 EXE 实数一致；套餐 C 是全部 16 款业务工具 + 启动器。包内文件时间戳为 2026-11-07 11:26:14 UTC（北京时间 19:26:14）。
- 合同台账单品 artifact ID `13572935092` 已下载核验：外层 29,519,664 bytes，SHA256 `e00c33effa9d20538a78a9a23e60cd3e9be676124996b333c9a6bb6a24a1085d`；外层和嵌套 ZIP CRC 均通过；嵌套 ZIP 含 `MainlandContractLedgerAssistant.exe` 与 UTF-8 `README-mainland.txt`。
- 合并代码后的 Autonomous Business Engine main run #377（[#42368069900](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42368069900)）：build/deploy 均 success，测试 `138 passed`；Pages artifact ID `13572204036`，47,771 bytes。
- 本发布状态文档提交后的最新 Autonomous Business Engine main run #378（[#42368331248](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42368331248)）：build/deploy 均 success，测试 `138 passed`；Pages artifact ID `13572498649`，47,764 bytes。该次为文档变更触发，不改变 Mainland Windows EXE #256 的客户包内容。
- 最新通用 Windows EXE Build main run #115（[#42368069937](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42368069937)）success。

### 最终验收阻塞

- 仓库内嵌公钥指纹与配置公钥指纹仍不同：`src/license.py` 为 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem` 为 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。
- 卖家私钥不在仓库；未猜测、替换或新造私钥，也未要求上传私钥。代码/CI 和冻结 EXE 非交互自测通过，不等于真实授权激活通过。
- **交付状态：** 合同台账与到期提醒助手已完成代码、回归测试、Windows EXE 构建、冻结 EXE 非交互自测、PR/main 构建及主线客户套餐下载与 manifest 核验；17 款 EXE 主线包在构建层面可交付。整个产品线仍为“待最终验收”：真实 Windows GUI 操作、卖家公钥匹配、签发/激活/重启测试未完成，不得宣称已经完成正式授权销售验收。


## 2026-11-08 PR #17 合同履约工作流与风险规则增强

### 产品增强与验证
- PR #17（[Add contract fulfillment milestones and offline risk rules](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/17)）已于 2026-11-08 squash 合并；main 合并提交：\`8f0415ce670d3dcd2c83a2e917b6716d4f41e1c6\`。
- 在现有“合同台账与到期提醒助手”上增加离线履约节点：付款、收款、交付、验收、保证金、续约和其他事项；节点支持新增/编辑/完成/删除、计划金额与日期、严格 CSV 导入导出。
- 新增本地确定性风险规则：执行中合同过期、待办节点逾期/7 日内到期、履约节点日期超出合同期限、合同主体缺失、付款/收款计划合计超过合同金额、缺少履约计划和孤立节点。结果显示规则编号、风险等级与建议动作，不构成法律意见。
- 新增合同与节点操作日志、待付款/待收款和已完成金额汇总；新版 v2 备份包含合同、节点和日志，恢复前校验结构、版本、重复编号和合同关联，并保留旧版 v1 合同备份兼容恢复。
- 数据继续保存在本地：合同主表 \`%LOCALAPPDATA%\\MainlandBusinessTools\\contracts.json\`；履约节点和日志 \`%LOCALAPPDATA%\\MainlandBusinessTools\\contract_workflow.json\`。不调用 VPN、ChatGPT、外部 AI、云端或外部 API。
- 中文说明书已同步更新，明确风险规则、CSV 字段、旧备份迁移行为及不读取 PDF/Word、不提供法律意见等边界。

### PR Windows 验证
- PR Mainland Windows EXE run #258：[#42440171201](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440171201)，head \`8c05b6fced63f249e163586dfb37453254d610a1\`，18/18 jobs success（17 个产品/启动器构建 + customer package）。
- 合同台账 job #128607505911：\`36 passed\`；PyInstaller 标准 EXE 构建成功；冻结 EXE 自测输出 \`FROZEN_EXE_SELF_TEST_OK: process exited with code 0.\`。
- PR 客户包 artifact ID \`13601412144\` 已下载核验；内层 ZIP 17 个 EXE、17 份产品说明书、说明书索引、README 与套餐说明；内层 CRC 通过，manifest 与 15 个分片拼接 SHA256 一致。
- 首次 PR run #257（[#42440069079](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440069079)）曾因新测试未导出 workflow 常量、风险规则编号使用中文而失败（2 failed / 34 passed）；已修正并在 run #258 复验通过。该失败记录保留，未改写为成功。

### 合并后 main 正式构建与客户包
- main Mainland Windows EXE run #259：[#42440410231](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410231)，head \`8f0415ce670d3dcd2c83a2e917b6716d4f41e1c6\`，整体 success；18/18 jobs 全部 success（17 个产品/启动器 + Phase 1 customer delivery package）。
- main 合同台账 job #128608232978：\`36 passed\`；冻结 EXE 自测退出码 0；单品 artifact ID \`13600599066\`。
- main 客户包 artifact \`mainland-phase1-customer-package\` ID \`13601262927\`，278,393,605 bytes；外层 SHA256：\`74329d626f81429374f24b66ecc026dde5ca91f5522af77e07eb88c63ed5ea63\`。已实际下载，外层 ZIP CRC 检查通过。
- 内层 \`Phase1-Mainland-Windows-Tools.zip\`：278,314,876 bytes；SHA256：\`9ae659441a1d63fa0da016f9e0e8db21c1db203a17611f8be77ffa0007797427\`。manifest artifact ID \`13601642030\` 中 bytes/SHA256 完全匹配；parts artifact ID \`13601587362\` 含 15 个分片（14 个 18 MiB，末片 14,073,724 bytes），拼接后 bytes/SHA256 与内层 ZIP 完全一致。外层、manifest、parts、内层 ZIP CRC 均通过。
- 内层 ZIP 共 39 个条目（37 个文件、2 个目录）：17 个 EXE（16 款业务工具 + 工具箱启动器）、17 份说明书（16 款业务工具 + 工具箱）、1 份说明书索引、1 份大陆版 README、1 份套餐说明 TXT。套餐 A/B/C 描述与既有 17 EXE 数量一致；套餐 C 为 16 款业务工具 + 启动器。内层文件时间戳为 2026-11-08 02:55:24 UTC（北京时间 10:55:24）。
- main Autonomous Business Engine run #383：[#42440410278](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410278)，build/deploy 均 success；\`144 passed\`；GitHub Pages artifact ID \`13601382380\`（47,789 bytes）。
### 最终销售验收仍未完成
- 以上证明 PR 与 main 的代码测试、Windows PyInstaller 构建、冻结 EXE 非交互自测、17-EXE 客户包下载和 CRC/SHA256/manifest 核验通过；**不等于真实用户 Windows GUI 业务流程验收，也不等于授权激活验收**。
- \`src/license.py\` 内嵌公钥与 \`config/mainland_license_public_key.pem\` 仍存在指纹不匹配。卖家私钥不在仓库；未请求、上传、生成、猜测或替换任何私钥。
- 上架前仍须在真实 Windows 环境完成 GUI 业务流程测试，并由卖家在可信 Windows 电脑本地导出公钥或 SHA256 指纹（只提供公钥/指纹，绝不提供私钥）以核对客户端公钥；匹配后再进行真实签发、设备激活、关闭重启和再次验证。最终状态继续标记为“待最终验收”，不得宣称已可正式上架。


## 2026-11-08 PR #18 合同履约操作日志回滚修复

### 代码修复
- PR #18（[Preserve contract workflow audit history on failed writes](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/18)）已 squash 合并。
- main 合并提交：`c4fa4a6b05c43e29cda0e47bf8e1a8ef19843fe4`。
- 修复 `WorkflowStore.add/update/delete` 的失败回滚：当操作日志达到 5,000 条上限时，新增操作会先裁剪最早日志；如果随后磁盘写入失败，旧实现只删除新日志，无法恢复被裁剪的历史记录。现在在写入前快照完整日志，失败时恢复完整快照。
- 新增回归测试覆盖 add/update/delete 三种操作在 5,000 条日志上限时模拟磁盘写入失败的回滚行为。
- 未修改授权公钥、授权签名逻辑或卖家密钥。

### PR Windows 构建与修复记录
- PR run #260（[42478139913](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42478139913)）首次运行时合同台账 job 失败：测试夹具误引用应用模块未导出的 `normalize_milestone`，日志为 `AttributeError: module 'contract_ledger' has no attribute 'normalize_milestone'`。已修正测试夹具；未掩盖该失败。
- PR run #261（[42478243727](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42478243727)）最终 18/18 jobs success。
- 合同台账 job #128724369927：`37 passed in 0.76s`；PyInstaller one-file Windows EXE 构建成功；冻结 EXE 自测输出 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`。
- PR #18 最终 head：`c1ce7f02bf7c50032c59312bd61a5fb74d7e3866`。合并后 main 的 `src/contract_workflow.py` 与 `tests/test_mainland_contract_ledger.py` blob SHA 分别与 PR head 完全相同，确认打包源文件内容与合并后的 main 一致。

### 最新候选客户包核验（PR #18 run #261）
- artifact：`mainland-phase1-customer-package`，ID `13616781099`，278,395,126 bytes；SHA256：`48fac5e0afecd63b799986dcdfe4c0febeacefec07badfdfbe8b35932d8343dc`。
- 内层客户 ZIP：278,316,564 bytes；SHA256：`14fdfb837bc32892bd7983796fce1f3a8575779ad99ea8fa90671fbf6d495bb3`。
- manifest artifact ID `13615929917`：bytes 与 SHA256 与内层 ZIP 完全一致；外层 ZIP、内层 ZIP、manifest ZIP 的 CRC 检查均通过。
- 内层 ZIP 共 39 个条目（37 个文件、2 个目录）：17 个 EXE、17 份产品用户说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。
- 套餐说明：A 电脑文件处理三件套建议 19.9 元；B 办公效率工具箱建议 29.9 元；C 全能工作效率工具箱建议 39.9 元（16 款业务工具 + 启动器）。建议价格不是平台成交保证，实际售价需根据上架表现调整。
- 包内文件时间戳：2026-11-08 12:02:36 UTC。该包由 PR run #261 生成；其源代码文件已确认与合并后的 main 相同。合并后的 main push 工作流结果尚未通过当前 GitHub 连接器独立读取，故不把 PR run 冒充 main push run。

### 工作流与授权状态
- 最近可完整核验的 Autonomous Business Engine main run 仍为 #383（[42440410278](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410278)）：build/deploy success，144 passed，Pages artifact ID `13601382380`（47,789 bytes）。PR #18 合并后的 main push ABE run 尚未独立读取。
- 授权公钥仍待卖家提供本地导出的公钥或 SHA256 指纹进行匹配；不要求、也不接收卖家私钥。真实 Windows GUI、签发、激活、重启验收仍未完成，产品线状态继续为“待最终验收”。


## 2026-11-09 PR #19 装修工程签证与进度款管理助手已合并（候选包通过，主线包待独立核验）

### 产品与数据完整性增强
- PR #19（[Add offline construction variation and progress-payment assistant](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/19)）已于 2026-11-09 squash 合并；main 合并提交：`9774c457786f3f01e4ae9cde9630ed8d49198cf5`。
- 新增 `apps/装修工程签证与进度款管理助手.py`，产品授权 ID：`装修工程签证与进度款管理助手`；业务数据保存在 `%LOCALAPPDATA%\\MainlandBusinessTools\\construction_settlement.json`。
- 产品覆盖项目合同、增项/减项/工期签证、数量/面积/体积/固定金额计算、证据文件路径与 SHA256、进度款/质保金计算、风险规则和操作日志；不依赖 VPN、ChatGPT、外部 AI、云端或外部 API。
- 支持三类 CSV 严格导入/导出、全量 JSON 备份恢复、项目/签证/进度款关联校验和失败写入回滚。规则结果只作业务核对提示，不是法律意见、造价鉴定或审计结论。
- 本轮追加完整性校验：CSV/备份中的签证金额必须与计量规则重新计算结果一致；篡改金额会整批拒绝或拒绝恢复，不覆盖原数据。新增回归测试覆盖 CSV 与备份两条路径。

### PR Windows 构建与候选客户包核验
- PR 最终 Mainland Windows EXE run #266：[#42552887063](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42552887063)，最终 head `59fab873e5267415e3004eb2e083abda741230d3`；19/19 jobs success（18 个产品/启动器构建 + customer package）。
- 装修工程签证与进度款管理助手 job #128952142038：`35 passed in 0.61s`；源码 self-test 输出 `SELF_TEST_OK`；PyInstaller EXE 构建成功；冻结 EXE 自测输出 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`。
- PR 候选客户包 artifact `mainland-phase1-customer-package` ID `13645654774`，外层 ZIP 293,192,633 bytes，SHA256 `498046f1e6c59714027d41dbd530a76a4618f42f8e9f8d62b9a5e8ba4128a38a`；已实际下载，外层 CRC 通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：293,109,846 bytes，SHA256 `1a821aeb886e831bb51eaf296458dbe8421aaaffe541ec212427ab9e33dcf527`；manifest artifact ID `13646177712` 与内层 bytes/SHA256 完全匹配；parts artifact ID `13646172709`，16 个分片重组后的 bytes/SHA256 与内层 ZIP 完全匹配。外层、内层、manifest、parts ZIP CRC 均通过。
- 内层 ZIP 共 41 个条目（39 个文件、2 个目录）：18 个 EXE（17 款业务工具 + 启动器）、18 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。套餐 C 写明全部 17 款业务工具 + 启动器；README 声明 18 款 EXE，数量一致。包内文件时间戳为 2026-11-09 02:49:18 UTC。
- **该包是 PR run #266 的候选包，不是 main push 发布包；不得冒充主线正式发布包。**

### Main / Autonomous Business Engine 检查边界
- PR #19 产品合并提交为 `9774c457786f3f01e4ae9cde9630ed8d49198cf5`；随后 PR #20 产品合并提交为 `1d5b6ab5d98f8df752cb2754d4f319f9f3b6c4a3`。本次检查开始时 main HEAD 为 `1d5b6ab5d98f8df752cb2754d4f319f9f3b6c4a3`，open PR 查询为 0。
- 最近可实际下载核验的 main 客户包仍是 Mainland Windows EXE run #259（[#42440410231](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410231)），artifact ID `13601262927`；该包只有 17 个 EXE，早于 PR #18 的合同履约日志回滚修复及 PR #19、PR #20 两款新产品，因此已过时，不作为当前交付包。
- 最近有完整 job/artifact 记录可复核的 Autonomous Business Engine main run #383（[#42440410278](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410278)）：build/deploy success，`144 passed`；本次 fetch_workflow_run_artifacts 返回空列表，没有可下载的 workflow artifact。日志中业务引擎数据源出现一次 HTTP 502 fallback，但后续步骤、构建和部署均成功。
- 当前 GitHub 连接器可读取 PR-triggered workflow runs、job logs 和 artifacts，但没有列出 repository 最新 workflow runs 的动作；对 merge commit `9774c457...` 和 `1d5b6ab5...` 的 fetch_commit_workflow_runs 与 combined status 均未返回 main push run。因此本记录不猜测 main run 编号，也不把 PR #266 冒充 main run。需要取得并核验 PR #19 合并后最新 main Windows run 的实际 artifact 后，才能更新“主线客户包已验收”。

### 最终销售验收仍未完成
- `src/license.py` 内嵌公钥 SHA256 仍为 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem` SHA256 仍为 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，两者不匹配。
- 不请求、上传、创建、猜测或替换卖家私钥。真实 Windows GUI 业务流程、卖家公钥匹配、真实签发/激活/关闭重启后再次验证均未完成。
- 所有产品继续标记为“待最终验收”；PR 构建通过不等于真实 Windows 用户验收或授权销售验收。

## 2026-11-09 PR #20 物业租金与押金管理助手已合并（PR 候选包通过核验，主线包待独立核验）

### 产品能力与差异化规则
- PR #20（https://github.com/Ldc-12/Chatgpt-business-automatic/pull/20）已于 2026-11-09 squash 合并；产品代码合并提交：1d5b6ab5d98f8df752cb2754d4f319f9f3b6c4a3。
- 新增 apps/物业租金与押金管理助手.py，授权产品 ID：物业租金与押金管理助手；本地数据：%LOCALAPPDATA%\MainlandBusinessTools\rental_ledger.json。
- 租约自动生成月度租金账单；首月/末月按实际占用天数、自然月天数及 Decimal 半入规则折算；缴租日限定 1–28 日，账单编号与租约/账期绑定。
- 收款逐笔关联账单，允许部分收款并阻止累计收款超过应收；押金收取、扣除、退还形成流水，按日期验证历史余额，禁止余额变负。
- 风险规则覆盖逾期/7 日内到期租金、租约 30 日内到期、有效租约已过期、押金不足和退租后押金未结算。生成账单后锁定租约计费条款，避免后续编辑改写历史应收。
- 支持本地 JSON 持久化、四类 CSV 严格导入/导出、全量备份/恢复、原子写入和操作审计；不依赖 VPN、ChatGPT、外部 AI、云端、银行 API 或外部 API。没有自动催缴、滞纳金、租金递增或水电分摊功能，详见说明书。

### PR Windows 构建与候选客户包核验
- PR #20 最终 Mainland Windows EXE run #270：https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42553818450，最终 head ae1cc496508a08640d144f0df5420109ae3967e2；20/20 jobs success（19 个产品/启动器构建 + 1 个客户包任务）。
- 租金押金产品 job #128955034389：44 passed in 0.47s；源码 self-test 成功；PyInstaller EXE 构建成功；冻结 EXE 自测输出 FROZEN_EXE_SELF_TEST_OK: process exited with code 0.
- 首次 PR run #269 的日志显示 3 项测试失败（部分收款测试日期跨过缴租日、租金字段测试 fixture 未使用真实字段名、套餐计数断言仍为 17）；已逐项修正并由 run #270 全量重跑通过。#269 的失败日志已检查。
- PR 候选客户包 artifact mainland-phase1-customer-package ID 13646612125，外层 ZIP 307,996,303 bytes，SHA256 65b8b11ad963fb084ddee81db16002398fc1b0d7d459c0c586986375be11cad2；已实际下载，外层 CRC 通过。
- 内层 Phase1-Mainland-Windows-Tools.zip：307,909,257 bytes，SHA256 622fac16b42934d54a4f29374f4fb8aa9623a3487d4d598ebc552115cb770834；manifest artifact ID 13646612132 声明 bytes 307909257、parts 17、SHA256 与内层完全匹配；parts artifact ID 13646662063 的 17 个分片按序重组后，bytes/SHA256 与内层 ZIP 完全一致。外层、内层、manifest、parts ZIP CRC 均通过。
- 内层 ZIP 共 43 个条目（41 个文件、2 个目录）：19 个 EXE（18 款业务工具 + 启动器）、19 份产品说明书（18 款业务工具 + 启动器）、1 份说明书索引、1 份大陆版 README、1 份套餐说明。README 写明 19 款 EXE，套餐 C 写明全部 18 款业务工具 + 启动器；包内时间戳为 2026-11-09 03:00:22 UTC。
- 该包是 PR run #270 的候选包，不是 main push 发布包；不得冒充主线正式发布包。

### 当前主线发布状态
- PR #20 已合并；open PR 查询为 0。PR #20 merge commit 1d5b6ab5... 的 fetch_commit_workflow_runs 与 combined status 没有返回 main push run。
- 最近仍能实际下载核验的 main 客户包是 run #259 / artifact ID 13601262927，只有 17 个 EXE，早于 PR #18、#19、#20，不能作为当前交付包。PR #270 候选包虽已完整验包，但不替代 main push 包。
- 现有 GitHub 连接器未提供 repository 最新 workflow run 列表动作，不能据此确认 PR #20 合并后最新 main Windows EXE 和 Autonomous Business Engine run 编号；不猜测 run ID、不将 PR artifact 说成 main artifact。取得 main push 最新 run 与 artifact 并完成同样的下载、CRC、manifest/parts SHA256 核验后，才可更新主线包验收状态。

## 2026-11-09 当前主线复核与租约对账单导出改进

### 仓库与工作流复核
- 本轮开始时 main HEAD：`93b4f003abfcdae0dc9c29ffe9926b7ce49522f5`（记录 PR #20 租金押金产品合并与候选包核验）；open PR 查询为 0。
- PR #19 装修工程签证与进度款管理助手已合并，merge commit：`9774c457786f3f01e4ae9cde9630ed8d49198cf5`；PR #20 物业租金与押金管理助手已合并，merge commit：`1d5b6ab5d98f8df752cb2754d4f319f9f3b6c4a3`。
- 当前可读取的最新 Mainland Windows EXE workflow run 为 PR #20 run #270（[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42553818450)，head `ae1cc496508a08640d144f0df5420109ae3967e2`），20/20 jobs success（19 个产品/启动器矩阵任务 + 1 个客户套餐任务）。租金押金 job #128955034389 的回归测试、源码自测、PyInstaller 构建、冻结 EXE 30 秒内退出码 0 均成功；package job #128955378260 成功上传客户包、manifest 和 17 个分片。
- PR #20 的客户包 artifact `mainland-phase1-customer-package` ID `13646612125` 已于本轮重新下载。外层 ZIP 307,996,303 bytes，SHA256 `65b8b11ad963fb084ddee81db16002398fc1b0d7d459c0c586986375be11cad2`；内层 `Phase1-Mainland-Windows-Tools.zip` 307,909,257 bytes，SHA256 `622fac16b42934d54a4f29374f4fb8aa9623a3487d4d598ebc552115cb770834`。外层和内层 CRC 均通过。
- 内层 ZIP 共 43 个条目：19 个 EXE（18 款业务工具 + 工具箱启动器）、19 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。说明书目录有 20 个 Markdown 文件，其中 19 份产品说明书 + 1 份索引。
- **发现套餐说明缺项：**套餐 C 的数量写为 18 款业务工具，但括号列表漏列“物业租金与押金管理助手”。README 和 EXE 数量正确；该缺项已在本轮独立 PR 分支修复，并加入打包回归断言。修复通过 Windows CI 后才可纳入新客户包。
- 本轮开始时 main 已包含 PR #19、#20 产品代码，但 GitHub connector 未提供 repository 最新 push/scheduled workflow runs 列表动作；对 main HEAD 的 commit workflow runs 与 combined status 也未返回 main push run。因此不能确认 PR #20 合并后最新 main push 的 Mainland Windows EXE 或当前最新 ABE scheduled run，不能把 PR #270 候选包冒充 main push 包。

### Autonomous Business Engine 最近可完整复核记录
- 最近可完整读取 job 与日志的 main run #383（[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42440410278)）：build 与 deploy 两个 job 均 success；build 运行全仓 pytest（发布记录记载 144 passed），生成业务目录并上传 Pages artifact。
- build 日志确认上传 `github-pages` artifact ID `13601382380`，47,789 bytes；deploy 日志确认 Pages deployment success。当前 artifact 列表接口返回空数组，故以 job 日志中的上传记录为证。
- #383 运行于 2026-11-08，不能证明它是 2026-11-09 当日最新 scheduled run；由于缺少 run-list 接口，本轮不猜测更新的 run ID。

### 本轮研发 PR：租约对账单导出
- 新增租约级 CSV 对账单：按日期汇总该租约已生成的租金账单、逐笔收款、押金收取/扣除/退还流水及逐笔押金余额，并在文件末尾附租金应收、已收、未收和当前押金余额汇总。
- 对账单只统计已生成账单，不将尚未生成月份虚构为应收；使用 UTF-8 BOM 与原子写入，导出失败保留旧文件。
- 增加应用按钮、中文说明书、租约范围/金额/押金流水/CSV BOM/原子失败回归测试。
- 修复套餐 C 文案漏列租金押金助手的问题，并增加 packaging regression assertion。
- PR #21（[Add lease-scoped rental statement export and fix package catalog](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/21)）已 squash 合并；PR head `6550bb290e1e465b6732fc2b07be74a79a1b798a`，main merge commit `166bd2d8da4372e944c7e9518bc7c958f37b8965`。合并后 open PR 查询为 0。
- PR Windows run #275（[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42609099272)）20/20 jobs success（19 个产品/启动器矩阵 + 1 个客户套餐）；无失败 job。租金押金 job `129132703344`：48 passed，源码 self-test success，标准 PyInstaller EXE 构建 success，冻结 EXE self-test 明确退出码 0；客户包 job `129133339186` success。
- run #275 客户包 artifact `mainland-phase1-customer-package` ID `13669491905`，308,001,414 bytes，外层 SHA256 `4b4431f7f0e04b55138c11647cde1cc647ca4314885f95f421f5eddafdf23b2e`。内层 ZIP 307,914,586 bytes，SHA256 `3890e30c79ec408ebb5b9b8462b4cde84a2455dad39a711a71a551fd946362d2`；外层、内层 CRC 均通过。
- 内层 ZIP 43 个条目：19 个 EXE（18 款业务工具 + 工具箱启动器）、19 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。说明书目录共 20 个 Markdown（19 份产品说明书 + 1 份索引）。套餐 C 说明已列出“物业租金与押金管理助手”；大陆版 README 也列出其独立授权文件名。包内文件时间戳：2026-11-09 11:28:40 UTC。
- Manifest artifact ID `13669556680`；分片 artifact ID `13670290103`，共 17 个分片。下载后按顺序重组的 307,914,586 bytes 与内层 ZIP 字节完全一致，SHA256 与 manifest 一致；manifest 声明的 bytes、sha256、parts 数量全部吻合。
- 该客户包由 PR #21 run #275 构建；合并后已比对产品源码、测试、GUI、说明书、打包工作流与 packaging test 的 Git blob SHA，均与构建分支相同，因此候选包内容与已合并代码一致。但当前 GitHub connector 未返回 main push run 列表；不能把 PR artifact 标称为 main-push artifact，也不能确认合并后的 main push 是否已完成另一轮打包。

### 授权与最终验收
- `src/license.py` 内嵌公钥与 `config/mainland_license_public_key.pem` 仍不匹配；本轮未改动公钥、签名逻辑或卖家密钥。
- 真实卖家公钥匹配、Windows GUI、签发、设备激活及关闭重启后复验仍待完成；所有产品继续标记“待最终验收”，不宣称正式可销售。


## 2026-11-09 PR #22 修复单品 ZIP 缺少中文说明书
### 缺陷证据
- 本轮下载并检查 PR #21 run #275 的租金助手单品 artifact `13669153591`（29,615,916 bytes，SHA256 `d8e4fff4f6b2bccf2ca2001fb56836a80d666639c6ff2ad4b676f5f23b3cf3c5`）。其内层单品 ZIP 只有 EXE 与 README，没有对应中文说明书。
- 复查通用 Windows 工作流发现，所有单品 ZIP 都由同一逻辑仅写入 EXE 与 README，因此这不是单个产品问题，而是全部单品交付包的系统性缺项。完整套餐此前有说明书，但闲鱼单品购买者拿到的 ZIP 缺少说明书。
### 修复与合并
- PR #22（[Include Chinese manual in every standalone Windows product ZIP](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/22)）已 squash 合并；PR head `2370bc0d41075f82cd2c89070065094975c562f0`，main merge commit `9748a5695c38fe969b346c1dd162641c61923a82`。
- 为 19 个 EXE 矩阵项（18 款业务工具 + 工具箱）逐一绑定唯一说明书文件；每个单品 ZIP 现在包含 EXE、README 和 `说明书/<对应产品说明书>`。
- 新增回归测试检查 19 个 manual 路径唯一、文件实际存在，并确认 ZIP 构建步骤把对应说明书写入 `说明书/` 目录。

### Windows 构建与实际 ZIP 核验
- PR Windows run #277（[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42609982620)）：20/20 jobs success（19 个矩阵构建 + 1 个客户套餐任务），无失败 job。租金助手 job #129135612708：49 passed，源码 self-test、PyInstaller EXE、冻结 EXE self-test 均 success；工具箱/打包回归 job #129135612698：29 passed，冻结 EXE self-test success；客户包 job #129136221118 success。
- 租金助手单品 artifact `13669712383`：29,622,472 bytes，SHA256 `8c129226a5f5b326d272c35ebcee993d62ffb3248dd4ecbb3b9c82541909c54c`。实际下载检查外层与内层 ZIP CRC 均通过；内层 `MainlandRentalLedgerAssistant-mainland.zip` 14,804,828 bytes，SHA256 `7ea0d3ea21c498ccef1ce5e4190522cf1c475b16b88212d44799782977e35d07`，文件列表为 EXE、`README-mainland.txt`、`说明书/18-物业租金与押金管理助手-用户说明书.md`。说明书确实已进入单品包。
- run #277 客户包 artifact `mainland-phase1-customer-package` ID `13669622318`，308,006,299 bytes，外层 SHA256 `1cd32eda983f23c8a426144099cff3ce4ff7b8239bfce362f2e4f0dc88cf0638`；内层 ZIP 307,919,391 bytes，SHA256 `e7517b5e953b33edfc206bbdd91cef2894fe59227f2fec57e11c62b974623221`；外层、内层 CRC 均通过。
- 内层 ZIP 43 个条目：19 个 EXE、19 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明。套餐 C 已包含租金押金助手；包内时间戳 2026-11-09 11:35:00 UTC。
- Manifest artifact ID `13668634291`；分片 artifact ID `13670555204`，17 个分片。实际下载后按序重组为 307,919,391 bytes，与内层 ZIP 字节完全相同，SHA256 与 manifest 一致；manifest 的 bytes、SHA256、parts 数量全部吻合。
- 该包由 PR #22 run #277 构建；合并后 main 中的工作流与测试内容和构建分支对应 Git blob SHA 相同，因此候选包包含已合并的单品说明书修复。当前 connector 仍未提供 repository 最新 main push run 列表；本 artifact 仍标记为 PR 候选包，不冒充 main-push artifact。

### 当前状态与遗留阻塞
- PR #22 合并后 open PR 查询为 0；main merge commit `9748a5695c38fe969b346c1dd162641c61923a82`。
- ABE 最近可完整检查的 run 仍为 #383（2026-11-08）；build/deploy success，build 日志记录 144 passed，Pages artifact `13601382380` 上传成功、deploy success。当前无法确认 2026-11-09 当日最新 scheduled run 编号，不猜测 run ID。
- 卖家公钥指纹仍不匹配：内嵌 Ed25519 DER SHA256 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；配置公钥 DER SHA256 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。本轮没有修改任何密钥或签名代码。
- 真实 Windows GUI、可信卖家公钥匹配、签发、设备激活及关闭重启后再次验证仍待最终验收；PR CI 和冻结 EXE 自测不等于真实用户授权验收。

## 2026-11-10 自动复核：main Windows run #278 与 ABE run #399

### 当前主线与工作流
- 本轮开始时 main HEAD：`a677414f7416b63804295bf492adb6514b2525b9`。该提交仅更新 `docs/RELEASE_STATUS.md`；最新包含产品/工作流代码的 Windows main-push 构建仍是前一提交 `9748a5695c38fe969b346c1dd162641c61923a82`。
- 开始时 open PR：0。
- Mainland Windows EXE main-push run #278：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42610524499)，head `9748a5695c38fe969b346c1dd162641c61923a82`，结论 success。19/19 个产品矩阵构建 job 和 1/1 客户套餐 job 全部 success；各矩阵的自动回归测试、源码 self-test、冻结 EXE self-test、单品 ZIP 生成与上传步骤均 success。冻结 EXE 检查是进程自测，不等同于人工逐页 GUI 验收。
- Autonomous Business Engine scheduled run #399：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42711496275)，head `a677414f7416b63804295bf492adb6514b2525b9`，build/deploy 均 success；build 日志记录 `184 passed in 1.47s`，product_factory 与 xianyu_factory 步骤完成。Pages artifact ID `13716276205`，47,779 bytes。
- 最近的历史失败 Mainland run #264 已复核 job log：19 个 EXE build job 均成功，只有 package job 因分片上限 15 × 18 MiB 而失败。后续工作流上限已提高，run #278 package job 成功并产出 17 个分片。run #278 本身无失败 job；run #399 build/deploy 亦无失败 job。

### run #278 客户包实际下载验收
- `mainland-phase1-customer-package` artifact ID：`13670660669`，大小 308,006,470 bytes；创建时间 2026-11-09 11:39:24 UTC；下载后外层 ZIP SHA256：`eba21c6a1604da91c15e539bd8db8ad2cd89edaf945e4139950d3b59346dd050`。
- 外层 ZIP `testzip() = None`，包含内层 `Phase1-Mainland-Windows-Tools.zip`（307,919,710 bytes）及 `README-大陆版.md`（909 bytes）。内层 ZIP SHA256：`702748083dfddd3b097ce0f9adcac8c1d35115cf9a1e61c38f9d679c29cc7ad7`，`testzip() = None`。
- 内层 ZIP 共 43 个条目：19 个 EXE（18 款业务工具 + 工具箱启动器）、20 个 Markdown 文件（19 份产品说明书 + 1 份说明书索引）、1 份大陆版 README、1 份套餐说明及目录项。ZIP 内产品文件时间戳为 2026-11-09 11:39:04 UTC；内层 ZIP 时间戳 11:39:12 UTC。
- Manifest artifact ID：`13669842943`，781 bytes；内容声明 bytes `307919710`、SHA256 `702748083dfddd3b097ce0f9adcac8c1d35115cf9a1e61c38f9d679c29cc7ad7`、parts `17`。三项与实际内层 ZIP 字节数、SHA256 及分片数量一致。分片 artifact ID：`13670750443`，307,922,690 bytes。
- 套餐说明实际内容：A 文件处理三件套 19.9 元；B 办公效率工具箱 29.9 元；C 全部业务工具 + 启动器 39.9 元。上述为仓库建议价，不代表市场成交验证。
- 本包是 run #278、代码提交 `9748a569...` 的真实 main-push 构建产物；main 后续 HEAD `a677414f...` 仅增加发布状态文档，没有改动产品或 Windows 工作流代码。不得将此包说成包含本轮新开发的合同文件识别功能；该功能仍在独立 PR 中等待 Windows CI。

### 本轮继续开发：合同文件批量识别与规则提示
- 分支：`feat/contract-document-intake-review`，从 main HEAD `a677414f...` 独立创建。
- 新增 `src/contract_document_parser.py`：本地读取可搜索 PDF、DOCX、TXT、MD；按明确字段标签提取合同编号/名称、甲乙方、日期和金额；输出包含来源文件、完整度、待补齐字段、规则提示的 UTF-8 BOM CSV 草稿。
- 规则提示检查付款结算、交付验收、违约责任、争议解决、发票、质保/保证金等关键词，并提示缺失字段和日期异常。扫描版 PDF 明确提示暂不支持 OCR；不使用 AI、网络、云服务或外部 API。
- 草稿不会自动写入正式台账；用户必须对照合同原文补齐和复核后，再通过现有 CSV 追加导入。空金额不再默认为 0，必须明确填写金额；无偿合同填写 0。
- 新增 DOCX 读取依赖 `python-docx`，新增文档解析回归测试并纳入合同工具 Windows 矩阵；更新中文说明书和套餐 C 的功能描述。该分支尚未创建/通过 PR Windows CI，不能算作已交付功能。

### 授权与最终验收
- `src/license.py` 内嵌 Ed25519 公钥 DER SHA256：`B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem`：`7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，仍不匹配。本轮未读取、上传、生成、猜测或替换卖家私钥，也未修改两份公钥。
- 真实 Windows GUI/use flow、卖家公钥匹配、真实签发、设备激活及关闭重启后再次验证仍未完成。run #278 的冻结 EXE self-test 只证明自测模式下进程成功退出，不证明真实 GUI 或授权激活通过。
- **当前结论：所有版本继续标记为“待最终验收”，不得宣布可正式上架。**

## 2026-11-10 PR #23 合同文件批量识别：Windows CI 与候选包验收

### PR 与 CI
- PR #23：[Add offline contract document extraction and review drafts](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/23)。产品代码验收提交：`b4cea92fcfc6f74215731114cee96be7be80719a`；分支 `feat/contract-document-intake-review`。
- Mainland Windows EXE PR run #281：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42745612471)，head `b4cea92...`，结论 success。19/19 Windows 产品矩阵 job + 1/1 customer package job 全部 success。
- 合同台账 job `129596911779`：`51 passed in 1.25s`；源码 self-test success；PyInstaller one-file EXE 构建 success；冻结 EXE self-test 在 30 秒限制内退出且退出码 0；单品 ZIP 与 artifact 上传 success。
- 首次 run #279 的测试曾出现 1 fail / 50 pass：金额正则在 `12,345.678` 中错误截取了部分数字。已增加千分位分组与数字边界校验，拒绝截断成 `12.00`；修复后的 run #281 51 项全部通过。run #280 因新提交触发而 cancelled，不作为验收依据。

### 单品 artifact 实际检查
- `mainland-contract-ledger-windows` artifact ID `13731521618`，55,585,657 bytes，SHA256 `23beb60da0cad1ea1b653b51bb897a831b865cb2d0b35b11e8728038d39301fd`。
- artifact 外层 ZIP CRC 通过；内含 `MainlandContractLedgerAssistant.exe`（28,107,958 bytes）及单品 ZIP（27,782,965 bytes）。单品 ZIP SHA256 `3cc79d173f0457eca6a8e8ad1833a78d1d1090a8bf5b39cd7e1b8132007f8800`，CRC 通过，包含 EXE、`README-mainland.txt`、`说明书/16-合同台账与到期提醒助手-用户说明书.md`。说明书已随单品 ZIP 交付。

### PR #23 客户套餐候选 artifact 实际检查
- `mainland-phase1-customer-package` artifact ID `13730768686`，321,772,543 bytes；下载后外层 ZIP CRC 通过，SHA256 `a866535b525c967711161126f078ee579c1834352558b917abb7cebc163ee3f8`。
- 内层 `Phase1-Mainland-Windows-Tools.zip` 321,681,436 bytes，SHA256 `53fc4a44694051fb870ac993015fe77124a54f573788116d27937927f69ed095`；内层 CRC 通过。共 43 个条目：19 个 EXE、20 个 Markdown（19 份产品说明书 + 说明书索引）、大陆版 README、套餐说明和目录项。
- Manifest artifact ID `13730768692`，783 bytes；声明 bytes `321681436`、SHA256 `53fc4a44694051fb870ac993015fe77124a54f573788116d27937927f69ed095`、parts `18`，与实际内层 ZIP 大小和 SHA256 一致。分片 artifact ID `13731013490`，321,684,590 bytes；18 个 18 MiB 分片。
- 客户包内产品条目时间戳为 2026-11-10 02:53:34 UTC，内层 ZIP 时间戳 02:53:40 UTC；客户包 artifact 创建于 02:53:52 UTC，manifest artifact 02:53:53 UTC，分片 artifact 02:53:56 UTC。
- 套餐 C 描述已把合同台账新增的 PDF/DOCX/TXT 批量字段识别与规则提示列为功能；建议价仍为仓库内的 39.9 元，不代表市场成交价。此包是 PR 候选包，尚非 main-push release artifact。

### PR #23 状态与最终验收
- PR #23 的 Windows 构建、测试和候选包结构检查均通过，具备合并条件；合并后仍须等待 main-push Windows run 重新构建，并重新下载检查 main artifact。
- 新功能仍只支持可搜索 PDF/DOCX/TXT/MD；扫描 PDF 不做 OCR；识别草稿必须人工核对后再导入正式台账。
- 卖家公钥指纹仍不匹配，真实 Windows GUI/use flow、卖家公钥匹配、真实签发、设备激活与重启复验仍未完成。**PR CI 成功不等于产品已通过最终上架验收；所有版本继续标记为待最终验收。**

## 2026-11-10 main merge 后发布复验：Windows run #283 / ABE run #401

### 合并与主线
- PR #23（[合同文件批量识别与规则提示](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/23)）已 squash 合并，main merge commit：`189785b828772a90b06ead7f43259a5bf9c1f839`。产品代码验收提交 `b4cea92fcfc6f74215731114cee96be7be80719a` 对应 PR run #281。
- PR #24（[修复发布状态文档项目符号换行](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/24)）已 squash 合并，main HEAD：`a66d32014a5d2cc94cc6c7a342fbcefac64cf32d`。该提交仅修复 `docs/RELEASE_STATUS.md` 的三处历史项目符号换行，没有改动产品代码、测试、工作流或授权配置。
- 当前 open PR：0。main 的产品代码与 Windows 构建 run #283 的 head `189785b...` 一致；其后的 `a66d320...` 是文档修复。

### main Windows 构建
- Mainland Windows EXE main-push run #283：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42746132082)，head `189785b828772a90b06ead7f43259a5bf9c1f839`，结论 success。19/19 产品矩阵 job + 1/1 customer package job，共 20/20 job success。
- 合同台账 job `129598555404`：`51 passed in 1.88s`；源码 self-test、PyInstaller EXE build、冻结 EXE self-test（退出码 0）、单品 ZIP 与上传均 success。
- `mainland-contract-ledger-windows` artifact ID `13731855066`，55,584,629 bytes；对应合同台账 EXE 已进入 main 客户包。

### main 客户包实际下载检查
- `mainland-phase1-customer-package` artifact ID `13731915198`，321,778,330 bytes；创建时间 2026-11-10 02:59:54 UTC。下载后外层 ZIP CRC 通过，SHA256：`ebd067080c52593b6a02fa8db048813eeea6e1a861356b4770d599c590fff31e`。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：321,687,164 bytes；CRC 通过；SHA256：`e9ad039d74f1a4eff90bc9eeca0af5bbf64e189d718f0f40d28ddbb8ffab97c0`。
- 内层共 43 个条目：19 个 EXE（18 款业务工具 + 工具箱启动器）、20 个 Markdown（19 份产品说明书 + 1 份说明书索引）、1 份大陆版 README、1 份套餐说明及目录项。合同说明书 `16-合同台账与到期提醒助手-用户说明书.md` 已在包内，包含本轮 PDF/DOCX/TXT/MD 本地识别和人工复核说明。
- Manifest artifact ID `13731492869`，781 bytes；其 bytes `321687164` 与 SHA256 `e9ad039d...` 与实际内层 ZIP 完全一致；parts `18`。分片 artifact ID `13731328348`，321,690,318 bytes。外层、内层及 manifest ZIP CRC 均通过。
- 内层产品文件时间戳为 2026-11-10 02:59:38 UTC；内层 ZIP 为 02:59:44 UTC；客户包 artifact 02:59:54 UTC；manifest artifact 02:59:55 UTC；分片 artifact 02:59:58 UTC。
- 套餐 A/B/C 说明与当前 19 EXE 结构一致；套餐 C 为全部 18 款业务工具 + 启动器，建议价 39.9 元，并已注明合同工具包含 PDF/DOCX/TXT 批量字段识别和规则提示。该价格是仓库建议价，不是已验证成交价。

### 最新 Autonomous Business Engine
- ABE run #401：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42746302945)，head `a66d32014a5d2cc94cc6c7a342fbcefac64cf32d`，build/deploy 均 success；build 日志记录 `195 passed in 1.92s`，product_factory 生成 12 个产品，xianyu_factory 生成 12 项闲鱼目录。
- Pages artifact ID `13730859426`，47,755 bytes；实际下载 ZIP CRC 通过，内部 tar 共 198 个条目，含 12 个 delivery 页面、12 个产品页面、`mainland/index.html` 与 `xianyu/index.html`。artifact SHA256：`ffff66e0a532be60f08dd7084a3b92f83de017670da997fa2cf8bc6648830634`。
- ABE build 中一次外部数据请求返回 HTTP 502，使用既有 fallback 后仍完成测试、产品目录生成和 Pages 部署；这不是 Windows 离线产品运行依赖。

### 最终上架验收仍未完成
- main Windows 构建与客户包的结构、ZIP CRC、manifest SHA256 已复验；合同批量识别功能已进入 main，PR CI 与 main-push build 均通过。
- **仍未在真实用户 Windows 桌面环境人工完成 GUI/use flow 验收。** CI 的冻结 EXE self-test 是非交互模式，不可替代实际点击、导入合同、核对 CSV、正式导入台账、备份/恢复的手工流程。
- 卖家公钥指纹仍不匹配：`src/license.py` 内嵌 DER SHA256 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem` DER SHA256 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。没有读取、上传、生成、猜测或替换卖家私钥。
- 真实卖家公钥匹配、签发、设备激活、退出并重启后再次验证仍未完成。所有版本继续标记为“待最终验收”，不得宣布已可正式上架。


## 2026-11-10 PR #26 合同离线规则集与 main 发布复验（Windows run #296 / ABE run #404）

### 主线、PR 与 CI
- 本轮开始时 main HEAD：`2fcbbe70056d13d81722b5efca772555a89d2d93`；开始时唯一未完成 PR 为 #26。
- PR #26 [Add evidence-backed offline contract review rules](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/26) 已 squash 合并；合并提交与当前 main HEAD：`d2a52ee3e307813469c0cc475dbfc9eccd2da284`。本轮结束时 open PR：0（后续分类套餐 PR #27 另见下方）。
- 合同规则引擎新增版本 `CN-CONTRACT-2026.11.1`，对明确标注的总金额冲突、付款比例合计、同类日期冲突/期限倒置、保证金返还、违约金计算细节、自动续约通知窗口及条款关键词提供可解释提示；风险明细附规则编号、风险等级、原文行号/摘录和建议复核动作。只生成待人工核对草稿，不自动写入正式台账，不构成法律意见；不调用 AI、OCR、VPN、网络或外部 API。
- 代码复核发现两个跨条款误判风险：合同其他位置的“退还钥匙”或普通“提前30天通知”可能错误满足保证金返还/自动续约通知检查。已将两项检查收窄到各自条款行，并增加回归测试；中文说明书已明确跨段/跨页内容仍需人工核对。
- PR run #294 [Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42807552314) 曾因新增测试夹具把换行写成字面量 `\\n` 而失败（1 failed / 60 passed）；已修正为真实换行。最终 PR run #295 [Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42807951334) 20/20 jobs success；合同台账 job `129801864953` 为 `61 passed in 2.71s`，冻结 EXE self-test 退出码 0，单品 ZIP 上传成功。
- 合并后的 Mainland Windows EXE main-push run #296 [Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42808490114)，head `d2a52ee...`，20/20 jobs success，无失败 job。合同台账 job `129598555404`：`61 passed in 1.61s`；源码 self-test、PyInstaller build、冻结 EXE self-test（退出码 0）、单品 ZIP 上传均 success。
- Autonomous Business Engine main-push run #404 [Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42808490208)，build/deploy 两个 job 均 success；build 日志 `205 passed in 2.41s`；Pages artifact ID `13761620908`，47,764 bytes。

### run #296 最新 main 客户套餐实际下载核验
- `mainland-phase1-customer-package` artifact ID：`13761406186`，artifact 大小 321,775,649 bytes，创建时间 2026-11-10 11:35:44 UTC。实际下载外层 ZIP CRC 通过，包含内层 `Phase1-Mainland-Windows-Tools.zip` 与 `README-大陆版.md`。
- 内层 ZIP：321,684,337 bytes；SHA256 `66804fa9cf01d8b3d9b22ba8fcb09ea0082a7b4447f899ddbc472fd2b03c98a1`；`ZipFile.testzip() = None`。
- 内容核验：19 个 EXE（18 款业务工具 + 1 个启动器）、19 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份套餐说明；共 43 个 ZIP 条目（41 个文件、2 个目录）。本轮产品文件时间戳统一为 2026-11-10 11:35:26 UTC。
- Manifest artifact ID：`13761726039`，782 bytes；声明 bytes `321684337`、SHA256 `66804fa9...`、parts `18`，与实际内层 ZIP 大小及 SHA256 一致。分片 artifact ID：`13761256288`，321,687,491 bytes。
- 当前 main 包的套餐说明仍是原有 A/B/C 通用组合（19.9/29.9/39.9 元建议价）；分类系列 A–E 尚未进入此 main 包，不能把 PR #27 的候选内容描述为已交付。建议售价均未经过实际成交验证。
- 本包来自 main commit `d2a52ee...` 的真实 push 构建，不是历史包或 PR 候选包。

### 后续分类套餐开发
- 新分支 `feat/mainland-category-series-packages`，PR #27 [Package Windows tools into five independent business series](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/27) 已创建，尚待 Windows CI。
- 计划把 18 款业务工具不重复地拆成 A 办公效率（5 款）、B 门店经营（4 款）、C 财务与交易（4 款）、D 合同工程物业（3 款）、E 客户与个人事务（2 款）；F 仍为全部 18 款业务软件 + 工具箱启动器。
- 每个 A–E 分类 ZIP 将包含本系列全部 EXE、每款匹配的中文说明书和系列说明；另作为独立 Actions artifact 发布。完整客户包只额外附分类目录，不重复嵌入五个大 ZIP，避免把主包体积翻倍。
- PR #27 的五类 ZIP 生成、CRC/条目数校验、目录完整性、缺文件拒绝及工作流 artifact 测试尚未通过最终 Windows 构建；在 PR #27 合并和 main-push 构建前，不作为正式分类交付包。

### 授权与最终验收
- `src/license.py` 内嵌公钥与 `config/mainland_license_public_key.pem` 仍为已记录的不同 SHA256 指纹；卖家私钥未在仓库中，也没有确认已安全交付给用户。本轮未读取、上传、猜测、生成或替换任何生产私钥/公钥。
- 代码侧签名、产品 ID、路径和错误授权测试可继续；真实卖家公钥匹配、签发、Windows GUI、设备激活、退出重启后再次验证仍未完成。
- **当前结论：main CI 与冻结 EXE 自测通过，但真实 Windows GUI/授权激活仍待最终验收；不得宣称已通过正式销售验收。**

## 2026-11-10 分类套餐正式合入 main：Windows run #300 / ABE run #406

### PR、main 与 CI
- PR #27 [Package Windows tools into five independent business series](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/27) 已 squash 合并，merge commit：`b24a78a6f524826e40604a3583b4bbd37df5550a`。本轮复核 main HEAD 为该提交；open PR：0。
- PR #27 的 Mainland Windows EXE run #299：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42810056069)，head `34e2ddd28f1dc68ad6dc9fefa13236400c8873bb`，20/20 jobs success（19 个 Windows 构建矩阵 + 1 个客户包 job）。所有 19 个冻结 EXE self-test 均输出 `FROZEN_EXE_SELF_TEST_OK`，退出码 0。
- 失败记录已核对：run #297 的共享打包测试仍按旧标签 `套餐 C` 切分，产生 `IndexError`；run #298 改为 `系列 D` 后，测试又因套餐说明只写“物业租金与押金”简称而未包含完整产品名失败。PR 最终提交把分类说明改为完整产品名，并将测试断言更新为系列 D；run #299 全部通过。没有把失败 run 改写成成功。
- 合并后的 Mainland Windows EXE main-push run #300：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42811688664)，head 与 merge commit `b24a78a...` 一致，20/20 jobs success（19/19 Windows 产品/启动器矩阵 + 1/1 客户包 job）。各产品回归测试、源码 self-test、PyInstaller 构建和冻结 EXE self-test 均通过。
- Autonomous Business Engine main-push run #406：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42811688944)，head `b24a78a...`；build/deploy 均 success，build 日志 `210 passed in 1.63s`，product_factory 生成 12 个产品页；Pages artifact ID `13761899767`，47,773 bytes。外部数据请求曾返回 HTTP 502，工作流使用既有 fallback 后完成；本地 Windows 软件运行不依赖该服务。

### main 客户套餐 artifact 实际下载核验（run #300）
- `mainland-phase1-customer-package` artifact ID：`13763025418`，外层 artifact 321,788,304 bytes，外层 SHA256 `37c587b36084f3b68122f7e28b99f3a4cff033b3f7fcba85e071ce74891983f8`；外层 ZIP CRC 通过，含内层 `Phase1-Mainland-Windows-Tools.zip` 和 `README-大陆版.md`。
- 内层客户 ZIP：321,697,581 bytes，SHA256 `251fbe0ddf903cbaf578c49a3e33d7b42097a917c2618e14f04ce336959996c1`；`ZipFile.testzip() = None`。共 44 个条目（42 个文件、2 个目录）：19 个 EXE（18 款业务工具 + 工具箱启动器）、20 份说明书 Markdown（19 份产品说明书 + 1 份说明书索引）、大陆版 README、分类套餐目录和套餐说明。
- 内层产品文件时间戳：2026-11-10 11:59:28 UTC（中国标准时间 19:59:28）。客户包 artifact 创建于 11:59:47 UTC。
- Manifest artifact ID：`13763005452`，784 bytes；声明 bytes `321697581`、SHA256 `251fbe0d...`、parts `18`，与实际内层 ZIP 完全一致。分片 artifact ID：`13763065205`，321,700,735 bytes；18 个分片重新拼接后为 321,697,581 bytes，SHA256 与 manifest 完全一致。
- 套餐说明现已按 A–F 分类，不再用旧 A/B/C 通用礼包说明。建议售价仍未经过实际闲鱼成交验证。

### A–E 五个分类套餐实际下载核验（main run #300）
- `mainland-phase1-series-packages` artifact ID：`13762129966`，307,099,242 bytes；外层 ZIP CRC 通过，包含五个分类 ZIP 和 `系列套餐目录.md`。
- A 办公效率：5 个 EXE + 5 份匹配说明书；B 门店经营：4 + 4；C 财务与交易：4 + 4；D 合同工程物业：3 + 3；E 客户与个人事务：2 + 2。每个分类 ZIP 另含 `系列说明.txt`，五个 ZIP 的 CRC 均通过。
- 分类内容完整且不重复覆盖 18 款业务软件：A（文件整理、图片、PDF、会议、SOP）；B（库存、采购比价、售后工单、排班）；C（催款、经营收支、报价、报销）；D（合同台账、装修签证进度款、物业租金押金）；E（客户跟进、求职管理）。F 完整套餐保留 18 款业务工具 + 启动器。
- 五个 ZIP 的文件时间戳在 2026-11-10 11:59:02–11:59:16 UTC。分类 artifact 的六个条目均已检查，五个内层 ZIP 均成功解压并通过 CRC。
- 建议价：A/B/C/D 各 29.9 元，E 19.9 元，F 39.9 元；均为待市场验证的建议价，不是已验证成交价。单品仍独立交付，分类 ZIP 与完整套餐来自同一轮 main Windows 构建产物。

### 授权与最终验收
- 本轮未修改授权代码、公钥或任何私钥。当前客户端内嵌公钥指纹仍为 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；配置公钥指纹仍为 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，不匹配。
- 卖家私钥未在仓库；当前不能证明用户电脑上存在 `seller-private.pem`，也不能假定曾安全交付。不得让用户盲目搜索不存在的文件，不得猜测、替换或新造生产私钥。
- CI 冻结 EXE self-test 通过不等于真实 Windows GUI/授权激活通过。卖家密钥来源、公钥匹配、真实签发、设备激活、退出重启后再次验证及逐款 GUI/数据/备份恢复仍待最终验收。**当前全部商品仍标记为待最终验收，不得宣布可正式上架。**

## 2026-11-10 卖家授权私钥来源审计

- 当前 main Git tree 中与授权相关的文件只有：`src/license.py`、`config/mainland_license_public_key.pem`、`tools/issue_license.py`、`tools/export_license_public_key.py`、测试和说明文档；没有卖家私钥 PEM 文件，也没有密钥生成脚本。
- GitHub 代码搜索：`generate_private_key` 在仓库中 0 条命中；`seller-private.pem` 仅出现在说明文档；没有找到生产私钥生成、导出、交付或备份记录。代码搜索不能排除仓库外曾经生成过密钥，但仓库本身无法证明用户持有私钥。
- `tools/issue_license.py` 只读取 `--private-key` 指定的现有文件、派生公钥并签名；不会生成私钥。`tools/export_license_public_key.py` 只从现有私钥导出公钥和指纹；也不会生成私钥。因此不能假定 `seller-private.pem` 曾自动出现在用户电脑。
- 历史公钥变更：2026-09-23 初始客户端提交 `26066f7` 使用 `OYI/...` 公钥；配置公钥初始提交 `b7af0f0` 使用同一值；配置文件随后在 `376ee09` 独立改为 `EAK4...`；客户端又在 `6d1dccb` 独立改为 `aVE...`，并在 `c8f3014` 修正 PEM 算法标识拼写。两次独立修改没有形成当前一致的客户端/配置公钥。
- 以上历史无法证明哪把公钥对应真实卖家私钥，也无法证明任何私钥已安全交付。**不要求用户下载导出脚本、不要求搜索一个未确认存在的文件、不要求上传私钥；不猜测、不替换、不新造生产密钥。**只有在确认存在某个外部保管的真实私钥后，才可让用户在本机导出其公钥/指纹进行只读比对；若确实从未生成私钥，必须先由用户明确决定是否允许另行制定密钥轮换和安全托管方案，当前授权激活继续阻塞。


## 2026-11-11 PR #29：闲鱼售后纠纷证据链助手合并与主线构建 #313 验收

### 代码与功能
- PR [#29 Add offline after-sales dispute evidence-chain assistant](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/29) 已合并。
- 主线合并提交：`040172ce6028e55955d644a3a1d3a755d01d1836`。
- 新增产品：`apps/售后纠纷证据链管理助手.py`，授权产品 ID：`售后纠纷证据链管理助手`。
- 功能包括：售后案件台账、响应截止状态、证据文件本地归档、文件大小/SHA256、追加式哈希事件链、案件字段快照 SHA256、案件范围证据 ZIP、CSV 安全导出、全量备份/恢复。
- 每条事件绑定案件字段快照 SHA256；完整性校验会将最新快照与当前案件记录比对，发现绕过应用直接修改案件字段的情况。案件导出只包含当前案件事件，避免把其他买家/订单事件泄露到单案件包。
- 哈希链不是数字签名或可信时间戳；拥有本地完整写权限的人仍可重写整个数据文件并重新计算哈希。它不证明证据来源、形成时间或法律可采性。软件不登录或抓取闲鱼，不自动申诉，不依赖 VPN、ChatGPT、外部 AI 或云服务。
- 新增中文说明书：`docs/manuals/20-售后纠纷证据链管理助手-用户说明书.md`；已加入工具箱启动器、独立授权路径测试、Windows EXE 矩阵及 B 门店经营系列套餐。

### PR Windows 验证
- PR Windows Actions：[run #312](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42958040720)，head：`d67ead4a20278f4fe05c70ae8a9d7cf520576042`，22/22 jobs success。
- 售后证据工具测试：58 passed；源程序 self-test 输出 `SELF_TEST_OK`；冻结 EXE 自测在 Windows 上退出码 0，并输出 `FROZEN_EXE_SELF_TEST_OK`。
- 独立产品 artifact：`mainland-after-sales-evidence-windows`，ID `13827792273`，29,613,118 bytes；下载后外层 ZIP CRC 通过，SHA256 `1f493227862a8178bf64cff2a498b852f4ffa5a2cef28187a58fbcb65dc8a9b8`。内层单品 ZIP 14,800,256 bytes，SHA256 `1ad040984fd9c51f5969a740b2aa94c53b929753886d0f122e40a24f7b351344`，3 项：EXE、README、对应中文说明书；CRC 通过。
- PR 客户包 artifact：ID `13828615408`；内层 ZIP 351,278,267 bytes，SHA256 `df110e07ff4c82e960d7d8bc05021e7d8c1cdcbfc67ab39a41ce083aa4515b4c`。Manifest artifact ID `13827419654`，声明字节数和 SHA256 与下载内层 ZIP 完全一致。PR 分类套餐 artifact ID `13828410995`；A/B/C/D/E 分别为 5/6/4/3/2 款，5 个内层 ZIP CRC 均通过。以上是 PR 验证产物，不作为主线发布 artifact。

### 合并后的 main Windows EXE 构建与客户包
- Mainline Windows Actions：[run #313](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42958664332)，提交：`040172ce6028e55955d644a3a1d3a755d01d1836`，22/22 jobs success；21 个 Windows 矩阵构建任务与客户套餐任务全部成功，无失败 job。
- 主线售后证据工具：58 passed；源程序自测通过；PyInstaller Windows EXE 构建成功；冻结 EXE self-test 退出码 0。
- 主客户包 artifact：`mainland-phase1-customer-package`，ID `13828008669`，351,377,197 bytes；外层 ZIP CRC 通过，SHA256 `f6ef4c405f10707d06a6c54f11ecdf39fc1e36b3baf08af9d6ebe648a903d804`。
- 已实际下载内层 `Phase1-Mainland-Windows-Tools.zip`：351,278,099 bytes，SHA256 `d3966ab7c5076568e204750c50ca30c12247e3c49b4542591a8b270d52c7d117`；`ZipFile.testzip() = None`。共 48 个条目（46 个文件、2 个目录）：21 个 EXE（20 款业务软件 + 工具箱启动器）、24 个 Markdown 文件、1 份套餐说明 TXT。24 个 Markdown 包括 20 份产品说明书、1 份工具箱说明书、1 份说明书索引、1 份分类套餐目录、1 份大陆版 README。新售后证据 EXE 与 `20-售后纠纷证据链管理助手-用户说明书.md` 均在包内。
- 内层客户 ZIP 所有文件时间戳：2026-11-11 04:23:38 UTC（中国标准时间 12:23:38）；内层 ZIP 条目时间戳 04:23:46 UTC；客户包 artifact 创建时间 04:23:56 UTC（中国标准时间 12:23:56）。
- Manifest artifact ID `13828427035`，783 bytes；声明内层 ZIP `351278099` bytes、SHA256 `d3966ab7c5076568e204750c50ca30c12247e3c49b4542591a8b270d52c7d117`、19 个分片；与实际下载内层 ZIP 字节数和 SHA256 完全一致。
- 分类套餐 artifact：`mainland-phase1-series-packages`，ID `13828276561`，336,691,273 bytes；外层 ZIP CRC 通过，5 个内层 ZIP 均 CRC 通过：A 办公效率 5 款、B 门店经营 6 款、C 财务交易 4 款、D 合同工程物业 3 款、E 客户个人事务 2 款。B 套餐已包含“售后纠纷证据链管理助手”，且附对应说明书和系列说明。
- 售后单品主线 artifact：ID `13827329184`，29,615,913 bytes；外层 ZIP CRC 通过，内层单品 ZIP 14,801,832 bytes，SHA256 `a7a895d9fc3f66ffa51ab98b30cec0c4fc9994c3cb139e563cdcd5ea7f4f5a8d`，含 EXE、README、说明书三项，CRC 通过。

### Autonomous Business Engine
- main ABE Actions：[run #411](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42958664388)，提交同为 `040172ce6028e55955d644a3a1d3a755d01d1836`；build 与 deploy 均 success。
- 自动化引擎测试：252 passed；product_factory 生成 12 个产品；xianyu_factory 生成 12 个闲鱼商品目录条目。
- Pages artifact ID `13827913533`，47,768 bytes；下载后 ZIP CRC 通过，SHA256 `d1024fb51e9a0729d1689ec509957dbf72d47d47706804f104d9a0f433421cc1`；内含 198 个 TAR 条目、12 个 delivery 页面、12 个 Xianyu listing 页面，以及 mainland/xianyu 索引。

### 失败修复记录
- PR 初次 Windows run #307 曾失败：证据篡改测试写入了不同长度文件，先触发大小变化检查而非 SHA256 检查；说明书唯一性断言仍按 20 份而非 21 份计算。已将篡改样本改为相同字节长度，并把唯一说明书数量改为 21。最终 PR run #312 和合并后 main run #313 均通过。
- 旧的主线 run #306 客户包（20 个 EXE、19 款业务软件 + 启动器）已被本节 run #313 的 21 个 EXE 主线包取代；不可将旧包当成最新包。

### 最终验收阻塞仍然存在
- 客户包和 Windows CI 构建通过，不等于真实 Windows GUI 全流程、卖家授权签发、首次激活、退出重启后再次验证已经完成。
- `src/license.py` 内嵌公钥与 `config/mainland_license_public_key.pem` 的 SHA256 指纹仍不一致；本轮没有读取、上传、生成、猜测或替换卖家私钥，也没有修改任何生产公钥。
- 仍须在真实 Windows 电脑完成逐款 GUI、保存/重启、CSV、备份恢复验收；并在确认真实卖家密钥来源后完成公钥匹配、签发、激活和重启复验。**所有商品继续标记为待最终验收，尚未达到闲鱼正式上架标准。**


## 2026-11-11 文档记录提交后的 ABE 最新复核（run #412）

- 文档验收 PR #30 合并后，main 文档提交为 `f4e5df91bbd5c179c10b63a754f8e31a1a8bd215`。该提交只更新发布状态文档，没有改变 Windows 产品代码；因此最新 Mainland Windows EXE 仍是上节 run #313。
- 最新 Autonomous Business Engine Actions：[run #412](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42959480730)，提交：`f4e5df91bbd5c179c10b63a754f8e31a1a8bd215`，build/deploy 均 success。
- ABE 测试仍为 252 passed；product_factory 生成 12 个产品，xianyu_factory 生成 12 个闲鱼商品目录条目。
- 最新 Pages artifact ID `13827823903`，47,773 bytes；下载后 ZIP CRC 通过，SHA256 `ca3f47be81d68d8ff5eef79ec0becf5698a3664b55db79bcfed3adc8d92ca731`；内含 198 个 TAR 条目、12 个 delivery 页面、12 个 Xianyu listing 页面，以及 mainland/xianyu 索引。
- 该 ABE run 不替代 Windows EXE 构建、客户包内容验收或真实 Windows GUI/授权验收。

## 2026-11-11 PR #32：售后证据归档路径 Windows 兼容性加固

- 发现售后纠纷证据链助手的 ZIP 恢复校验原先主要按 POSIX 路径规则判断；某些 POSIX 合法名称（如 CON.txt、NUL、COM1、带冒号/问号/星号的文件名、尾随空格或句点）在 Windows 文件系统中属于设备名或非法路径，可能导致恢复失败或产生非预期文件系统行为。
- PR [#32 Reject Windows-unsafe evidence archive paths](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/32) 已合并；合并提交：86af3aa50fb3d7600c9833deb23280991298cd13。
- 代码修改仅收紧 safe_relative()：拒绝 Windows 保留设备名（含 COM/LPT 数字与上标变体）、控制字符、Windows 禁用字符及尾随空格/句点；正常嵌套相对路径继续允许。
- 新增 2 项回归测试，覆盖 13 种非法路径与正常嵌套路径。独立本地逻辑检查：13/13 非法路径均拒绝，正常路径接受。
- PR Mainland Windows EXE Actions [run #314](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/42969364179)：22/22 jobs success；售后证据产品 job 130353995303：60 passed in 1.27s，源码 self-test SELF_TEST_OK，Windows 冻结 EXE self-test FROZEN_EXE_SELF_TEST_OK，退出码 0；独立售后 EXE artifact ID 13833096162。
- PR 客户包 artifact ID 13832447191；PR 分类套餐 artifact ID 13833105918。这些是 PR 构建候选产物，不作为最新 main 客户交付包。
- 合并后 main HEAD 已更新为上述提交。合并后的 main-push Windows 构建、客户套餐 artifact 与 ABE 运行尚待重新核验；在 main 新构建完成前，最新已核验 main 客户包仍是 run #313（artifact 13828008669），不得用 PR artifact 冒充 main 发布包。
- 本次未修改任何授权公钥、私钥或签发逻辑；真实 Windows GUI/授权激活仍待最终验收。


## 2026-11-11 PR #33 合并、CSV 安全加固与 main run #319 最终验收

### 本轮代码改进
- PR [#33 Prevent spreadsheet formula execution in food batch CSV exports](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/33) 已合并。
- 合并提交：`0a697def3173257bfbda8de8f51b2c1ba585632d`。
- 食品批次助手的“导出批次 CSV”和“导出库存流水”现在都会对去除前导空白后以 `=`、`+`、`-`、`@` 开头的单元格前置英文单引号，避免 Excel/WPS 将商品编码、备注、供应商、去向或原因当作公式执行；本地 JSON 原始数据不变。
- 新增回归测试覆盖批次编号、商品编码/名称、供应商、备注、库存流水去向/原因、前导空白及数量字段；中文说明书已补充实际 CSV 导入字段流程和安全导出说明。
- PR 验证 run #318：22/22 jobs success；食品批次产品 53 passed，源码 self-test 为 `SELF_TEST_OK`，Windows 冻结 EXE self-test 为 `FROZEN_EXE_SELF_TEST_OK`（退出码 0）；客户包 job success。
- 失败迭代没有隐瞒：run #316 的测试夹具把未经规范化的批次编号传给库存调整，触发“找不到所选批次”；修正为读取 store 中规范化后的批次编号。run #317 又把扣减 1 件后的数量误断言为 10，日志实际为 9；已修正断言。最终 run #318 全部通过后才合并。

### 合并后 main Windows EXE 构建
- main HEAD：`0a697def3173257bfbda8de8f51b2c1ba585632d`。
- Mainland Windows EXE Actions run #319：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43013197801)，结论 success，22/22 jobs success（21 个产品/启动器 Windows 构建任务 + 1 个客户套餐任务），无失败 job。
- 食品批次助手 main job：53 passed；源码 self-test 通过；PyInstaller EXE 构建成功；冻结 EXE self-test 退出码 0。单品 artifact `mainland-food-batch-windows` ID `13850229946`，29,596,771 bytes。
- Autonomous Business Engine run #417：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43013197776)，build/deploy 均 success；自动化引擎测试 255 passed；product_factory 生成 12 个产品页面，xianyu_factory 生成 12 个闲鱼商品目录条目；Pages artifact ID `13850459272`，47,783 bytes。

### 最新 main 客户包实际下载与核验（run #319，不是 PR 候选包）
- 客户包 artifact：`mainland-phase1-customer-package`，ID `13851492463`，351,390,188 bytes；外层 SHA256：`8f34d0bd8c473305017235fa8ebbe0fe31a6a79ddc932853dbdb6673a5700e3f`。
- 已实际下载外层 ZIP 并解出内层 `Phase1-Mainland-Windows-Tools.zip`：351,290,633 bytes；SHA256：`60ef8dccb0b43ce1a18ac9d68707b1bebf2ed48421282eddaebbb2de51bffc63`；外层与内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 48 个条目（46 个文件、2 个目录）：21 个 EXE（20 款业务工具 + 工具箱启动器）、21 份对应产品说明书、1 份说明书索引、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明 TXT；文档文件合计 25 份。21 个 EXE 均在包内，包含新增的食品批次与保质期追踪助手、售后纠纷证据链管理助手。
- 内层所有文件时间戳统一为 2026-11-11 19:37:58（中国标准时间）；客户包 artifact 创建时间为 19:38:13。
- Manifest artifact ID `13852150497`，782 bytes；声明内层 ZIP 字节数 `351290633`、SHA256 `60ef8dccb0b43ce1a18ac9d68707b1bebf2ed48421282eddaebbb2de51bffc63`、分片数 19、分片大小 18 MiB；与实际下载的内层 ZIP 完全一致。
- 分类套餐 artifact：`mainland-phase1-series-packages`，ID `13850879976`，336,702,379 bytes；外层 CRC 通过，包含 5 个分类 ZIP 和目录。A 办公效率 5 款、B 门店经营 6 款、C 财务与交易 4 款、D 合同工程物业 3 款、E 客户与个人事务 2 款；逐个下载结构核验，五个内层 ZIP 的 CRC 均通过，每包均含对应数量的 EXE、同数量产品说明书及系列说明。
- 当前套餐说明建议价：A/B/C/D 各 29.9 元，E 19.9 元，F 全系列 39.9 元；均是待市场验证的建议价，不是已验证闲鱼成交价。F 包含 20 款业务工具 + 工具箱启动器。

### 授权与最终验收（状态未改变）
- 本轮没有读取、上传、生成、猜测、替换或轮换任何生产私钥/公钥；卖家私钥不在仓库。
- `src/license.py` 内嵌公钥 SHA256 仍为 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem` SHA256 仍为 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，两者不一致。
- 不假定 `seller-private.pem` 曾自动出现在用户电脑，也不要求用户盲目搜索或上传私钥。若用户确认真实卖家私钥确实存在且由其在可信 Windows 电脑保管，最终只需在本机导出公钥 PEM 或 SHA256 指纹供比对；不得发送私钥。若没有已知的真实私钥，必须先由用户明确决定是否制定密钥轮换/安全托管方案。
- **状态仍为“待最终验收”，不是可正式销售版。** 目前 CI 的源码测试、PyInstaller 构建、冻结 EXE 非交互启动/退出码自测和 ZIP 内容核验均通过；但未完成用户真实 Windows 电脑上的 GUI 全流程、实际卖家密钥匹配、真实签发/激活/重启后再次验证，以及逐款 CSV、数据持久化和备份恢复验收。未完成这些项目之前，不得向用户宣称已达到闲鱼正式上架标准。
- 当前 main 无未完成 PR。


## 2026-11-12 PR：合同人工复核历史与来源指纹（待 Windows CI）

- 独立分支：feat/contract-review-decision-ledger。
- 新增本地人工复核历史：识别草稿记录来源文件 SHA256、规则版本、风险明细 SHA256；用户填写人工结论、复核人和备注后，整批校验并追加到独立复核历史。
- 完全相同的复核内容重复导入会被拒绝；不同结论或备注作为新的复核历史保留。复核 CSV 导出对公式型文本进行转义。
- 合同工作区备份升级为 v3，纳入合同、履约节点、操作记录和人工复核历史；仍兼容 v1/v2 旧备份，恢复旧备份时复核历史清空。
- 新增 src/contract_review.py 与 tests/test_mainland_contract_review.py，覆盖来源/风险指纹、有效复核导入、重复导入拒绝、无效行原子拒绝、篡改风险明细检测、公式安全导出、历史恢复和旧版备份兼容。
- 更新合同助手中文说明书及 Windows EXE 矩阵测试任务。
- 本 PR 尚未获得 Windows Actions 结果；尚未合并、未进入 main 客户包。所有发布继续标记“待最终验收”。
- 本次没有读取、上传、生成、猜测、替换或轮换任何生产密钥。src/license.py 与配置公钥指纹不一致的问题仍独立保留。


## 2026-11-12 自动化复核：主线包验包与 PR #35

### 主线与 PR
- 当前 main HEAD：e04145fd4abeb5251ddb447bf345cad5e3221042。该提交只更新发布状态文档；最近一次 Mainland Windows EXE 构建所验证的源码树为 0a697def3173257bfbda8de8f51b2c1ba585632d。
- 本轮 open PR 查询：PR #35 Add persistent contract review decisions and evidence fingerprints（https://github.com/Ldc-12/Chatgpt-business-automatic/pull/35），分支 feat/contract-review-decision-ledger，尚未合并。
- PR #35 增加合同人工复核历史、来源文件和风险明细 SHA256、人工结论/复核人/备注、重复导入拒绝、v3 组合备份兼容、CSV 公式注入防护。PR Windows CI 尚未取得可核验 run/check 结果，不得合并或视为已交付。

### 已重新下载的 main 客户包（run #319）
- Mainland Windows EXE Actions：run #319（https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43013197801），head SHA 0a697def3173257bfbda8de8f51b2c1ba585632d；当前可访问的 job 列表为 22/22 success（21 个 Windows EXE 构建任务 + 1 个客户包任务），没有失败 job。已检查合同台账 job 日志：72 passed，冻结 EXE 自测 FROZEN_EXE_SELF_TEST_OK，退出码 0。
- 客户包 artifact mainland-phase1-customer-package ID 13851492463，351,390,188 bytes；下载后的外层 ZIP SHA256 8f34d0bd8c473305017235fa8ebbe0fe31a6a79ddc932853dbdb6673a5700e3f，CRC 通过。
- 内层 Phase1-Mainland-Windows-Tools.zip：351,290,633 bytes；SHA256 60ef8dccb0b43ce1a18ac9d68707b1bebf2ed48421282eddaebbb2de51bffc63；ZipFile.testzip() = None。48 个条目（46 文件、2 目录）：21 个 EXE（20 款业务工具 + 工具箱启动器）、21 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明。
- 内层 ZIP 的文件时间戳为 2026-11-11 19:37:58（中国标准时间）；客户包 artifact 创建时间 2026-11-11 19:38:13。
- Manifest artifact ID 13852150497；内容声明 bytes 351290633、SHA256 60ef8dccb0b43ce1a18ac9d68707b1bebf2ed48421282eddaebbb2de51bffc63、parts 19、part size 18MiB；与实际内层 ZIP 大小和 SHA256 完全一致。Manifest ZIP CRC 通过。
- 套餐说明包含 A 办公效率 5 款、B 门店经营 6 款、C 财务与交易 4 款、D 合同工程物业 3 款、E 客户与个人事务 2 款、F 全系列 20 款业务工具 + 工具箱启动器。建议价均为待市场验证价格，不是已验证成交价。

### ABE 与最新 run 查询限制
- 已检查 Autonomous Business Engine run #417（https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43013197776），head SHA 0a697def3173257bfbda8de8f51b2c1ba585632d；build/deploy 2/2 success，日志显示 255 passed，生成 12 个产品页面及 12 个闲鱼目录条目，Pages artifact ID 13850459272。
- GitHub 连接器的 fetch_commit_workflow_runs 仅返回 PR 事件运行，未提供仓库级最新 workflow runs 列表；对 main HEAD e04145f 查询返回空数组。ABE 工作流会在 main push 时运行，因此不能仅凭 run #417 断言它是当前最新 ABE run；本记录只称其为已检查的最近可核验 run，不猜测 run #418 或其他 run ID。run #319 是当前可列出 artifact 并下载核验的 main Windows EXE 构建。
- run #319 和 #417 的 job 列表均无失败项，因此没有失败 job log 可复核；已检查合同构建、客户包上传和 ABE build/deploy 日志。

### 授权与销售状态
- 重新核对的客户端 Ed25519 公钥 DER SHA256：B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741；配置公钥 DER SHA256：7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961，仍不一致。
- 未读取、上传、生成、猜测或替换卖家私钥/生产公钥。所有版本继续标记“待最终验收”；CI 自测不替代真实 Windows GUI 使用、卖家密钥匹配、授权签发、激活和重启后再次验证。


### PR #35 首轮 Windows 失败记录与修正
- PR Mainland Windows EXE run #321（https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43147915634）在合同台账 job 中执行 88 项相关测试：87 passed、1 failed。失败测试为 test_review_csv_export_escapes_spreadsheet_formulas，实际导出值为 "'@SUM(1,1)"，测试却要求保留复核备注前导空格 "'  @"。
- 根因是复核记录规范化阶段会 trim 备注空白；CSV 安全转义功能实际已正确在 @ 前添加单引号。已把测试断言修正为规范化后的真实输出，不改变数据或安全行为。
- run #321 其余部分因后续分支更新而出现 cancelled/in-progress，未形成完整 Windows 矩阵与客户包验收；不得把它标为成功。修正后的新一轮完整 PR 构建仍待验证。


## 2026-11-12 PR #35 合并及 main run #324 客户包复核

### PR #35 与失败修正
- PR [#35 Add persistent contract review decisions and evidence fingerprints](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/35) 已于 2026-11-12 03:40:05 UTC squash 合并；合并提交/main HEAD：`a143eff9300bd0c72462dda970f1210782381806`。
- PR Windows run #323：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43148141662)，22/22 jobs success；合同台账及相关测试 `88 passed`；冻结 EXE 自测 `FROZEN_EXE_SELF_TEST_OK`，退出码 0；客户包 job success。
- 失败记录保留：PR run #321 的合同测试 job #130949987889 曾出现 1 failed / 87 passed，失败是测试错误地要求保留规范化时会去除的备注前导空格；已检查原始日志并修正断言。run #321 其余部分因分支更新取消，不能算成功；run #323 是完整通过的验证。
- PR 候选客户包 artifact ID `13912818159`（351,393,253 bytes），已下载核验：外层 ZIP CRC 通过；内层 ZIP 351,293,772 bytes、SHA256 `688304e418c2e64a9adad32f2e56dd209fc5c6b6e6cf88351224603fcb8badcb`、CRC 通过，包含 21 个 EXE、21 份产品说明书及套餐文档。Manifest artifact ID `13912388916`，其字节数与 SHA256 与内层 ZIP 一致。该 PR artifact 只作为合并前候选验证，不代替 main artifact。

### 合并后 main Windows EXE run #324
- Mainland Windows EXE run #324：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43149731508)，head `a143eff9300bd0c72462dda970f1210782381806`，22/22 jobs success（21 个 EXE build jobs + 1 个客户包 job），无失败 job。
- 合同台账 job #130955816725：`88 passed in 1.93s`；冻结 EXE 自测日志出现 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`。其他 20 个产品/启动器 build jobs 和客户包 job 均 success。
- main 客户包 artifact `mainland-phase1-customer-package` ID `13913905235`，351,397,703 bytes；下载后的外层 ZIP SHA256 `058e0dad93adb69ee5b20bd9539a6e5d6283585572503d65cc133288164361f9`，CRC 通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：351,298,434 bytes；SHA256 `ce9f357dbf29f378a148131d3f4d4e03699b58dcc4ab13990323ddf655554cbf`；`ZipFile.testzip() = None`。48 个条目：21 个 EXE（20 款业务工具 + 工具箱启动器）、21 份产品说明书、1 份说明书索引、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明 TXT。内层所有文件时间戳为 2026-11-12 11:42:18（中国标准时间）。
- Manifest artifact ID `13912769702`，784 bytes；声明内层 ZIP bytes `351298434`、SHA256 `ce9f357dbf29f378a148131d3f4d4e03699b58dcc4ab13990323ddf655554cbf`、parts `19`、part size `18MiB`；与实际下载内层 ZIP 完全一致，manifest ZIP CRC 通过。
- 分类套餐 artifact ID `13913047921`，336,712,197 bytes，外层 CRC 通过；包含 A–E 五个分类 ZIP 和目录。五个分类 ZIP 的 CRC 均通过，分别包含 A 5 EXE/5 说明书、B 6/6、C 4/4、D 3/3、E 2/2。分类建议售价仍仅是待市场验证的定价，不是已验证闲鱼成交价。

### Autonomous Business Engine run #420
- ABE run #420：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43149731535)，head 同为 `a143eff9300bd0c72462dda970f1210782381806`，build/deploy 2/2 success；测试 `271 passed`。
- product_factory 生成 12 个 live-checkout 产品页，xianyu_factory 生成 12 个闲鱼目录条目；Pages artifact ID `13913356649`，47,758 bytes，已下载并检查 ZIP CRC。Pages TAR 内有 17 个产品页面/产品 JSON、12 个交付页和 12 个闲鱼商品目录条目。
- ABE 构建日志中一次实时 API 请求返回 HTTP 502，系统按既有 fallback 继续完成构建并部署成功；此 run 的成功不代表该次外部 API 请求成功。

### 当前发布状态
- PR #35 已合并；main 的 Windows EXE 构建和客户包、manifest、分类 ZIP 均已完成下载与内容核验。
- **仍为“待最终验收”，不能宣布正式上架。** CI 冻结 EXE 非交互启动/退出码自测不等同于用户真实 Windows 桌面 GUI 全流程验收。卖家公钥指纹不一致问题仍未解决：`src/license.py` 内嵌公钥 DER SHA256 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`，配置文件 DER SHA256 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。没有读取、上传、生成、猜测、替换或轮换任何生产私钥/公钥；真实卖家密钥匹配、Windows 授权签发/激活/退出重启后再次验证，以及逐款真实 GUI/数据流程验收仍未完成。
- 后续功能分支 `feat/contract-review-version-diff` 正在增加同一合同、同一规则版本下的风险命中版本对比；该分支尚未建立 PR，尚未通过 Mainland Windows EXE 矩阵，不属于当前 main 客户包。

## 2026-11-12 main run #327 最新客户包复核与本轮自动化记录

### 当前 main 与开放 PR
- main HEAD：`73e1b5485eab5eb70790e10370d41775a62af3ec`，提交时间 2026-11-12 11:59:22（UTC），提交内容为合同复核版本间风险变化对比；本次检查开放 PR 为 0。
- Mainland Windows EXE run #327：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43151795927)，head 与 main HEAD 一致，22/22 jobs success（21 个 Windows 产品/启动器构建 + 1 个客户套餐 job），无失败 job。
- 合同台账 job #130962475038：`94 passed in 2.21s`；冻结 EXE 日志含 `FROZEN_EXE_SELF_TEST_OK: process exited with code 0.`。本次矩阵的 purchase-compare、food-batch 等产品 job 的自动回归测试、源码自测、EXE 构建和冻结 EXE 自测均 success。
- 近期失败记录：run #320（job #130948750253）及 run #321（job #130949987889）的合同台账测试因断言错误失败。日志实际输出复核备注规范化后的 `'@SUM(1,1)`，旧测试却要求保留已被 normalize 去除的前导空格 `'  @`；这是测试预期错误，不是 CSV 公式转义失效。修正后的 PR #35 run #323、main run #324 及本次 run #327 均通过。run #321 其余 jobs 因分支更新取消，不将其记为成功。

### 最新 main 客户包（run #327，已实际下载核验）
- 客户包 artifact `mainland-phase1-customer-package` ID：`13914635619`，外层 artifact ZIP 351,395,008 bytes，SHA256 `99b0e3add2af1140cad709e5ee230175e8d1757086672df894676950e6b5f33f`。
- 已下载外层 ZIP 并解出内层 `Phase1-Mainland-Windows-Tools.zip`：351,296,009 bytes，SHA256 `f8e8bed56ccda9fde43fba27c1e5569164f6dbe174d53b2f339d79627b81b066`；外层与内层 `ZipFile.testzip() = None`。
- 内层 ZIP 共 48 个条目（46 个文件、2 个目录）：21 个 EXE（20 款业务软件 + 1 个工具箱启动器）、21 份逐款中文产品说明书、1 份说明书索引 README、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明 TXT。所有内层文件时间戳为 2026-11-12 12:01:46（中国标准时间）。
- Manifest artifact ID：`13914745235`，783 bytes；声明内层 ZIP 字节数 351,296,009、SHA256 `f8e8bed56ccda9fde43fba27c1e5569164f6dbe174d53b2f339d79627b81b066`、分片数 19、分片大小 18 MiB；与实际下载文件的字节数及 SHA256 完全一致。
- 分类套餐 artifact ID：`13914735179`，336,707,621 bytes，ZIP CRC 通过；包含 A–E 五个分类 ZIP 和目录。系列分别为办公效率 5 款、门店经营 6 款、财务与交易 4 款、合同工程物业 3 款、客户与个人事务 2 款。建议售价仍只是待市场验证价格。
- 最新客户包的实际下载、文件清单、EXE 数量、逐款说明书数量、套餐说明、manifest 和时间戳均已核验；不以历史 artifact 替代本次 main 包。

### Autonomous Business Engine
- 最新 scheduled run #422：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43173738158)，head SHA 与 main HEAD 一致，build/deploy 2/2 success。
- build job #131032897008：`277 passed in 2.17s`；product_factory 与 xianyu_factory 均执行成功。deploy job #131033085941 success。
- Pages artifact ID：`13923630831`，47,761 bytes，已下载；ZIP CRC 通过，内部 tar 包含 198 个条目。该引擎产物与大陆 Windows EXE 客户包是不同交付物，不可混为一谈。

### 本轮新增的待验证 PR
- PR #37：[Make contract backup exports atomic and failure-safe](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/37)，分支 `fix/atomic-contract-backup-20261112`，head `c3e579ae5ce20ca673bad200f486bd4229c5f1d8`，尚未合并。
- 改动：合同工作区 JSON 备份改为同目录临时文件写入、flush/fsync 后原子替换；失败时保留旧备份并清理临时文件；自动创建不存在的目标目录；新增两项回归测试并更新中文说明书。必须等 PR #37 的完整 Windows 矩阵、冻结 EXE 自测及客户包 job 全部通过后才可合并。

### 授权与最终验收
- 客户包仍标记为“待最终验收”，不是已完成真实 Windows 授权激活的正式销售包。
- 客户端内嵌公钥 DER SHA256：`B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；配置公钥 DER SHA256：`7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，仍不一致。
- 未读取、上传、生成、猜测、替换或轮换生产私钥/公钥。真实卖家密钥匹配、真实 Windows 签发/激活/退出后重启复验和逐款 GUI/数据流程验收仍未完成。


## 2026-11-12 main run #329 最新客户包核验与合同 CSV 导出加固计划

### 主线、PR 与 Windows / ABE 工作流
- run #329 验证时 main HEAD 为 `009a10866f4ebafdac85b3c4054569da7f586e0b`（PR #37 合并提交）；之后发布记录文档提交为 `96c3d636159d399b87d98173d709e26bc7db2b09`，PR #39 合并后当前 main HEAD 为 `c6fbf73e3d5652a349a9e243f9088be8a7f2b82d`；当前 open PR：0。
- PR [#37 Make contract backup exports atomic and failure-safe](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/37) 已合并，merge commit 为 `009a10866f4ebafdac85b3c4054569da7f586e0b`。改动为合同工作区备份先写同目录临时文件、flush/fsync 后原子替换，替换失败保留旧备份并清理临时文件；自动创建目标目录；新增失败回归与嵌套目录回归，并更新中文说明书。
- PR #37 的 Mainland Windows EXE run #328：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43207387705)，完整矩阵及客户包 job 均成功；合并后的 main Mainland Windows EXE run #329：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43208567963)，22/22 jobs success（21 个产品/启动器 Windows 构建 + 1 个客户包任务），无失败 job。
- main run #329 合同台账 job #131149912057：合同台账、合同文件解析、人工复核、风险版本对比、授权和套餐相关测试 `96 passed in 2.94s`；冻结 EXE 日志出现 `FROZEN_EXE_SELF_TEST_OK`，进程退出码 0。客户包上传 job #131150980460 成功。
- Autonomous Business Engine run #424：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43208567925)，build/deploy 2/2 success；build job #131149911317 的测试为 `279 passed in 2.40s`；日志明确显示 product_factory 生成 12 个 Stripe checkout 产品页面、xianyu_factory 生成 12 个闲鱼目录条目。Pages artifact ID `13938573628`，47,803 bytes；下载后 ZIP CRC 通过，内部 TAR 共 198 个条目。
- 近期失败日志复核：Windows run #320 的合同台账 job #130948750253 曾为 1 failed / 86 passed。唯一失败是测试断言要求复核备注保留 normalize 已去除的前导空格（期望 `'  @`，实际安全导出为 `'@SUM(1,1)`）；这是测试预期错误，已修正，后续 PR #35 run #323、main run #324、#327、#329 均通过。run #320 的客户包 job 因该测试失败而 skipped；不把该 run 记为成功，也没有把旧失败包当作交付包。
- 本轮没有失败的最新 main #329 或 ABE #424 job；其余 job 均为 success，因此没有需要重跑的失败 job。

### 最新 main 客户包（run #329，已实际下载与核验）
- Artifact：`mainland-phase1-customer-package`，ID `13940062530`，351,403,678 bytes；外层 ZIP SHA256 `0c4abc9e372fbd7a32eae9573db57acb3eb3855cd0bcd292cd46d17386798ac8`，`ZipFile.testzip() = None`。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：351,304,242 bytes；SHA256 `7e71ac5c258ac2e5ce50e6d2374da7d4ba562deabd30efdd36502bef1b4bfc87`；内层 ZIP CRC 通过。
- 内层 ZIP 共 48 个条目（46 个文件、2 个目录）：21 个 EXE（20 款业务工具 + 1 个启动器）、21 份逐款中文说明书，另有说明书索引、分类套餐目录、套餐说明 TXT 和大陆版 README。内层文件时间戳为 2026-11-12 11:25:00 UTC（北京时间 19:25:00）；artifact 创建时间 11:25:16 UTC（北京时间 19:25:16）。
- Manifest artifact `mainland-phase1-package-manifest` ID `13939862606`，781 bytes；声明内层 ZIP 为 351,304,242 bytes、SHA256 `7e71ac5c258ac2e5ce50e6d2374da7d4ba562deabd30efdd36502bef1b4bfc87`、19 个分片、每片 18 MiB；与实际下载内层 ZIP 的字节数和 SHA256 完全一致。Manifest ZIP CRC 通过。
- 分类套餐 artifact `mainland-phase1-series-packages` ID `13940552095`，336,716,198 bytes；外层 ZIP CRC 通过，含 A–E 五个分类 ZIP 和目录。逐包 CRC 均通过：A 办公效率 5 EXE/5 份说明书；B 门店经营 6/6；C 财务与交易 4/4；D 合同工程物业 3/3；E 客户与个人事务 2/2。建议价格仍为待市场验证价格，不是实际成交数据。
- 客户包、manifest、分类套餐均为 run #329 当前 main 产物，已真实下载检查；没有使用 run #319 或其他历史包替代最新包。

### PR #39 合同 CSV 导出原子写入（已合并）
- PR [#39 Make contract CSV exports atomic and failure-safe](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/39) 已于 2026-11-12 合并；merge commit `c6fbf73e3d5652a349a9e243f9088be8a7f2b82d`。
- 合同 CSV 现在先在内存完整生成，保留 UTF-8 BOM 与公式型文本安全前缀，再通过同目录临时文件、flush/fsync 和原子替换写出。写入或替换失败时原 CSV 保留，临时文件清理。
- 新增两项回归：模拟替换失败时原 CSV 不变且无残留临时文件；成功导出包含 BOM 且 `=1+1` 变为安全文本 `'=1+1`。中文说明书同步更新。
- PR #39 的最终 Mainland Windows EXE run #331：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43212640842)，22/22 jobs success；合同台账 job #131164070219 为 `98 passed in 2.23s`，冻结 EXE 自测 `FROZEN_EXE_SELF_TEST_OK`，退出码 0。候选包 artifact ID `13942132291` 已下载核验：21 EXE、21 份逐款说明书、48 个条目，CRC 通过；manifest artifact ID `13942521798` 与候选包 SHA256/字节数一致。
- PR #39 首轮 run #330 的合同台账 job #131163457590 出现 1 failed / 97 passed；失败是新增测试把 BOM 断言写成了反斜杠文本，导致误判。已改为直接检查字节 `EF BB BF`，最终 run #331 22/22 通过后才合并。run #330 其余 job 被新提交取消，不记为成功。
- 当前代码改动已进入 main，不能再把 PR #39 标记为待合并。

### 授权与销售验收（仍未解除）
- `src/license.py` 内嵌 Ed25519 公钥 DER SHA256：`B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；`config/mainland_license_public_key.pem` DER SHA256：`7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，仍不一致。
- 本轮没有读取、上传、生成、猜测、替换或轮换任何生产私钥/公钥；卖家私钥仍不在仓库。授权代码侧路径、产品 ID 和签名验证可继续测试，但生产密钥不得臆造。
- **客户包仍标记“待最终验收”，不是可正式销售版。** 尚未完成可信 Windows 设备上的卖家公钥匹配、真实授权签发/激活、退出重启后复验，以及逐款 GUI 和数据流程验收。最终只需用户在可信 Windows 电脑本地导出公钥 PEM 或 SHA256 指纹供比对，绝不需要私钥。


## 2026-11-12 PR #39 合并后 main run #332 最新客户包核验

### 主线与 Windows EXE
- 当前 main HEAD：`c6fbf73e3d5652a349a9e243f9088be8a7f2b82d`；当前 open PR：0。
- Mainland Windows EXE run #332：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43213307901)，head SHA 与 main 一致，22/22 jobs success（21 个 Windows 产品/启动器构建 + 1 个客户包 job），无失败 job。
- 合同台账 job #131166127483：`98 passed in 2.32s`；冻结 EXE 自测 `FROZEN_EXE_SELF_TEST_OK`，退出码 0。CSV 导出原子写入回归已包含在这 98 项测试中。
- PR #39 run #331 与合并后 main run #332 均完整通过。main run #332 是本记录当前最新正式客户包来源。

### 最新 main 客户包（run #332，已实际下载与核验）
- Artifact `mainland-phase1-customer-package` ID `13942960955`，351,393,535 bytes；外层 ZIP SHA256 `588341643bdca9b17c8d7e13019023e15cd0f0d899f688505e351659afb2d381`，`ZipFile.testzip() = None`。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：351,294,521 bytes；SHA256 `9edf07de814526df45ffb6ebdf71eba6652e98ab6c18f50e70b7326accac4e93`；内层 ZIP CRC 通过。
- 内层 ZIP 48 个条目（46 个文件、2 个目录）：21 个 EXE（20 款业务工具 + 工具箱启动器）、21 份逐款中文说明书、1 份说明书索引、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明 TXT。内层文件时间戳为 2026-11-12 11:58:24 UTC（北京时间 19:58:24）；artifact 创建时间 11:58:48 UTC（北京时间 19:58:48）。
- Manifest artifact ID `13942831110`，784 bytes；声明内层 ZIP 为 351,294,521 bytes、SHA256 `9edf07de814526df45ffb6ebdf71eba6652e98ab6c18f50e70b7326accac4e93`、19 个分片、每片 18 MiB；与实际下载文件的字节数和 SHA256 完全一致，manifest ZIP CRC 通过。
- 分类套餐 artifact `mainland-phase1-series-packages` ID `13941693873`，336,707,514 bytes；外层 CRC 通过，五个分类 ZIP 均 CRC 通过并逐一检查：A 办公效率 5 EXE/5 说明书；B 门店经营 6/6；C 财务与交易 4/4；D 合同工程物业 3/3；E 客户与个人事务 2/2。套餐说明中的建议价 A–D 各 29.9 元、E 19.9 元、F 全系列 39.9 元，明确注明“待市场验证”，不是实际成交数据。

### 最新 Autonomous Business Engine
- ABE run #426：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43213307783)，build/deploy 2/2 success；build job #131166125929 测试 `281 passed in 2.28s`，生成 12 个 Stripe checkout 产品页面和 12 个闲鱼目录条目。
- Pages artifact ID `13941723312`，47,768 bytes；已下载核验，外层 ZIP CRC 通过，内部 TAR 198 个条目，其中 17 个 product.json、12 个闲鱼 listing.txt、12 个交付页面。
- ABE 构建日志有一次实时外部 API HTTP 502，按现有 fallback 继续完成构建和部署；因此 workflow success 不代表该次外部 API 请求成功。ABE run #425（前一轮文档提交触发）也为 2/2 success、279 passed，并出现相同 fallback 记录。

### 当前授权与销售状态
- 生产公钥不一致问题未改变：客户端内嵌公钥 DER SHA256 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；配置公钥 DER SHA256 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。
- 未读取、上传、生成、猜测、替换或轮换生产私钥/公钥。客户包仍为 **待最终验收**，不是可正式销售版；真实 Windows GUI、卖家公钥匹配、签发/激活和退出重启后复验尚未完成。

## 2026-11-13 PR #40 合并与 main run #350 客户包核验

### 主线、PR 与失败记录
- PR [#40 Add offline food safety inspection and corrective-action closure assistant](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/40) 已合并，squash merge commit：`2b5a8e85c6eaf858184029e55e1c6fa67e381633`。合并后 main HEAD 与该提交一致；当前 open PR：0。
- PR #40 最新候选 head：`f43fb02da9544c62a9023485a10eaa417f513204`；Mainland Windows EXE run #349：[Actions](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43362609854)，23/23 jobs success（22 个产品/启动器 Windows 构建 + 1 个客户包任务）。门店食品安全巡检 job #131681124695：`73 passed`，源码自测 `SELF_TEST_OK`，冻结 EXE 自测 `FROZEN_EXE_SELF_TEST_OK`，退出码 0；客户包预上传检查和上传后重新下载复检均通过。
- PR #40 早期 run #342 中多个产品 job 因同一个共享测试夹具错误失败。失败日志定位到 `tests/test_mainland_package_inspection.py:48`：断言引用未定义变量 `include_series`，报 `NameError`；食品安全 job 为 1 failed / 67 passed，文件整理 job 为 1 failed / 50 passed。修正测试后，run #349 完整通过才合并。run #341 没有生成 job；run #347/#348 是分支更新后取消的旧矩阵，不计为通过。
- PR #40 新增离线“门店食品安全巡检与整改闭环助手”：17 项版本化清单、风险加权内部管理分、同门店同规则 90 天重复问题识别、责任人/整改期限约束、整改复查闭环、哈希链审计、多门店风险报表、CSV 导入导出、原子写入和备份恢复；新增独立中文说明书、启动器入口、授权路径测试及 ZIP 预上传检查器。它不依赖 VPN、ChatGPT 或外部 AI；清单及分数仅供内部管理，不是监管合规结论。
- PR #40 候选 artifact ID `14009157370` 曾下载核验，但它是 PR 候选包，不作为 main 当前交付来源。合并后的 main 客户包以下以 run #350 为唯一当前来源。

### 合并后 main Mainland Windows EXE run #350
- [Mainland Windows EXE run #350](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43415683885)，head SHA `2b5a8e85c6eaf858184029e55e1c6fa67e381633`，23/23 jobs success（22 个产品/启动器构建 + 1 个客户交付包任务），无失败 job。
- 食品安全巡检 job #131852856512：`73 passed in 1.63s`；源码自测 `SELF_TEST_OK`；冻结 EXE 自测 `FROZEN_EXE_SELF_TEST_OK`，退出码 0。其 Windows 独立 EXE artifact ID `14030818767`。
- 客户包 job #131853769287：分类套餐构建、客户 ZIP 检查、上传、重新下载、复检、分片和 manifest 生成均 success。日志两次出现 `MAINLAND_PACKAGE_INSPECTION_OK`，上传后重下载复检得到相同的内层 SHA256。
- 最新 main 客户包 artifact `mainland-phase1-customer-package` ID `14031796993`，366,196,186 bytes；外层 ZIP SHA256 `911aa3f4504ede772d8a30cf89b65d0188af521f07b9ba8f82934e221b81960a`，CRC 通过。
- 内层 `Phase1-Mainland-Windows-Tools.zip`：366,091,032 bytes；SHA256 `a8fd43c910b8f618f242f0cd55a542c630dcd4411c582873bbd92c14ac5ef629`；ZIP CRC 通过。
- 内层共 50 个条目（48 个文件、2 个目录）：22 个 EXE（21 款业务软件 + 工具箱启动器）、22 份逐款中文说明书、1 份说明书索引、1 份大陆版 README、1 份分类套餐目录、1 份套餐说明 TXT、1 份客户包 inspection JSON。全部内层文件时间戳为 2026-11-13 11:18:42 UTC（北京时间 19:18:42）；artifact 创建时间 11:19:00 UTC（北京时间 19:19:00）。
- inspection JSON 确认 EXE=22、manual=22、entry_count=50、CRC passed；包含 A–F 六个套餐说明，价格均标注为待市场验证建议价。F 为 21 款业务软件 + 启动器的完整客户包，不是额外第六个分类 ZIP。
- Manifest artifact ID `14031348882`，2,567 bytes；声明内层 ZIP 为 366,091,032 bytes、SHA256 `a8fd43c910b8f618f242f0cd55a542c630dcd4411c582873bbd92c14ac5ef629`、20 个分片、每片 18 MiB；与下载内层包字节数及 SHA256 完全一致。Manifest ZIP CRC 通过。
- 分类套餐 artifact ID `14032355108`，351,512,109 bytes；外层 ZIP CRC 通过。五个分类 ZIP 均单独解压核验且 CRC 通过：A 办公效率 5 EXE/5 说明书；B 门店经营 7/7；C 财务与交易 4/4；D 合同工程物业 3/3；E 客户与个人事务 2/2。分类目录和套餐说明均包含新增食品安全巡检工具；F 完整包包含全部 21 款业务工具和启动器。
- 客户包、manifest、分类套餐均为合并后 main run #350 的真实 artifact，已下载、核对 ZIP 文件列表、CRC、EXE/说明书数量、套餐说明、文件时间戳和 SHA256；未使用 PR 候选包或历史包替代。

### 合并后 Autonomous Business Engine run #430
- [ABE run #430](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/43415683925)，head SHA 与 main 一致，build/deploy 2/2 success。
- build job #131852855648：`317 passed in 2.43s`；Pages artifact ID `14031985656`，47,764 bytes；已下载核验，外层 ZIP CRC 通过，内部 TAR 198 个条目，包含 17 个 product.json 和 12 个闲鱼 listing.txt。
- 本轮机会数据实时请求返回 HTTP 502，日志明确为 `fallback: HTTPError`，引擎使用已有 fallback 数据完成后续产品页构建和部署；因此 ABE workflow success 不代表实时 API 请求成功。deploy job #131853002289 已报告 Pages deployment success。

### 授权与销售验收
- 客户端内嵌 Ed25519 公钥 DER SHA256 仍为 `B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`；配置公钥 DER SHA256 仍为 `7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`，两者不一致。
- 本轮没有读取、上传、生成、猜测、替换或轮换任何生产私钥/公钥。卖家私钥不在仓库。
- **最新 main 客户包仍为“待最终验收”，不是可正式销售版。** CI 的冻结 EXE 自测不等同于用户真实 Windows GUI、真实授权签发/激活和退出重启后复验。还需在可信 Windows 电脑用本机原有卖家私钥导出公钥 PEM 或 SHA256 指纹供比对；只需要公钥或指纹，绝不上传私钥。

