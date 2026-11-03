# 第一批大陆版发布状态

## 最近一次可复现构建（2026-11-03 20:46，中国标准时间）

- 主分支构建提交：`58016ae270f00dc9a488d5edfc5fbd81393395f9`（PR #9 合并提交）。
- 授权防错 PR：[#9 Guard license issuance with embedded-key match and add public-key export](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/9)，已合并。
- Mainland Windows EXE Actions：[#151](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41638303845)，结论：`success`。
- 10/10 个 Windows 矩阵任务全部成功：自动回归测试、源码自测、PyInstaller EXE 构建、首次启动冒烟检查、UTF-8 中文 README 和单品 ZIP 均通过。
- 总套餐打包 job：成功；Autonomous Business Engine：[#346](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41638303726)，build/deploy 均成功。
- 客户套餐 artifact：`mainland-phase1-customer-package`，ID：`13231977373`，artifact 大小：129,594,654 bytes。
- 下载后外层 artifact ZIP 包含最终客户 ZIP 和大陆版 README；内层客户 ZIP：129,558,555 bytes。
- 内层客户 ZIP SHA256：`1e2f23fe687cb63ce33a18641e61eaf8b155a08f0ed2a2b30ec54c8e3821075c`；与 manifest artifact `13232056237` 中的 SHA256、字节数完全一致。
- ZIP 完整性检查：通过（`ZipFile.testzip() = None`）。内容为 10 个 EXE、10 份产品用户说明书、1 份说明书索引 README、1 份大陆版 README、1 份套餐说明 TXT；共 25 个条目（23 个文件、2 个目录）。
- 分片清单 artifact：`mainland-phase1-package-manifest`，ID：`13232056237`；7 个 20 MiB 分片 artifact 均上传成功。
- 客户 ZIP 内文件时间戳：2026-11-03 12:46:18 UTC；artifact 创建时间：12:46:25 UTC；工作流完成时间：12:46:38 UTC（中国标准时间 20:46:38）。

## 冒烟检查范围

CI 会启动每个冻结 EXE，确认进程至少存活 5 秒，再由 CI 主动终止。它证明 EXE 可启动，不代表 GUI 每个页面、真实用户交互、数据迁移或授权激活已经完整验收。源码自测和自动回归测试另行通过。

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
py tools/export_license_public_key.py --private-key "C:\\你的私钥路径\\seller-private.pem"
```

只把输出的 `SHA256=` 指纹（或公钥 PEM）发回用于比对；不要发送私钥。预期客户端指纹为上面 `src/license.py` 的 `B646...`。如果不一致，签发工具会拒绝生成客户授权，必须先确认密钥归属，再制定明确的密钥轮换方案。

## 上架前剩余验收

1. 卖家本地导出公钥指纹与客户端内嵌公钥匹配。
2. 在真实 Windows 电脑验证实际签发、产品名、设备码、到期日、签名校验、激活和重启后仍有效。
3. 验证无授权、错误签名、错误产品、错误设备及过期授权均被拒绝。
4. 逐款检查首次运行、重启后数据保留、CSV 导入/导出和备份恢复；目前销售客户跟进工具的 JSON 备份/恢复说明最完整，其他业务工具仍需逐款补齐备份恢复验收和中文说明。
5. 完成真实 Windows 终端验收后，再发布闲鱼商品。

## 当前结论

第一阶段 10 款 Windows EXE 已通过 GitHub Actions 的 10/10 矩阵构建与 ZIP 内容验收，最新客户包可供下载并进行后续终端验收。**这仍是待最终验收版本，不是已完成真实授权激活、可直接对外销售的正式成品。**
