---
name: export-contacts
description: 按消息量扫描所有联系人，列出超过阈值的重要联系人。当用户想知道"和谁聊得最多"、"找出重要联系人"、"按聊天量排名"时使用此 skill。
---

# 微信重要联系人扫描

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构和 Step 0。

## 说明

扫描所有已解密的消息库，统计每个联系人的消息总量，过滤出超过阈值的重要联系人并按量排序。同一联系人的消息可能分散在多个库中，建议传入全部库以得到完整计数。

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：查找联系人

```bash
cd ~/Repo/wechat-to-LLM
python scripts/find_contact.py <关键词>
```

输出：wxid、消息表名、各库消息量及日期范围，以及一条即用的 `export_contacts.py` 命令。

### Step 2：运行导出命令

> **必须重定向到文件，禁止裸跑。** stdout 和 stderr 均不得进入上下文窗口。

```bash
python scripts/export_contacts.py \
  --contact-db wechat-decrypt/decrypted/contact/contact.db \
  --msg-dbs wechat-decrypt/decrypted/message/message_*.db \
  > output/contacts.txt 2>&1
```

时间范围无关（`export_contacts.py` 统计全量消息数），可调整 `--threshold` 过滤阈值：

| 参数 | 说明 |
|------|------|
| `--threshold N` | 最低消息数阈值，默认 50 |
| `--include-chatrooms` | 同时显示群聊 |
