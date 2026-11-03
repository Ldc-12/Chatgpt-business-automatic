# 第一批大陆版发布状态

## 最近一次可复现构建（2026-11-03 20:20，中国标准时间）

- 发布分支：`fix-package-artifact-download-and-readme-encoding`
- PR：[#8 Make mainland package downloads verifiable and fix README encoding](https://github.com/Ldc-12/Chatgpt-business-automatic/pull/8)
- PR head：`f24b386b2bf4c5f3c144421c8312533d8d05b4c0`
- Mainland Windows EXE Actions：[#141](https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41634598567)，结论：`success`
- 10/10 个 Windows 矩阵任务全部成功：回归测试、源码自测、EXE 构建、首次启动冒烟检查、单品 ZIP 均通过。
- 总套餐打包 job：成功；Code scanning AI findings：成功。
- 正式构建产物 artifact：`mainland-phase1-customer-package`，ID：`13229404109`，大小：129,596,442 bytes。
- 外层 artifact 内的最终客户 ZIP：129,560,314 bytes。
- 最终客户 ZIP SHA256：`8f3b5dea11f40d9d8a85c31546f69e1c227e9e7176b0873c1086d8588a7506e3`。
- ZIP 内容验收：10 个 EXE、10 份产品用户说明书、1 份说明书索引 README、1 份大陆版 README、1 份套餐说明 TXT；共 25 个 ZIP 条目（含 2 个目录）。
- 下载分片清单 artifact：`mainland-phase1-package-manifest`，ID：`13230375920`；7 个分片 artifact 已上传，重组后与最终 ZIP SHA256 完全一致。
- 构建时间：2026-11-03 12:20:21 UTC（2026-11-03 20:20:21 中国标准时间）。

## 冒烟检查范围

CI 的 EXE 冒烟检查会启动每个冻结 EXE，确认进程至少存活 5 秒，然后由 CI 主动终止。它用于确认 EXE 能启动，不代表 GUI 每个页面、用户交互或授权激活已完整验收。每个产品的源码自测和自动回归测试另行通过。

## 授权系统阻塞（正式销售前必须解决）

- `src/license.py` 内嵌公钥 SHA256 指纹：`B64663DA16A11E9E927D2FAE897973373ADBEA81B45D300C208ACF4F2896E741`。
- `config/mainland_license_public_key.pem` SHA256 指纹：`7AEA3764E5D59B0C2502CCD302CBBBBC79CD96555AE2D5472477B5E473A2E961`。
- 两份文件均可解析为 Ed25519 公钥，但指纹不同，不能视为同一密钥对。
- 卖家私钥不在仓库中。不得上传、提交或发送卖家私钥，也不得猜测或新造私钥来覆盖现有公钥。
- 最终匹配验收只需要卖家在可信 Windows 电脑本地导出公钥后，向开发方提供**公钥 PEM 或 SHA256 指纹**；不需要提供私钥。
- 在确认卖家公钥与客户端内嵌公钥匹配，并完成真实 Windows 签发、激活和重启验证前，不得宣称授权可用或标记为正式可销售。

## 上架前剩余验收

1. 核对卖家本地私钥导出的公钥或 SHA256 指纹与客户端内嵌公钥一致。
2. 在真实 Windows 电脑验证签发、正确产品名、设备码、到期日、签名校验和激活。
3. 验证无授权、错误签名、错误产品、错误设备及过期授权均被拒绝。
4. 逐款检查首次运行、重启后数据保留、CSV 导入/导出及备份恢复。
5. 完成真实 Windows 终端验收后，再发布闲鱼商品。

## 当前结论

第一阶段 10 款 Windows EXE 已有一份通过 GitHub Actions 构建和 ZIP 内容验收的技术交付包，可用于后续终端验收；但卖家授权密钥匹配和真实 Windows 激活尚未完成，因此**当前仍是待最终验收版本，不是可直接对外销售的正式成品**。
