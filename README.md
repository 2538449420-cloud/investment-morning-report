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
- Vercel Cron 每天自动触发；
- 多个公开 RSS 新闻源；
- GitHub Models 免费推理接口，以及可替换 AI 提供商；
- 当前晨报与按日期保存的历史晨报；
- 失败保护：抓取、AI或校验失败时不覆盖上一期。

## 运行方式

界面内置测试晨报作为离线后备内容。`launcher/` 包含07:40生成、08:00发布的后台；配置云端API密钥并部署后，页面会自动读取最新晨报。

安全原则：API密钥只保存在云端环境变量中，不写入网页、JSON、Git或浏览器本地存储。

## 自动流程

```text
Vercel Cron（北京时间目标08:00）
→ 抓取公开RSS
→ 免费AI分析并生成完整JSON
→ 校验结构、数量和来源URL
→ 归档到 data/history/YYYY-MM-DD.json
→ 更新 data/history.json
→ 最后更新 data/today.json
→ 网页自动读取GitHub最新内容
```

任一步失败都不会覆盖上一期。

## Vercel部署

1. 在Vercel用GitHub登录，导入仓库 `2538449420-cloud/investment-morning-report`。
2. Framework Preset选择 `Other`，其他构建设置保持默认，先完成首次部署。
3. 在Vercel项目 `Settings → Environment Variables` 添加：

| 名称 | 用途 |
|---|---|
| `CRON_SECRET` | 自己生成的长随机字符串，保护定时接口 |
| `GH_MODELS_TOKEN` | GitHub Models读取权限，仅供免费AI推理 |
| `GH_CONTENT_TOKEN` | 仅授权本仓库Contents读写，用于保存晨报 |
| `GH_CONTENT_REPOSITORY` | `2538449420-cloud/investment-morning-report` |
| `AI_PROVIDER` | `github_models` |
| `AI_MODEL` | 默认 `openai/gpt-4.1-mini`，也可换成账号可用模型 |

4. 环境变量添加到Production，保存后重新部署一次。
5. `vercel.json` 设置为UTC 00:00触发，即北京时间目标08:00。
6. 首次任务成功后，网页出现当天晨报，往期内容进入历史目录。

不要把任何Token写入代码、JSON、聊天或浏览器前端。免费模型有速率和额度限制；限额不足时网站保留上一期。

## 切换AI提供商

- GitHub Models：`AI_PROVIDER=github_models`，使用 `GH_MODELS_TOKEN`。
- OpenAI：`AI_PROVIDER=openai`，配置 `OPENAI_API_KEY` 和可用的 `AI_MODEL`。
- 兼容Chat Completions的其他接口：配置 `AI_PROVIDER=custom`、`AI_ENDPOINT`、`AI_API_KEY`、`AI_MODEL`。

详细步骤见《部署说明.md》。
