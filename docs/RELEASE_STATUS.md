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

- main 发布代码提交：`ffb6fb33ae0e89116aaf57ec650742f39fe7b16e`（PR #16 merge commit）；其后仅有本发布状态文档提交 `5a16f61f88d93f2979298ecc56a1b402f9eea0f9`，未改变产品代码；未完成 PR：0。
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
