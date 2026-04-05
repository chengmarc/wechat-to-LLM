---
name: skill-chatroom
description: 从已解密的微信数据库中提取群聊记录，输出为 LLM 可读的压缩文本。当用户需要导出群聊内容、生成群聊总结、或分析群内对话时使用此 skill。
---

# 微信群聊导出

适用环境：Windows，微信 PC 版 4.x，依赖 `ylytdeng/wechat-decrypt` 完成解密前置步骤。

## 前置条件

参见 `ylytdeng/wechat-decrypt` 完成解密。解密输出位于 `wechat-decrypt/decrypted/`，结构：

```
decrypted/
├── contact/
│   └── contact.db
└── message/
    └── message_0.db
```

---

## 数据库结构

### 群聊与双人会话的区别

群聊的 `message_content` 字段为 BLOB，格式为：

```
wxid_xxx:\n正文内容
```

`real_sender_id` 在群聊中不可靠，真实发送者 wxid 嵌在内容前缀中，需手动解析。SQLite 中 `':\n'` 字面量无效，需用 `char(58,10)` 替代。

### 定位群聊表名

群 username 格式为 `数字@chatroom`，在 contact.db 中查询：

```bash
sqlite3 ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
  "SELECT username, nick_name, remark FROM contact
   WHERE username LIKE '%@chatroom%'
     AND (nick_name LIKE '%关键词%' OR remark LIKE '%关键词%');"
```

消息表名 = `Msg_` + MD5(群 username)：

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('12345678@chatroom'.encode()).hexdigest())"
```

---

## 操作流程

### Step 0：更新解密数据（每次必做，不得跳过）

> **注意**：解密使用 `python decrypt_db.py`，而非 `python main.py`。
> `main.py` 启动的是实时监听模式，不会输出完整的 decrypted/ 目录。

```bash
cd ~/Repo/wechat-decrypt
python decrypt_db.py
```

### Step 1：构建 id_map（新群或有新成员时需要更新）

**1a. 从消息内容提取全量 wxid**

```bash
sqlite3 ~/Repo/wechat-decrypt/decrypted/message/message_0.db \
  "SELECT DISTINCT
       substr(message_content, 1, instr(message_content, char(58,10)) - 1) AS wxid
   FROM {Msg_MD5}
   WHERE local_type = 1
     AND instr(message_content, char(58,10)) > 0
   ORDER BY wxid;"
```

记录所有 wxid。

**1b. 查询昵称，生成 id_map.json**

```bash
sqlite3 -json ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
  "SELECT username, nick_name, remark FROM contact
   WHERE username IN ('wxid_aaa', 'wxid_bbb', ...);" \
  > ~/Repo/wechat-to-LLM/output/id_map_{名称}.json
```

`id_map.json` 格式（sqlite3 -json 直接输出）：

```json
[
  { "username": "wxid_xxx", "nick_name": "昵称", "remark": "备注" },
  ...
]
```

显示优先级：`nick_name` 非空则显示昵称，否则显示 `username`。

> **DB Browser 备选**：Execute SQL 执行上述查询，底部结果区 → File → Export → Table as JSON，保存为 `~/Repo/wechat-to-LLM/output/id_map_{名称}.json`。

### Step 2：运行导出脚本

输出文件固定放在 `~/Repo/wechat-to-LLM/output/`，命名为 `chat_{名称}.txt`，`id_map` 同目录。

```bash
cd ~/Repo/wechat-to-LLM
python scripts/export_chatroom.py \
  --db ~/Repo/wechat-decrypt/decrypted/message/message_0.db \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --id-map output/id_map_{名称}.json \
  > output/chat_{名称}.txt

# 最近7天
python scripts/export_chatroom.py --db ... --table ... --id-map output/id_map_{名称}.json --days 7 > output/chat_{名称}.txt

# 指定日期范围
python scripts/export_chatroom.py --db ... --table ... --id-map output/id_map_{名称}.json \
  --since 2026-03-01 --until 2026-04-01 > output/chat_{名称}.txt
```

**参数说明**：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--db` | ✅ | message_0.db 路径 |
| `--table` | ✅ | 消息表名，如 `Msg_xxxx` |
| `--id-map` | ✅ | id_map.json 路径 |
| `--days` | | 最近 N 天，默认 1；与 `--since` 互斥 |
| `--since` | | 起始日期 YYYY-MM-DD |
| `--until` | | 截止日期 YYYY-MM-DD，默认当前时间 |
| `--threshold` | | 时段阈值（秒），默认 3600 |
| `--tz` | | 时区偏移小时数，默认 8 |

进度信息输出到 stderr，正文输出到 stdout，重定向互不干扰。

---

## 输出格式

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
【昵称】：消息内容|
【昵称】：消息内容|

-----------------------
[yy-MM-dd HH:mm]
-----------------------
...
```

时间戳为 GMT+8（可通过 `--tz` 调整）。相邻消息间隔超过阈值则插入新分隔线。未在 id_map 中的发送者直接显示 wxid。