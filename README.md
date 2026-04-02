<div align="center">

# wechat-to-LLM

> *"你和 TA 聊了三年，所有记录都在你电脑里，你却一条都搜不到"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-blueviolet)](https://claude.ai)
[![WeChat 4.x](https://img.shields.io/badge/WeChat-4.x-brightgreen)](https://weixin.qq.com)

<br>

你有没有想过，微信里那几年的聊天记录<br>
那些争吵、那些道歉、那些"在吗"<br>
全都加密躺在你的电脑里，你却一条都读不出来<br>

**这个 Skill 帮你把它们交给 Claude。**

解密核心由 [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 提供<br>
本项目贡献的是：Claude Skill、DB schema 梳理、SQL 查询模板、LLM 导出格式

[这个项目做了什么](#这个项目做了什么) · [支持环境](#支持环境) · [快速开始](#快速开始) · [数据库结构](#数据库结构)

</div>

---

## 这个项目做了什么

微信 4.x 的聊天记录是加密的 SQLite，结构也不直观——没有全局消息表，每个联系人单独一张表，表名还需要手动计算。

本项目在 `ylytdeng/wechat-decrypt` 的解密能力基础上，提供：

- **Claude Skill**：自然语言驱动的完整操作流，从找人到导出一步到位
- **DB schema 文档**：梳理了哪些字段有用、哪些可以忽略、数据类型的实际含义
- **SQL 查询模板**：联系人定位、时间范围过滤、双人对话导出
- **LLM 导出格式**：压缩为带时段分隔的紧凑文本，直接可以送入 LLM 分析

---

## 你可以用它做什么

**找那条你记得但死活搜不到的消息**

```
你     ❯ 帮我找和李明的聊天，他说过"我不会走的"，大概是去年冬天

Claude ❯ 在 2024-12-07 找到一条：
         李明：我不会走的，别这样想
         上下文：你们在讨论异地的事
```

**看看你们到底说过什么**

```
你     ❯ 把我和张雪 2023 年全年的聊天导出来，我想交给 AI 分析

Claude ❯ 已导出 4,821 条消息，时间跨度 2023-01-03 至 2023-12-29
         压缩为 LLM 可读格式，按对话时段自动分段
         文件：chat_zhangxue_2023.txt
```

**整理一段关系的完整时间线**

```
你     ❯ 帮我找和前公司王总的所有消息，从加好友到最后一条

Claude ❯ 最早记录：2021-03-15（入职当天）
         最后一条：2025-01-20
         共 1,203 条，其中你发 612 条，对方发 591 条
```

> 文字消息和系统通知（撤回、加好友）为明文，可直接搜索。图片、语音、视频、通话存储为压缩格式，暂不支持提取内容。

---

## 支持环境

| 环境 | 支持状态 |
|------|:-------:|
| Windows + 微信 PC 4.x | ✅ |
| macOS + 微信 | ❌ |
| 微信 3.x | ❌ |

解密期间微信桌面端需保持**登录运行**，需要管理员权限终端。

---

## 快速开始

### Step 1 — 安装解密工具

本项目的解密能力来自 [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt)，请先完成它的安装：

```bash
git clone https://github.com/ylytdeng/wechat-decrypt
cd wechat-decrypt
pip install -r requirements.txt
python main.py decrypt
```

微信 4.x 数据目录默认在 `C:\Users\{用户名}\xwechat_files\`，与 3.x 不同。可在微信 → 设置 → 文件管理确认实际路径。解密输出至 `wechat-decrypt/decrypted/`。

### Step 2 — 加载 Claude Skill

将本项目的 `wechat-decrypt.md` 放入你的 Claude skill 目录：

```bash
# Claude Code（全局）
cp wechat-decrypt.md ~/.claude/skills/

# 或当前项目
mkdir -p .claude/skills && cp wechat-decrypt.md .claude/skills/
```

加载后用自然语言操作即可，无需记 SQL：

```
帮我找和 [微信名/备注名] 的聊天记录
把 [某人] 2024 年的对话导出成可以给 AI 分析的格式
搜一下有没有人跟我提过 [关键词]
```

---

## 数据库结构

解密后是标准 SQLite，两个库。

### `contact/contact.db` — 找人

搜联系人：

```sql
SELECT username, nick_name, remark, alias FROM contact
WHERE nick_name LIKE '%关键词%'
   OR remark    LIKE '%关键词%'
   OR alias     LIKE '%关键词%';
```

查到的 `username`（wxid）是下一步的钥匙。

### `message_0.db` — 找消息

微信没有全局消息表。每个联系人的消息单独一张表，表名是 `Msg_` + MD5(wxid)：

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxx'.encode()).hexdigest())"
```

消息表有效字段：

| 字段 | 说明 |
|------|------|
| `local_type` | 消息类型：1 = 文字 ✅，10000 = 系统通知 ✅，其余为压缩数据 |
| `real_sender_id` | 发送方 ID，双人会话只有两个值，先 `SELECT DISTINCT` 确认映射 |
| `create_time` | Unix 时间戳（秒） |
| `message_content` | type 1 / 10000 为明文，其余为压缩二进制 |

可忽略字段：`upload_status`（全 0）、`compress_content`（全空）、`sort_seq`（≈ create_time × 1000）、所有 `WCDB_CT_*` 列。

### 导出为 LLM 可读格式

```sql
SELECT
    CASE real_sender_id WHEN 10 THEN '我' WHEN 1781 THEN 'TA' END AS sender,
    substr(strftime('%Y-%m-%d %H:%M', create_time, 'unixepoch', '+8 hours'), 3) AS time,
    message_content
FROM Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHERE local_type = 1
ORDER BY create_time ASC;
```

---

## 已失效的同类工具

| 工具 | 失效原因 |
|------|------|
| `xaoyaoo/PyWxDump` | 2025 年 10 月收到律师函，已删库 |
| `LC044/WeChatMsg` | 依赖 PyWxDump，连带失效 |
| `SuxueCode/WechatBakTool` | 停止更新，不支持 4.x |

---

## 免责声明

本工具仅用于学习和研究目的，用于解密**自己的**微信数据。请遵守相关法律法规，不要用于未经授权的数据访问。

---

<div align="center">

MIT License © [chengmarc](https://github.com/chengmarc)

*数据是你的。读它的权利也是你的。*

</div>

