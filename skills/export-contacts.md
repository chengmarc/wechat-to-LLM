---
name: export-contacts
description: 按消息量扫描所有联系人，列出超过阈值的重要联系人，并引导用户选择导出。当用户想知道"和谁聊得最多"、"找出重要联系人"、"按聊天量排名"时使用此 skill。
---

# 微信重要联系人扫描

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构和 Step 0。

## 说明

扫描所有已解密的消息库（message_0.db、message_1.db……编号不设上限，message_0 最新、编号越大越早），统计每个联系人的消息总量，过滤出超过阈值的重要联系人并按量排序。同一联系人的消息可能分散在多个库中，建议传入全部库以得到完整计数。

---

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：扫描并列出重要联系人

```bash
cd ~/Repo/wechat-to-LLM
python scripts/export_contacts.py \
  --contact-db ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
  --msg-dbs ~/Repo/wechat-decrypt/decrypted/message/message_*.db \
  --threshold 100
```

> shell glob `message_*.db` 会自动展开为目录下所有消息库，无需手动列举编号。

**参数说明**：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--contact-db` | ✅ | contact.db 路径 |
| `--msg-dbs` | ✅ | 消息库路径列表（空格分隔，可传多个） |
| `--threshold` | | 最低消息数阈值，默认 50 |
| `--include-chatrooms` | | 同时显示群聊（默认只显示双人会话） |

**输出格式**：

```
 #  消息数  显示名    wxid            消息表
--------------------------------------------------------------------
 1    4821  张雪      wxid_abc...     Msg_xxxxxxxx...
 2    1203  王总      wxid_def...     Msg_yyyyyyyy...
```

进度（扫描哪个库）输出到 stderr，结果表格输出到 stdout。

### Step 2：按需导出

根据上一步的结果，选择联系人后使用 `export-private` 导出。

> **重要**：export-contacts 的消息数是跨所有库的合计，但 export-private 每次只能指定一个 `--db`。导出前先确认该联系人的表在哪些库里有数据（见 export-private 跨库合并流程）。

若列表中有群聊（使用 `--include-chatrooms` 时出现），用 `export-chatroom` 导出。
