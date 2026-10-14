# 第一批大陆版发布状态

## 当前结论（2026-10-14）

- 10 款 Windows EXE 在 2026-10-05 的 GitHub Actions 构建中通过了各自的回归测试、源码自测、EXE 启动冒烟检查，并生成独立 ZIP。
- 同次构建成功生成总交付包 `Phase1-Mainland-Windows-Tools.zip`，包含 EXE、中文说明书和套餐说明。
- 可在 GitHub Actions 成功构建记录中下载当时的交付包：  
  https://github.com/Ldc-12/Chatgpt-business-automatic/actions/runs/37284661083
- 2026-10-14 修复了文件整理、图片批处理、PDF 批处理三个单品启动时未执行授权校验的问题；最新构建正在验证这些变更，验证成功前不应把旧交付包当作已更新版本销售。
- 授权为离线签名授权；卖家必须持有与仓库内公钥匹配的私钥才能为买家签发授权。私钥不得上传到 GitHub。

## 上架前检查清单

1. 等待最新 `Mainland Windows EXE` 工作流成功。
2. 从最新成功记录的 Artifacts 下载 `mainland-phase1-customer-package`。
3. 检查 ZIP 内含 10 个 EXE、中文说明书和套餐说明。
4. 卖家在实际 Windows 电脑上验证授权签发、激活、重启后数据保留、CSV 导入导出及卸载/备份说明。
5. 用未授权设备测试应阻止启动；用匹配的有效授权测试可正常启动。
6. 完成实际 Windows 终端验证后，再发布闲鱼商品。

## 套餐建议

以 `.github/workflows/mainland-exe.yml` 中的套餐说明为准；价格只是初始测试价，应根据咨询、转化和售后情况调整。

## 限制

GitHub Actions 中的 EXE 构建及冒烟检查不等于在真实买家电脑上完成全流程验收。未完成卖家私钥准备与实际授权测试前，不应宣称产品已达到无条件开箱即用状态。
