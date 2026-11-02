# 第一批大陆版发布状态

## 当前结论（2026-11-03）

- PR #4 已合并至 main，修复产品名称含空格时授权文件路径被错误替换的问题。
- main 分支 Windows 构建 Actions run 41502171443 已成功，10/10 个产品矩阵任务全部成功；回归测试、源码自测、EXE 构建、EXE 启动冒烟检查均通过；总套餐打包 job 成功。
- 正式总套餐 artifact：`mainland-phase1-customer-package`，artifact ID：13170475013，大小 129,591,029 bytes。
- 已下载并检查 artifact 内的最终交付 ZIP。最终 ZIP 内含 10 个 EXE、10 份产品用户说明书、说明书目录 README、套餐说明 TXT 和大陆版 README。
- 最终交付 ZIP SHA256：`a3895e18764cc4e30150a52e21992209d6a31c13067d88351371b623984c8731`。
- 构建记录：https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/41502171443
- 最新产品源码合并提交：`44c8b128529f8ef749bcee494c9081175d0218e3`。本发布状态文档后续单独更新。

## 授权系统阻塞（正式销售前必须解决）

- `src/license.py` 内嵌公钥与 `config/mainland_license_public_key.pem` 内容不同，不能假设它们属于同一密钥对。
- 卖家私钥不在仓库中，且不得上传到 GitHub 或发送给 ChatGPT。
- 在卖家于可信 Windows 电脑从现有私钥导出公钥并确认匹配前，不得声称可以签发有效授权，也不得把产品标记为正式可销售。
- 后续只需要用户提供导出的**公钥**或 SHA256 指纹，不需要私钥。

## 上架前验收

1. 从 main 分支成功构建记录下载 `mainland-phase1-customer-package`。
2. 检查 ZIP 内含 10 个 EXE、10 份中文说明书、套餐说明及 README。
3. 在真实 Windows 电脑上验证卖家本地私钥对应公钥，并完成授权签发、激活、重启后数据保留、CSV 导入导出及备份恢复测试。
4. 用未授权设备测试应阻止启动；用匹配的有效授权测试可正常启动。
5. 完成真实 Windows 终端验收后，再发布闲鱼商品。

## 限制

GitHub Actions 的自动化回归测试、EXE 构建和启动冒烟检查不等于真实买家电脑上的完整验收。授权密钥一致性和真实 Windows 激活尚未完成前，不应宣称产品已达到无条件开箱即用状态。
