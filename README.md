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

**这两个 Skill 帮你把它们交给 Claude。**

解密核心由 [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 提供<br>
本项目贡献的是：Claude Skill（私聊 + 群聊）、DB schema 梳理、SQL 查询模板、LLM 导出格式

[这个项目做了什么](#这个项目做了什么) · [支持环境](#支持环境) · [快速开始](#快速开始) · [数据库结构](#数据库结构)

</div>

---

## 这个项目做了什么

微信 4.x 的聊天记录是加密的 SQLite，结构也不直观——没有全局消息表，每个联系人单独一张表，表名还需要手动计算。群聊更麻烦：发送者 ID 嵌在消息内容里，不在独立字段。

本项目在 `ylytdeng/wechat-decrypt` 的解密能力基础上，提供：

- **Claude Skill — 私聊**（`skills/skill-private.md`）：联系人定位、消息查询、双人对话导出
- **Claude Skill — 群聊**（`skills/skill-chatroom.md`）：成员 ID 提取、发送者映射、群消息导出
- **导出脚本**（`scripts/`）：私聊/群聊各一个，CLI 参数化，可独立运行
- **DB schema 文档**：梳理了哪些字段有用、哪些可以忽略、数据类型的实际含义
- **SQL 查询模板**：联系人定位、时间范围过滤、双人/群聊导出
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

**导出群聊总结**

```
你     ❯ 把这个群最近一周的消息导出来，我想让 AI 做个总结

Claude ❯ 已导出 2026-03-27 至 2026-04-03 的群聊记录
         共 847 条，涉及 23 位成员
         文件：chat_2026-03-27_2026-04-03.txt
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
python decrypt_db.py
```

微信 4.x 数据目录默认在 `C:\Users\{用户名}\xwechat_files\`，与 3.x 不同。可在微信 → 设置 → 文件管理确认实际路径。解密输出至 `wechat-decrypt/decrypted/`。

### Step 2 — 加载 Claude Skill

根据需要加载私聊或群聊 Skill（或两者都加载）：

```bash
# Claude Code（全局）
cp skills/skill-private.md ~/.claude/skills/
cp skills/skill-chatroom.md ~/.claude/skills/

# 或当前项目
mkdir -p .claude/skills
cp skills/skill-private.md .claude/skills/
cp skills/skill-chatroom.md .claude/skills/
```

加载后用自然语言操作即可，无需记 SQL：

```
帮我找和 [微信名/备注名] 的聊天记录
把 [某人] 2024 年的对话导出成可以给 AI 分析的格式
把 [某群] 最近 7 天的消息导出来
```

### Step 3 — 安装脚本依赖

导出脚本仅依赖 Python 标准库，无需额外安装。直接运行：

```bash
# 双人会话
python scripts/export_private.py --db PATH --table MSG_TABLE --my-id MY_ID --other-id OTHER_ID > chat_private.txt

# 群聊
python scripts/export_chatroom.py --db PATH --table MSG_TABLE --id-map id_map.json > chat_chatroom.txt
```

参数说明见各 Skill 文件或 `python scripts/export_*.py --help`。

---

## 数据库结构

解密后是标准 SQLite，两个库。

### `contact/contact.db` — 找人

```bash
sqlite3 ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
  "SELECT username, nick_name, remark, alias FROM contact
   WHERE nick_name LIKE '%关键词%'
      OR remark    LIKE '%关键词%'
      OR alias     LIKE '%关键词%';"
```

查到的 `username`（wxid）是下一步的钥匙。群聊的 username 格式为 `数字@chatroom`。

### `message/message_0.db` — 找消息

微信没有全局消息表。每个联系人的消息单独一张表，表名是 `Msg_` + MD5(wxid)：

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxx'.encode()).hexdigest())"
```

消息表有效字段：

| 字段 | 说明 |
|------|------|
| `local_type` | 消息类型：1 = 文字 ✅，10000 = 系统通知 ✅，其余为压缩数据 |
| `real_sender_id` | 发送方 ID；私聊可用，群聊不可靠（发送者嵌在 `message_content` 前缀中） |
| `create_time` | Unix 时间戳（秒） |
| `message_content` | type 1 / 10000 为明文，其余为压缩二进制；群聊格式为 `wxid_xxx:\n正文` |

可忽略字段：`upload_status`（全 0）、`compress_content`（全空）、`sort_seq`（≈ create_time × 1000）、所有 `WCDB_CT_*` 列。

完整操作流程见 `skills/` 目录下的对应 Skill 文件。

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
