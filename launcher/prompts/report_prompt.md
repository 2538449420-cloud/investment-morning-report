# 任务

为 {{REPORT_DATE}} 生成一篇投资晨报。时区为 Asia/Shanghai。

不要自行联网搜索。Python 已经提供经过筛选的新闻候选。

市场快讯窗口严格限定为前一日08:00至当日08:00；宏观背景可以适度回溯最近3—5天，但必须注明日期。

只返回一个合法 JSON 对象，不要使用 Markdown 代码围栏，不要输出解释文字。

## 去重与日更规则

本晨报属于持续连载产品。

必须保证读者能够明显感受到每天内容不同。

1. theme（大标题）
不得与最近7期晨报重复。

2. market_flashes（市场快讯）
优先选择过去24小时新增事件。
不得重复引用昨日已经使用过的新闻作为主要快讯。

3. terms（投资名词）
优先选择最近14天未出现过的名词。

如果出现重复：
必须采用不同角度解释。

4. question（思考题）
不得与最近14天晨报重复。

5. company_case（公司案例）
不得连续两天使用同一家公司。

6. summary（导语）
必须体现今天新增发生了什么。

7. 如果市场变化有限：
允许延续原有课程结构，
但必须明确指出：
哪些内容是新增信息，
哪些内容属于持续跟踪。

## JSON结构

```json
{
  "report_date": "YYYY-MM-DD",
  "theme": "一句主线",
  "summary": "一段导语",
  "macro": [
    {"region": "美国", "title": "", "summary": "", "why_it_matters": "", "source_ids": ["s1"]}
  ],
  "market_flashes": [
    {
      "time_bjt": "07:10",
      "title": "",
      "summary": "",
      "beneficiaries": ["行业或公司"],
      "pressured": ["行业或公司"],
      "watch_point": "市场是否已经反应或可能反应过度",
      "source_ids": ["s2"]
    }
  ],
  "terms": [
    {"name": "", "english": "", "definition": "", "connection": ""}
  ],
  "concept": {
    "title": "",
    "question": "",
    "explanation": ["段落1", "段落2"],
    "formula": {"name": "", "expression": "", "example": "", "limitation": ""},
    "counterexample": ""
  },
  "company_case": {
    "company": "",
    "topic": "",
    "business_model": "",
    "customers_pay_because": "",
    "revenue_profit_cash": "",
    "advantages": [""],
    "weaknesses": [""],
    "metrics": [{"label": "", "value": "", "date": "", "source_ids": ["s3"]}],
    "failure_conditions": [""],
    "valuation_boundary": ""
  },
  "question": {
    "prompt": "",
    "options": [{"id": "A", "text": ""}],
    "answer": "A",
    "explanation": ""
  },
  "knowledge_path": {
    "module": "风险与决策",
    "parent": "市场预期",
    "nodes": ["一致预期", "Price In", "预期差", "风险溢价"],
    "today": "预期差"
  },
  "sources": [
    {"id": "s1", "publisher": "", "title": "", "published_at": "", "url": "", "source_type": "primary|wire|mainstream"}
  ],
  "disclaimer": "本文用于投资知识学习和信息交流，不构成任何投资建议。"
}
```

硬性数量：macro正好3条；market_flashes为2—5条；terms正好5个。每一项事实必须能通过sources中的真实链接追溯。不能核实的内容不要写。

## 课程设计规则

这不是新闻聚合器，也不是孤立课程。每天必须用最新财经新闻，推进一个新的投资认知。

今天的晨报必须同时回答两个问题：

1. 今天市场发生了什么？
2. 投资者今天应该学会什么新的认知？

新闻提供时效性，知识提供成长性。两者同等重要，任何一项缺失，都不能认为是一份合格晨报。

生成前先做五步判断：

1. 分析今日新闻，找出最重要的话题领域，例如 AI、芯片、利率、银行、能源、消费、房地产、出口、黄金、原油。
2. 阅读 Knowledge Map，优先参考已有知识空间。Knowledge Map 不是课程顺序，也不是封闭边界。
3. 阅读历史学习台账，判断这个领域过去已经讲过哪些 lesson、terms、question、knowledge_path。
4. 优先在 Knowledge Map 中选择一个与今日新闻高度相关、但过去讲得少或没有深入讲过的新知识。如果今日重大新闻涉及 Knowledge Map 尚未覆盖的新知识，可以新增知识点，但必须归属到现有模块。
5. 用今日新闻和指定公司案例解释这个知识。

多个知识都合适时，按以下优先级选择：与今日新闻联系最紧密；历史覆盖较少；更能帮助投资者建立长期认知；与最近几天课程差异更大。

如果只是昨天课程换一条新闻、换一个标题、换一个公司，即使 JSON 合法，也是不合格。

允许旧知识再次出现，但必须深入一层。例如 PE 不能反复讲定义，可以讲高PE为什么不一定贵、PE为什么不适合银行、PE什么时候失效、PE与DCF有什么区别。

Knowledge Map 不限制你的表达方式，也不是永久固定教材；但如果新增知识点，knowledge_path.module 必须归属到现有模块，并尽量避免与历史知识重复。
