# 投资晨报个人网页版

这是一个手机优先、无需安装客户端的个人投资晨报网页。

## 打开方式

直接双击 `index.html` 即可预览。为了获得更稳定的浏览效果，也可以在当前文件夹启动任意静态文件服务器。

## 已实现

- 今日晨报在线阅读；
- 新版“3条宏观＋3—5条市场快讯”结构；
- 手机与桌面响应式布局；
- 晨报目录与阅读进度；
- 正文字号切换并保存偏好；
- 往期晨报页面；
- 投资知识树页面，以及正文只显示“今日路径”；
- 互动思考题；
- 打印或保存为 PDF；
- 导出 Word 兼容草稿；
- GitHub Actions每天自动触发；
- 多个公开 RSS 新闻源；
- DeepSeek API，以及可替换 AI 提供商；
- 当前晨报与按日期保存的历史晨报；
- 失败保护：抓取、AI或校验失败时不覆盖上一期。

## 运行方式

界面内置测试晨报作为离线后备内容。`launcher/` 包含07:40生成、08:00发布的后台；配置云端API密钥并部署后，页面会自动读取最新晨报。

安全原则：API密钥只保存在云端环境变量中，不写入网页、JSON、Git或浏览器本地存储。

## 自动流程

```text
GitHub Actions（北京时间07:40启动，目标08:00前发布）
→ 抓取公开RSS
→ DeepSeek分析并生成完整JSON
→ 校验结构、数量和来源URL
→ 归档到 data/history/YYYY-MM-DD.json
→ 更新 data/history.json
→ 最后更新 data/today.json
→ 网页自动读取GitHub最新内容
```

任一步失败都不会覆盖上一期。

系统从2026-06-21开始扫描缺失日期，每次最多生成2期并按最早缺口优先。若余额不足，次日早上会再次检查并继续补缺。

## 部署与自动生成

Vercel已经连接GitHub并负责网页；GitHub Actions负责每天生成。只需在GitHub仓库的Actions Secrets中配置 `DEEPSEEK_API_KEY`，不用在Vercel填写。每天生成成功后会提交当前晨报和历史归档，Vercel自动同步。

余额不足或接口失败时，网站保留上一期并显示“当前展示最近一期”，不会生成假内容。

## 切换AI提供商

- GitHub Models：`AI_PROVIDER=github_models`，使用 `GH_MODELS_TOKEN`。
- OpenAI：`AI_PROVIDER=openai`，配置 `OPENAI_API_KEY` 和可用的 `AI_MODEL`。
- 兼容Chat Completions的其他接口：配置 `AI_PROVIDER=custom`、`AI_ENDPOINT`、`AI_API_KEY`、`AI_MODEL`。

详细步骤见《部署说明.md》。
