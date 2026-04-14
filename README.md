<div align="center">

# 微信.skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-blueviolet)](https://claude.ai)
[![WeChat 4.x](https://img.shields.io/badge/WeChat-4.x-brightgreen)](https://weixin.qq.com)

**让 Claude 在本地读懂你的微信。**

</div>

---

同事.skill、前任.skill、女娲.skill——这一波 skill 热潮背后，有一个共同的上游问题：

**我他妈到底怎么把微信聊天记录喂进去？**

微信的数据库是加密的，表名是混淆的，消息横跨多个分片库，引用回复是压缩编码。你拿到的不是可读文本，是一堆打不开的文件。

**微信.skill** 解决这个问题。解密、查询、导出，全部在本地运行，数据不离机。而且不止于此。

## Agent Native

其他所谓的 Skill 其实是一个 Prompt 文件，丢给你，然后你自己想办法。

微信.skill 的设计目标不是文件，是**让 Claude 直接读懂你的微信**。所有 SQL 查询在本地运行，Claude 通过 Skill 调度脚本，结果实时返回对话——查询、搜索、分析、整理，全部原地完成，不需要任何中间步骤。

**为前任.skill / 同事.skill / 女娲.skill 准备原材料**

```
你     ❯ 把我和张雪三年的聊天整理出来，给前任.skill 用

Claude ❯ 已跨 message_0.db + message_1.db + message_2.db 合并，
         2022-03-15 至 2025-04-01，共 8,203 条，按对话时段分段
         → output/chat_张雪.txt ✓
```

**找那条你记得但搜不到的消息**

```
你     ❯ 帮我找和李明的聊天，他说过"我不会走的"，大概是去年冬天

Claude ❯ 2024-12-07
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

> 支持文字、引用回复、链接/卡片分享、语音、图片、位置、通话、撤回消息，微信 4.x 全兼容。

## 为什么其他工具不够

微信 4.x 的数据有几个非显然的设计，直接读是拿不到正确结果的：

- **加密**：SQLCipher 加密，密钥在微信进程内存里，需要运行时提取
- **表名混淆**：联系人表名 = `Msg_` + MD5(wxid)，没有字典表，需要反向计算
- **多库分片**：同一联系人的消息横跨 message_0.db 到 message_N.db，需要跨库合并排序
- **appmsg 编码**：引用回复、链接分享存为 zstd 压缩 XML，`local_type` 以 `inner_type × 2³² + 49` 编码，不解压是乱码
- **群聊发送方**：`real_sender_id` 字段不可靠，真实 wxid 嵌在消息内容前缀 `wxid_xxx:\n` 中，需要单独解析

这些全部在 `scripts/common.py` 统一处理，Skill 层和上层脚本不需要关心。

## 怎么开始

**Step 0 — 克隆本项目**

```bash
git clone --recursive https://github.com/chengmarc/wechat-to-LLM
```

**Step 1 — 解密数据库**

微信保持登录，以管理员权限运行：

```bash
cd wechat-to-LLM/wechat-decrypt
pip install -r requirements.txt
python main.py decrypt
```

**Step 2 — 安装 Skill**

```bash
cp skills/*.md ~/.claude/skills/
```

完成。打开 Claude Code，直接说你想做什么。

## 目录说明

| 目录 | 用途 |
|---|---|
| `wechat-decrypt/` | 解密 submodule `ylytdeng/wechat-decrypt`，解密后数据在其 `decrypted/` 子目录 |
| `backup/` | 存放 `all_keys.json` 密钥备份，已加入 `.gitignore` |
| `output/` | 导出脚本的输出目录，已加入 `.gitignore` |

**环境要求**：Windows + 微信 PC 4.x，Linux 未测试，暂不支持 macOS。

**依赖**：Python 3.10+，[zstandard](https://pypi.org/project/zstandard/)（`pip install zstandard`），sqlite3（标准库，精简 Linux 镜像需额外安装 `python3-sqlite3`）。

## 免责声明

本工具仅用于 **在本地** 读取 **你自己的** 微信数据，请遵守相关法律法规，不得用于未经授权的数据访问。

数据库解密技术由 **开源仓库** `ylytdeng/wechat-decrypt` 提供，本工具 **没有** 进行任何解密相关的工作，本工具仅提供 **Agent Native** 的 **数据库查询** 封装。

---

<br>

<div align="center">

MIT License © [chengmarc](https://github.com/chengmarc)

*数据是你的。读它的权利也是你的。*

</div>
