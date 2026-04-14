---
name: export-private
description: 从已解密的微信数据库中查询双人会话记录，压缩导出为 LLM 可读文本。当用户需要导出与某人的聊天记录、搜索历史消息、或将双人对话用于 LLM 分析时使用此 skill。
---

# 微信双人会话导出

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构、Step 0 和公共参数说明。

## 双人会话特有说明

- `real_sender_id` 可靠。脚本自动推断：两个 sender_id 中**较小的为自己**，较大的为对方（各库实测均符合此规律）。
- 若自动推断结果有误，用 `--my-id` / `--other-id` 手动覆盖。
- 引用回复的发送方由 `other_table_hash`（表名去掉 `Msg_` 前缀，即对方 wxid 的 MD5）自动判断，无需额外操作。

---

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：定位联系人

```bash
cd ~/Repo/wechat-to-LLM
sqlite3 wechat-decrypt/decrypted/contact/contact.db \
  "SELECT username, nick_name, remark, alias FROM contact
   WHERE nick_name LIKE '%关键词%' OR remark LIKE '%关键词%' OR alias LIKE '%关键词%'
   ORDER BY remark;"
```

记录结果中的 `username`（wxid）。

> **DB Browser 备选**：打开 `contact/contact.db` → Execute SQL，执行上述 SQL 去掉 bash 外层。

### Step 2：计算消息表名

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxxxxxxx'.encode()).hexdigest())"
```

### Step 3：确认消息分布在哪些库

> **快捷方式**：`export-contacts` 的输出已包含"所在库"列，可直接跳过此步。

同一联系人的消息可能横跨多个库。查表名在各库中的行数和时间范围：

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

### Step 4：导出

输出文件固定放在 `output/`，命名为 `chat_{名称}.txt`。

`--db` 支持传多个路径，脚本自动按时间戳排序合并，无需手动控制顺序：

```bash
cd ~/Repo/wechat-to-LLM

# 单库
python scripts/export_private.py \
  --db wechat-decrypt/decrypted/message/message_0.db \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  > output/chat_{名称}.txt

# 跨库（直接传多个 --db，顺序无关）
python scripts/export_private.py \
  --db wechat-decrypt/decrypted/message/message_0.db \
      wechat-decrypt/decrypted/message/message_1.db \
      wechat-decrypt/decrypted/message/message_2.db \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  > output/chat_{名称}.txt
```

> **推断失败时**：若报"无法自动推断"错误（例如某库只有单方消息），先查各 ID 的消息内容确认哪个是自己（一般较小的那个），再手动指定 `--my-id` / `--other-id`。

**私聊专有参数**：

| 参数 | 说明 |
|------|------|
| `--my-id` | 自己的 real_sender_id；省略时自动推断（较小值） |
| `--other-id` | 对方的 real_sender_id；省略时自动推断（较大值） |

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