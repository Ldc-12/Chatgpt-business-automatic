import json, os, re
from datetime import datetime, timezone

OUT = "site/xianyu"
BASE = "https://ldc-12.github.io/Chatgpt-business-automatic"

PRODUCTS = [
    ("ai-coding-productivity-roi-kit","AI 编程效率 ROI 工具包",19.9,"AI 编程效率记录、复盘、ROI 计算表","程序员,AI编程,效率工具,Excel模板,工作效率"),
    ("freelancer-invoice-follow-up-kit","自由职业者催款跟进工具包",19.9,"应收账款跟进表、催款话术与每周复盘模板","自由职业,催款,应收账款,Excel模板,接单"),
    ("small-business-automation-audit-kit","小微企业自动化审计工具包",29.9,"梳理重复工作、评估自动化价值的实用模板","企业管理,自动化,效率提升,流程管理,Excel"),
    ("job-search-application-tracker-pro","求职申请管理 Pro",12.9,"职位申请、面试准备、跟进记录一套管理模板","求职,简历,面试,工作表,Excel模板"),
    ("ai-content-workflow-planner","AI 内容工作流规划器",19.9,"内容选题、生产、审核、发布的完整工作流模板","自媒体,AI写作,内容运营,小红书,效率"),
    ("client-onboarding-workflow-kit","客户 onboarding 交付工具包",19.9,"客户资料、项目启动、交付节点与欢迎邮件模板","客户管理,项目管理,自由职业,私域,交付"),
    ("meeting-action-tracker","会议行动项追踪器",9.9,"会议纪要、责任人、截止日期和跟进模板","会议纪要,项目管理,团队协作,Excel"),
    ("sop-builder-starter-kit","SOP 标准流程搭建工具包",19.9,"把重复工作整理成可执行、可交接的标准流程","SOP,流程管理,企业管理,创业,团队"),
    ("freelance-proposal-pipeline","自由职业报价提案管理器",19.9,"客户线索、报价、跟进和成交状态一体化管理","自由职业,报价,接单,客户管理,Excel"),
    ("simple-sales-pipeline-kit","轻量销售 Pipeline 工具包",19.9,"不需要复杂 CRM，也能管理客户阶段和下一步行动","销售,CRM,客户管理,销售漏斗,Excel"),
    ("creator-content-calendar-pro","自媒体内容日历 Pro",19.9,"内容日历、选题库、月度复盘模板","自媒体,内容日历,选题,运营,Excel"),
    ("personal-finance-admin-tracker","家庭财务事务管理器",12.9,"账单、订阅、续费和每月财务事务提醒模板","家庭财务,账单,订阅,Excel,生活管理"),
]

def slugify(s):
    return re.sub(r"[^a-z0-9-]", "", s.lower().replace(" ","-"))

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def make_cn_guide(p):
    return f"""# {p["name"]}｜大陆版使用说明\n\n## 你买到的是什么\n这是一套可以直接用 WPS/Excel/常见文档软件打开的效率工具，不要求 ChatGPT、OpenAI、VPN 或海外软件。\n\n## 建议使用方法\n1. 先打开表格/模板，删除示例数据。\n2. 按自己的工作、客户、项目或内容填入第一批真实数据。\n3. 连续使用 7 天。\n4. 每周复盘一次，保留真正有用的字段。\n\n## 注意\n模板是工具，不保证赚钱、求职、成交、涨粉或其他具体结果。示例数据仅用于演示。\n"""

def make_zip(slug):
    source=os.path.join("site","products",slug)
    target=os.path.join(OUT,slug,slug+"-xianyu-cn.zip")
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for root,_,files in os.walk(source):
            for name in files:
                full=os.path.join(root,name)
                z.write(full,os.path.relpath(full,source))
    return target

def listing(product):
    slug,name,price,summary,keywords = product
    checkout = BASE + "/products/" + slug + "/"
    delivery = BASE + "/delivery/" + slug + "/"
    title = f"{name}｜可直接使用｜WPS/Excel模板｜数字资料"
    body = f"""【产品】{name}

【适合谁】
适合个人、小微企业、自由职业者、运营人员等，希望把重复工作整理成固定流程的人。

【你将获得】
{summary}
包含可编辑的表格/文档模板，下载后即可按自己的实际情况修改。

【使用方式】
1. 下载压缩包/文件
2. 用 WPS、Excel 或常用文档软件打开
3. 把示例数据替换成自己的内容
4. 按模板开始使用

【产品特点】
• 不要求 ChatGPT
• 不要求海外软件
• 可在电脑上使用 WPS/Excel
• 一次购买，长期使用
• 示例数据均可替换

【交付】
拍下并完成付款后，按平台实际订单交付方式发送文件或下载地址。

【售后】
数字商品属于可复制资料，请下单前确认需求。文件无法打开、下载异常等问题可联系处理；模板内容可根据个人实际情况自行修改。

【搜索关键词】
{keywords}

【重要说明】
本商品是效率/管理模板，不构成财务、法律、医疗或职业结果保证。
"""
    return {
        "slug":slug,"title":title,"name":name,"price_rmb":price,
        "summary":summary,"keywords":keywords.split(","),"listing":body,
        "source_product":BASE+"/products/"+slug+"/","delivery_url":delivery,
        "checkout_url":checkout,
    }

def main():
    os.makedirs(OUT, exist_ok=True)
    catalog = [listing(p) for p in PRODUCTS]
    write(OUT+"/catalog.json", json.dumps({
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "channel":"闲鱼大陆版",
        "payment_note":"当前仅生成上架素材；闲鱼正式收款与虚拟商品自动交付需按平台规则完成开通/审核。",
        "products":catalog
    }, ensure_ascii=False, indent=2))
    cards = []
    for p in catalog:
        slug=p["slug"]
        path=f"{OUT}/{slug}"
        write(path+"/listing.txt", p["listing"])\n        make_zip(slug)
        write(path+"/README.md", "# "+p["name"]+"\n\n闲鱼标题：\n"+p["title"]+"\n\n价格：￥"+str(p["price_rmb"])+"\n\n"+p["listing"])
        cards.append(f"<article><h2>{p['name']}</h2><p>{p['summary']}</p><strong>￥{p['price_rmb']}</strong><p><a href='{slug}/listing.txt'>复制闲鱼详情文案</a> · <a href='{p['source_product']}'>产品预览</a></p></article>")
    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>闲鱼上架素材中心</title><style>body{font-family:system-ui,-apple-system,sans-serif;max-width:1000px;margin:0 auto;padding:28px;line-height:1.65}article{border:1px solid #ddd;border-radius:14px;padding:18px;margin:14px 0}a{color:#06c}strong{font-size:22px}</style></head><body><h1>闲鱼上架素材中心</h1><p>12 个大陆版数字效率产品。当前采用低门槛测试价；成交数据稳定后，再根据内容深度、买家反馈和转化数据逐步调整。</p>""" + "".join(cards) + """<hr><p><strong>合规提示：</strong>请按闲鱼当前商品、支付、虚拟商品及知识产权规则发布；不要绕过平台支付或以虚假方式描述商品。</p></body></html>"""
    write(OUT+"/index.html", html)
    print("Generated Xianyu catalog:", len(catalog))

if __name__ == "__main__":
    main()
