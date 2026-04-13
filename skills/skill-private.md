---
name: skill-private
description: 从已解密的微信数据库中查询双人会话记录，压缩导出为 LLM 可读文本。当用户需要导出与某人的聊天记录、搜索历史消息、或将双人对话用于 LLM 分析时使用此 skill。
---

# 微信双人会话导出

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

### contact/contact.db — 联系人

**contact 表**有效字段：

| 字段 | 说明 |
|------|------|
| `username` | wxid，用于计算消息表名 |
| `nick_name` | 微信昵称 |
| `remark` | 备注名 |
| `alias` | 用户自设微信号 |

### message/message_0.db — 消息

**Msg_{MD5} 表**：每个联系人一张，表名 = `Msg_` + MD5(wxid)。

有效字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `local_id` | INTEGER PK | 本地自增 id |
| `local_type` | INTEGER | 消息类型 |
| `real_sender_id` | INTEGER | 发送方；双人会话只有两个值 |
| `create_time` | INTEGER | Unix 时间戳（秒） |
| `message_content` | TEXT | 正文；仅 type 1/10000 为明文 |

忽略字段：`upload_status`（全 0）、`compress_content`（全空）、`sort_seq`（≈ create_time×1000）、`WCDB_CT_*`、`source`、`server_id`、`server_seq`。

**local_type 枚举**：

| local_type | 类型 | export_private 输出 |
|---|---|---|
| 1 | 文字 | 原文 |
| 3 | 图片 | `[图片]` |
| 34 | 语音 | `[语音]` |
| 42 | 名片 | `[名片]` |
| 43 | 视频 | `[视频]` |
| 47 | 微信表情 | `[表情]` |
| 48 | 位置 | `[位置]` |
| 50 | 通话 | `[通话]` |
| 10000 | 系统通知（撤回等）| `[撤回了一条消息]` 等 |
| `N × 2³² + 49` | 扩展类型（zstd 压缩 XML）| 自动解码，见下 |

**扩展类型解码规律**：`local_type % 2³² == 49` 的消息均为 zstd 压缩的 appmsg XML，内部 `<type>` 字段决定实际类型：
- `type=57`（引用回复）→ `「引用 {发送方}：{被引用内容}」{回复正文}`
- `type=4/5/…`（链接/卡片分享）→ `[分享] {标题} {URL}`

解码引用和分享消息需安装 `zstandard`（`pip install zstandard`）。

---

## 操作流程

### Step 0：更新解密数据（每次必做，不得跳过）

> **注意**：解密使用 `python decrypt_db.py`，而非 `python main.py`。
> `main.py` 启动的是实时监听模式，不会输出完整的 decrypted/ 目录。

```bash
cd ~/Repo/wechat-decrypt
python decrypt_db.py
```

### Step 1：定位联系人

```bash
sqlite3 ~/Repo/wechat-decrypt/decrypted/contact/contact.db \
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

### Step 3：导出并压缩

微信 4.x 中自己的 `real_sender_id` 固定为 `10`，对方 ID 由脚本自动推断，无需手动确认。

输出文件固定放在 `~/Repo/wechat-to-LLM/output/`，命名为 `chat_{名称}.txt`（`{名称}` 为联系人标识，如 `alice`）。

```bash
# 最简用法（全量导出）
cd ~/Repo/wechat-to-LLM
python scripts/export_private.py \
  --db ~/Repo/wechat-decrypt/decrypted/message/message_0.db \
  --table Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  > output/chat_{名称}.txt

# 最近 7 天
python scripts/export_private.py --db ... --table ... --days 7 > output/chat_{名称}.txt

# 指定日期范围
python scripts/export_private.py --db ... --table ... \
  --since 2024-01-01 --until 2025-01-01 > output/chat_{名称}.txt
```

**参数说明**：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--db` | ✅ | message_0.db 路径 |
| `--table` | ✅ | 消息表名，如 `Msg_xxxx` |
| `--my-id` | | 自己的 real_sender_id，默认 `10` |
| `--other-id` | | 对方的 real_sender_id；省略时自动推断 |
| `--days` | | 最近 N 天；与 `--since` 互斥 |
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
用户：消息内容|
对方：消息内容|

-----------------------
[yy-MM-dd HH:mm]
-----------------------
...
```

相邻消息时间间隔超过阈值（默认 1 小时）则插入新时间段分隔线。
