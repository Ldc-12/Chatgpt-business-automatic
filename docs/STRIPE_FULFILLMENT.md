# Stripe 自动发货说明

## 当前架构

1. Stripe Payment Link 负责收款。
2. 付款完成后，Stripe 可以将客户重定向到站点，并把 `{CHECKOUT_SESSION_ID}` 附加到 URL。
3. 正式自动发货应由 Stripe `checkout.session.completed` webhook 触发。
4. GitHub Pages 只负责展示静态产品和交付说明，不保存 Stripe 密钥。

## 当前限制

GitHub Pages 是静态托管，不能安全验证 Stripe Session，也不能接收 Stripe Webhook。因此当前 delivery 页面不能单独作为“付款验证器”。

## 正式方案

将 `server/stripe_webhook.py` 部署到支持 HTTPS serverless function 的平台，并配置：

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`

Webhook 监听：

- `checkout.session.completed`

Payment Link 的 metadata 应包含：

- `product_slug`

Webhook 验证付款成功后，再生成一次性下载凭证或向客户发送交付邮件。

## Payment Link 跳转

Stripe Payment Link 支持：

`after_completion[type]=redirect`

以及：

`after_completion[redirect][url]=https://ldc-12.github.io/Chatgpt-business-automatic/delivery/{slug}/?session_id={CHECKOUT_SESSION_ID}`

Stripe 官方文档：
https://docs.stripe.com/api/payment-link/update

注意：不要把 Stripe Secret Key 提交到 GitHub。
