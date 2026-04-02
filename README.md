<div align="center">

# wechat-decrypt

> *"你和 TA 聊了三年，所有记录都在你电脑里，你却一条都搜不到"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-blueviolet)](https://claude.ai)
[![WeChat 4.x](https://img.shields.io/badge/WeChat-4.x-brightgreen)](https://weixin.qq.com)

<br>

你有没有想过，微信里那几年的聊天记录<br>
那些争吵、那些道歉、那些"在吗"<br>
全都加密躺在你的电脑里，你却一条都读不出来<br>

**这个 Skill 帮你解锁它们。**

丢给 Claude，它帮你解密、定位联系人、导出对话<br>
可以用来做 LLM 分析，可以找那条你记得但搜不到的消息<br>
也可以只是，重新读一遍

[支持环境](#支持环境) · [安装](#安装) · [使用](#使用) · [数据库结构](#数据库结构) · [技术背景](#技术背景)

</div>

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
你     ❯ 帮我找和前公司 王总 的所有消息，从加好友到最后一条

Claude ❯ 最早记录：2021-03-15（入职当天）
         最后一条：2025-01-20
         共 1,203 条，其中你发 612 条，对方发 591 条
```

> 文字消息和系统通知（撤回、加好友）为明文，可直接搜索。图片、语音、视频、通话存储为压缩格式，暂不支持提取内容。

---

## 支持环境

| 环境 | 支持状态 |
|------|:-------:|
| Windows + 微信 PC 4.x | ✅ 全自动 |
| macOS + 微信 | 🔜 计划中 |
| 微信 3.x | ❌ 不支持 |

解密期间微信桌面端需保持**登录运行**，需要管理员权限终端。

---

## 安装

```bash
git clone https://github.com/chengmarc/wechat-decrypt
cd wechat-decrypt
pip install -r requirements.txt
```

将 `wechat-decrypt.md` 放入你的 Claude skill 目录即可：

```bash
# Claude Code（全局）
cp wechat-decrypt.md ~/.claude/skills/

# 或当前项目
mkdir -p .claude/skills && cp wechat-decrypt.md .claude/skills/
```

---

## 使用

### 一键解密

```bash
python main.py decrypt
```

微信 4.x 数据目录默认在 `C:\Users\{用户名}\xwechat_files\`（不是 Documents，和 3.x 不一样）。可在微信 → 设置 → 文件管理确认实际路径。解密输出至 `wechat-decrypt/decrypted/`。

### 在 Claude 中操作

Skill 加载后，用自然语言描述需求即可：

```
帮我找和 [微信名/备注名] 的聊天记录
把 [某人] 2024 年的对话导出成可以给 AI 分析的格式
搜一下有没有人跟我提过 [关键词]
```

---

## 数据库结构

解密后是标准 SQLite，两个库，逻辑清晰。

### `contact/contact.db` — 找人

```sql
SELECT username, nick_name, remark, alias FROM contact
WHERE nick_name LIKE '%关键词%'
   OR remark    LIKE '%关键词%'
   OR alias     LIKE '%关键词%';
```

查到的 `username`（wxid）是下一步的钥匙。

### `message_0.db` — 找消息

微信没有一张全局消息表。每个联系人的消息单独存在一张表里，表名是 `Msg_` + MD5(wxid)：

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxx'.encode()).hexdigest())"
```

这个设计意味着你没法直接搜全库——必须先找人，再算出那个人的表名，再去查。

消息表的有效字段：

| 字段 | 说明 |
|------|------|
| `local_type` | 消息类型：1 = 文字 ✅，10000 = 系统通知 ✅，其余为压缩数据 |
| `real_sender_id` | 发送方 ID，双人会话只有两个值，先 SELECT 一下确认映射 |
| `create_time` | Unix 时间戳（秒） |
| `message_content` | type 1 / 10000 为明文，其余为压缩二进制 |

可以忽略的字段：`upload_status`（全 0）、`compress_content`（全空）、`sort_seq`（≈ create_time × 1000）、所有 `WCDB_CT_*` 列。

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

`real_sender_id` 的两个值先用 `SELECT DISTINCT real_sender_id` 确认，再填入。

---

## 技术背景

微信 4.x 用 SQLCipher 4 加密：AES-256-CBC + HMAC-SHA512，KDF 为 PBKDF2-HMAC-SHA512（256,000 次迭代），页大小 4096 字节。

密钥不在任何配置文件里——它活在微信进程的内存中。`wechat-decrypt` 扫描进程内存，匹配 `x'<64位hex密钥><32位hex盐>'` 格式直接提取 raw key，完全不依赖二进制偏移量，所以对所有 4.x 版本都有效。

用 DB Browser for SQLCipher 直接打开这些文件是不行的，加密参数非标准。必须先解密，再用普通版 DB Browser for SQLite 查询。

### 已失效的同类工具（别踩坑）

| 工具 | 失效原因 |
|------|------|
| `xaoyaoo/PyWxDump` | 2025 年 10 月收到律师函，已删库 |
| `LC044/WeChatMsg` | 依赖 PyWxDump，连带失效 |
| `SuxueCode/WechatBakTool` | 停止更新，不支持 4.x |

---

<div align="center">

MIT License © [chengmarc](https://github.com/chengmarc)

*数据是你的。读它的权利也是你的。*

</div>
