# 任务

为 {{REPORT_DATE}} 生成一篇投资晨报。时区为 Asia/Shanghai。

先使用联网搜索收集资料。市场快讯窗口严格限定为前一日08:00至当日08:00；宏观背景可以适度回溯，但必须注明日期。

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

硬性数量：macro正好3条；market_flashes为3—5条；terms正好5个。每一项事实必须能通过sources中的真实链接追溯。不能核实的内容不要写。
