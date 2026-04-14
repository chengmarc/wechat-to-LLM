---
name: export-chatroom
description: 从已解密的微信数据库中提取群聊记录，输出为 LLM 可读的压缩文本。当用户需要导出群聊内容、生成群聊总结、或分析群内对话时使用此 skill。
---

# 微信群聊导出

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构、Step 0 和公共参数说明。

## 群聊特有说明

- `real_sender_id` 不可靠。真实发送者 wxid 嵌在 `message_content` 前缀中：`wxid_xxx:\n正文内容`。
- 非文字消息（图片、引用等）无 wxid 前缀，发送方标注为 `【?】`。
- 群 username 格式：`数字@chatroom`（如 `12345678@chatroom`）。

---

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：定位群聊表名

```bash
# 1a. 在 contact.db 中查找群聊
sqlite3 ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
  "SELECT username, nick_name, remark FROM contact
   WHERE username LIKE '%@chatroom%'
     AND (nick_name LIKE '%关键词%' OR remark LIKE '%关键词%');"

# 1b. 计算消息表名
python -c "import hashlib; print('Msg_' + hashlib.md5('12345678@chatroom'.encode()).hexdigest())"
```

### Step 2：构建 id_map（新群或有新成员时更新）

**2a. 从消息内容提取全量 wxid**

```bash
sqlite3 ~/Repo/wechat-decrypt/decrypted/message/message_0.db \
  "SELECT DISTINCT
       substr(message_content, 1, instr(message_content, char(58,10)) - 1) AS wxid
   FROM {Msg_MD5}
   WHERE local_type = 1
     AND instr(message_content, char(58,10)) > 0
   ORDER BY wxid;"
```

**2b. 查询昵称，生成 id_map.json**

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

### Step 3：导出

输出文件固定放在 `~/Repo/wechat-to-LLM/output/`，命名为 `chat_{名称}.txt`。

```bash
cd ~/Repo/wechat-to-LLM

# 最近 1 天（默认）
python scripts/export_chatroom.py \
  --db ~/Repo/wechat-decrypt/decrypted/message/message_0.db \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --id-map output/id_map_{名称}.json \
  > output/chat_{名称}.txt

# 最近 7 天
python scripts/export_chatroom.py --db ... --table ... --id-map output/id_map_{名称}.json \
  --days 7 > output/chat_{名称}.txt

# 指定日期范围
python scripts/export_chatroom.py --db ... --table ... --id-map output/id_map_{名称}.json \
  --since 2026-03-01 --until 2026-04-01 > output/chat_{名称}.txt
```

**群聊专有参数**：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--id-map` | ✅ | id_map.json 路径 |
| `--days` | | 最近 N 天，**默认 1**（群聊消息量大，不建议全量） |

公共参数（`--db`、`--table`、`--since`、`--until`、`--threshold`、`--tz`）参见 `common.md`。

---

## 输出格式

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
【昵称】：消息内容 ⏎
【昵称】：消息内容 ⏎
```

发送方标签：`【昵称】`（在 id_map 中）或 `【原始 wxid】`（不在 id_map 中）；非文字消息 → `【?】`。
