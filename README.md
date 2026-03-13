# 中国金融市场资讯简报自动化

这套方案使用 `GitHub Actions + Python 定时脚本 + SMTP 邮件推送`，可以在你的电脑关机时继续运行。

## 功能

- 工作日北京时间 `09:30` 自动执行
- 周一输出“本周前瞻”，周二到周五输出“周内滚动简报”
- 固定四栏：`A股 / 债市 / 汇率 / 政策`
- 优先从百度搜索结果中抓取本周中国金融市场资讯线索
- 每条内容都附带来源链接
- 自动生成 Markdown 报告并通过邮件发送

## 文件结构

- [`.github/workflows/market-digest.yml`](D:\Codex\.github\workflows\market-digest.yml)
- [`scripts/market_digest.py`](D:\Codex\scripts\market_digest.py)
- [`requirements.txt`](D:\Codex\requirements.txt)
- [`.env.example`](D:\Codex\.env.example)

## 使用方法

1. 把仓库推到 GitHub。
2. 在 GitHub 仓库 `Settings > Secrets and variables > Actions` 中添加这些 secrets：
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `SMTP_USE_TLS`
   - `MAIL_FROM`
   - `MAIL_TO`
   - `BAIDU_COOKIES`，可选
3. 启用 GitHub Actions。
4. 手动运行一次 `China Market Digest` 工作流，确认邮件能正常送达。

## 定时说明

- GitHub Actions 的 `cron` 使用 `UTC` 时区。
- 当前工作流配置为 `30 1 * * 1-5`，对应北京时间工作日 `09:30`。
- 如果你后面想改成别的时间，只需要调整 [`.github/workflows/market-digest.yml`](D:\Codex\.github\workflows\market-digest.yml) 里的 cron。

## 报告模式

- 周一：输出“本周前瞻”
- 周二到周五：输出“周内滚动简报”
- 固定栏目：`A股 / 债市 / 汇率 / 政策`

## 邮件服务建议

- `QQ 邮箱`：常见做法是使用 SMTP 授权码，不直接用登录密码。
- `Gmail`：建议使用应用专用密码。
- `企业邮箱`：按服务商提供的 SMTP 配置填写。

## 关于百度抓取

GitHub Actions 的云端 IP 可能触发百度风控，因此脚本做了这些处理：

- 设置常见浏览器请求头
- 支持通过 `BAIDU_COOKIES` 注入 cookie
- 失败时会保留已抓到的结果并继续生成报告

如果你后面发现百度在 Actions 上不稳定，最稳的升级方向是把采集部分改成：

- 百度检索做辅助
- 官方站点和主流财经媒体做主来源

这个仓库结构已经留好了，后续扩展不需要重做。
