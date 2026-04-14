<div align="center">

# 微信.skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-blueviolet)](https://claude.ai)
[![WeChat 4.x](https://img.shields.io/badge/WeChat-4.x-brightgreen)](https://weixin.qq.com)

<br>

**把你的微信聊天记录交给 Claude，让它成为你的记忆。**

*在对话里直接问 Claude：她当时说了什么、我们是哪天最后一次聊、这段关系从什么时候开始变。*

</div>

---

## 它能做什么

**找那条你记得但搜不到的消息**

```
你     ❯ 帮我找和李明的聊天，他说过"我不会走的"，大概是去年冬天

Claude ❯ 在 2024-12-07 找到一条：
         李明：我不会走的，别这样想
         上下文：你们在讨论异地的事
```

**整理一段关系的完整时间线**

```
你     ❯ 帮我找和前公司王总的所有消息，从加好友到最后一条

Claude ❯ 最早记录：2021-03-15（入职当天）
         最后一条：2025-01-20
         共 1,203 条，其中你发 612 条，对方发 591 条
```

**为人物 skill 提供原料**

```
你     ❯ 把我和张雪三年内的所有聊天导出来

Claude ❯ 已合并 message_2.db + message_1.db + message_0.db，
         2022-03-15 至 2025-04-01，共 8,203 条，按对话时段分段
         → output/chat_张雪.txt
```

输出的 `chat_张雪.txt` 直接作为前任.skill、同事.skill 的输入原料。

**群聊总结**

```
你     ❯ 把这个群最近一周的消息整理一下

Claude ❯ 已导出 2026-03-27 至 2026-04-03，共 847 条，涉及 23 位成员
```

> 支持文字、图片、语音、视频、表情、位置、通话、引用回复、链接/卡片分享、系统通知（撤回）。

---

## 和 GUI 工具的本质区别

WeFlow、WeChatMsg、PyWxDump 这类工具的逻辑是：**导出文件，交给你**。你拿到一个 HTML 或 TXT，怎么用是你自己的事。

微信.skill 的逻辑是：**Claude 直接读数据库**。没有"导出"这个动作——你在对话里提问，Claude 实时查询、定位、分析，结果直接出现在对话里。

| | GUI 工具 | 微信.skill |
|---|---|---|
| 操作方式 | 打开 App → 点击导出 | 用自然语言对话 |
| 结果 | 一个静态文件 | Claude 的实时回答 |
| 后续处理 | 自己想办法 | 继续追问、分析、整理 |
| 接入 LLM | 额外步骤 | 原生，零距离 |

---

## 工作原理

```mermaid
flowchart LR
    WX["微信 PC 4.x\n登录中"]
    SCR["scripts/auto_scroll.py\n强制加载历史消息"]
    WX -.->|"可选前置步骤"| SCR

    WX -->|"decrypt_db.py\n管理员权限"| DB

    subgraph DB ["wechat-decrypt · decrypted/"]
        direction TB
        C[("contact.db\n联系人")]
        M0[("message_0.db\n最新")]
        Mdot["· · ·"]
        MN[("message_N.db\n最早")]
    end

    DB --> SK

    subgraph SK ["微信.skill"]
        direction TB
        subgraph SL ["skills/"]
            direction LR
            COM["common.md\n公共知识库"]
            SCON["export-contacts.md"]
            SPRI["export-private.md"]
            SGRP["export-chatroom.md"]
            SSUM["summary.md"]
        end
        subgraph SC ["scripts/"]
            direction LR
            PCON["export_contacts.py"]
            PPRI["export_private.py"]
            PGRP["export_chatroom.py"]
        end
        SCON --> PCON
        SPRI --> PPRI
        SGRP --> PGRP
    end

    PCON -->|"联系人排行\n定位导出目标"| PPRI & PGRP
    PPRI -->|"LLM 可读文本"| OUT["前任.skill / 同事.skill\n搜索 / 分析"]
    PGRP --> SSUM
    SSUM -->|"群聊摘要"| OUT
```

解密层由内置的 [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) submodule 完成：从微信进程内存提取密钥，解密 SQLCipher 数据库。微信.skill 负责之后的一切：把解密后的数据接入 Claude，通过 skill 实现完全的 agent 化操作。

---

## 怎么开始

**Step 0 — 克隆本项目**

```bash
git clone --recursive https://github.com/chengmarc/wechat-to-LLM
```

**Step 1 — 解密数据库**

微信需保持登录，以管理员权限运行：

```bash
cd wechat-to-LLM/wechat-decrypt
pip install -r requirements.txt
python main.py decrypt
```

**Step 2 — 安装 Skill**

```bash
cp skills/common.md ~/.claude/skills/
cp skills/export-contacts.md ~/.claude/skills/
cp skills/export-private.md ~/.claude/skills/
cp skills/export-chatroom.md ~/.claude/skills/
cp skills/summary.md ~/.claude/skills/
```

完成。打开 Claude Code，直接用自然语言说你想做什么。

---

## 目录说明

| 目录 | 用途 |
|---|---|
| `wechat-decrypt/` | 解密 submodule（ylytdeng/wechat-decrypt），解密后数据在其 `decrypted/` 子目录 |
| `backup/` | 存放 `all_keys.json` 密钥备份。文件包含数据库加密密钥，已加入 `.gitignore` |
| `output/` | 导出脚本的输出目录，已加入 `.gitignore` |

**环境要求**：Windows / Linux + 微信 PC 4.x。暂不支持 macOS。

**依赖**：Python 3.10+，[zstandard](https://pypi.org/project/zstandard/)（`pip install zstandard`）。

---

## 技术实现

微信 4.x 的消息存储有几个非显然的设计，直接读 SQLite 是拿不到正确数据的：

- **表名混淆**：每个联系人独占一张表，表名是 `Msg_` + MD5(wxid)，没有字典表，需要反向计算
- **多库分片**：同一联系人的历史消息横跨 message_0.db 到 message_N.db，按时间分布，需跨库合并排序
- **appmsg 编码**：引用回复、链接分享等扩展消息存为 zstd 压缩 XML，`local_type` 以 `inner_type × 2³² + 49` 编码，不解压拿到的是乱码
- **系统消息混合帧**：type=10000 部分是完整 zstd 帧，部分是 zstd 帧头后直接拼接明文 XML，需要两路 fallback
- **群聊发送方**：群消息的 `real_sender_id` 不可靠，真实 wxid 嵌在 `message_content` 前缀 `wxid_xxx:\n` 中，需要单独解析

这些都在 `scripts/common.py` 中统一处理，上层脚本和 skill 不需要关心。

---

## 免责声明

本工具仅用于读取**你自己的**微信数据，请遵守相关法律法规，不得用于未经授权的数据访问。

---

<div align="center">

MIT License © [chengmarc](https://github.com/chengmarc)

*数据是你的。读它的权利也是你的。*

</div>
