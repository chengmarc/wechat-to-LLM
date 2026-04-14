---
name: export-private
description: 从已解密的微信数据库中查询双人会话记录，压缩导出为 LLM 可读文本。当用户需要导出与某人的聊天记录、搜索历史消息、或将双人对话用于 LLM 分析时使用此 skill。
---

# 微信双人会话导出

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构、Step 0 和公共参数说明。

## 双人会话特有说明

- `real_sender_id` 可靠，但同一人在不同消息库中的 ID 数值不同，不可跨库比较。
- 发送方映射通过 `--sender-map sender_map.json` 管理（每库独立一条）。文件不存在时脚本自动推断并写出 JSON 后退出，用户核对后重新运行导出。
- JSON 每条含 `_samples` 字段（各 sender_id 的采样消息），便于人工判断谁是用户、谁是对方；`_samples` 只读不写，导出时自动忽略。
- 引用回复的发送方由 `other_table_hash`（表名去掉 `Msg_` 前缀，即对方 wxid 的 MD5）自动判断，无需额外操作。

---

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：定位联系人

```bash
cd ~/Repo/wechat-to-LLM
python -c "
import sqlite3
conn = sqlite3.connect('wechat-decrypt/decrypted/contact/contact.db')
for r in conn.execute(\"SELECT username, nick_name, remark, alias FROM contact WHERE nick_name LIKE '%关键词%' OR remark LIKE '%关键词%' OR alias LIKE '%关键词%' ORDER BY remark\"):
    print(r)
"
```

记录结果中的 `username`（wxid）。

### Step 2：计算消息表名

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxxxxxxx'.encode()).hexdigest())"
```

### Step 3：确认消息分布在哪些库

> **快捷方式**：`export-contacts` 的输出已包含"所在库"列，可直接跳过此步。

```bash
python -c "
import sqlite3, glob, os
from datetime import datetime, timezone, timedelta
tz = timezone(timedelta(hours=8))
table = 'Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
base = 'wechat-decrypt/decrypted/message'
for db in sorted(glob.glob(os.path.join(base, 'message_*.db'))):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name=?', (table,))
    if cur.fetchone():
        cur.execute(f'SELECT MIN(create_time), MAX(create_time), COUNT(*) FROM {table}')
        mn, mx, cnt = cur.fetchone()
        print(f'{os.path.basename(db)}: {cnt} 条  {datetime.fromtimestamp(mn,tz).strftime(\"%Y-%m-%d\")} ~ {datetime.fromtimestamp(mx,tz).strftime(\"%Y-%m-%d\")}')
    else:
        print(f'{os.path.basename(db)}: (无此表)')
    conn.close()
"
```

### Step 4：生成 sender_map.json 并核对

首次运行时文件不存在，脚本自动推断写出后退出：

```bash
cd ~/Repo/wechat-to-LLM
python scripts/export_private.py \
  --db wechat-decrypt/decrypted/message/message_0.db \
      [其他库...] \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --sender-map output/sender_map_{名称}.json
```

打开生成的 JSON，对照 `_samples` 中的消息内容核对每个库的 `my_id`（用户）和 `other_id`（对方）是否正确，如有误直接修改数值后保存。

sender_map.json 格式：

```json
[
  {"db": "message_7.db", "my_id": 1, "other_id": 2, "_samples": {"1": ["..."], "2": ["..."]}},
  {"db": "message_6.db", "my_id": 2, "other_id": 7, "_samples": {"2": ["..."], "7": ["..."]}}
]
```

### Step 5：导出

```bash
cd ~/Repo/wechat-to-LLM
python scripts/export_private.py \
  --db wechat-decrypt/decrypted/message/message_0.db \
      [其他库...] \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --sender-map output/sender_map_{名称}.json \
  > output/chat_{名称}.txt
```

公共参数（`--db`、`--table`、`--days`、`--since`、`--until`、`--threshold`、`--tz`）参见 `common.md`。

---

## 输出格式

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
【用户】：消息内容 ⏎
【对方】：消息内容 ⏎
```

发送方标签：自己 → `用户`，对方 → `对方`。
