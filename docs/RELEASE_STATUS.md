# 第一批大陆版发布状态

## 当前结论（2026-11-03）

- PR #4 已于 2026-11-02 合并至 main：修复产品名称含空格时授权文件路径被错误替换的问题。
- 合并前的 Windows 验证构建（Actions run 38751142900）已成功：10 个产品矩阵任务全部完成回归测试、源码自测、EXE 构建、EXE 启动冒烟检查及单品 ZIP 上传；总套餐打包任务也成功。
- 该次成功构建生成 artifact：`mainland-phase1-customer-package`（artifact ID：11982301687，约 129.6 MB），以及 10 个单品 artifacts。该构建属于合并前 PR 分支的验证结果。
- 合并到 main 后已触发新的正式分支构建：Actions run 41502171443；记录更新时仍在运行。必须以该 main 构建成功后的 artifact 作为正式最新包，不要把旧包冒充 main 最新包。
- 最新主分支提交：`44c8b128529f8ef749bcee494c9081175d0218e3`。

## 授权系统阻塞（必须解决后才能正式销售）

- `src/license.py` 内嵌公钥与 `config/mainland_license_public_key.pem` 当前内容不同，不能假设它们属于同一密钥对。
- 卖家私钥不在仓库中，且不得上传到 GitHub 或发送给 ChatGPT。
- 在卖家于可信 Windows 电脑从现有私钥导出公钥并确认匹配前，不得声称可以签发有效授权，也不得把产品标记为正式可销售。
- 后续只需要用户提供导出的**公钥**或 SHA256 指纹，不需要私钥。

## 上架前检查清单

1. 确认 main 分支最新 `Mainland Windows EXE` 工作流成功。
2. 下载该次成功构建的 `mainland-phase1-customer-package` artifact。
3. 实际检查 ZIP：应包含 10 个 EXE、中文说明书目录、套餐说明及 README。
4. 在真实 Windows 电脑上用卖家本地私钥验证公钥匹配，并完成授权签发、激活、重启后数据保留、CSV 导入导出及备份恢复测试。
5. 用未授权设备测试应阻止启动；用匹配的有效授权测试可正常启动。
6. 完成真实 Windows 终端验收后，再发布闲鱼商品。

## 套餐建议

以 `.github/workflows/mainland-exe.yml` 中的套餐说明为准；价格只是初始测试价，应根据咨询、转化和售后情况调整。

## 限制

GitHub Actions 中的回归测试、EXE 构建和启动冒烟检查，不等于真实买家电脑上的完整验收。授权密钥一致性和真实 Windows 激活尚未完成前，不应宣称产品已达到无条件开箱即用状态。
