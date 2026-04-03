---
name: wechat-decrypt
description: 从PC端微信4.x提取并解密聊天记录数据库，导出为可查询的SQLite文件。当用户需要导出微信聊天记录、查询历史消息、分析对话内容、或将微信数据用于LLM分析时使用此skill。涉及密钥提取、数据库解密、联系人查找、消息查询等任务时均应触发。
---

# WeChat 4.x 聊天记录提取与解密

适用环境：Windows，微信PC版 4.x，Python 3.10+

## 工具链

| 工具 | 用途 | 状态（截至2026-04） |
|------|------|---------------------|
| `ylytdeng/wechat-decrypt` | 批量解密db + Web UI + MCP Server | ✅ 活跃，2025-03更新 |
| DB Browser for SQLite | 手动查询解密后db | ✅ 可用（普通版无密码框） |

**已失效工具（勿用）**：
- `xaoyaoo/PyWxDump`：2025-10收到律师函，已删库
- `LC044/WeChatMsg`：依赖PyWxDump，连带失效；作者转向TrailSnap（AI相册，无关）
- `SuxueCode/WechatBakTool`：停止更新，不支持4.x
- `xaoyaoo/PyWxDumpMini`：偏移量表停留在3.x，4.x识别不到进程

---

## 数据库结构

解密输出位于 `wechat-decrypt/decrypted/`，均为标准 SQLite 文件。

### message_0.db

**Name2Id 表**：wxid → 消息表映射

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_name` | TEXT PK | wxid，MD5后即对应 Msg_* 表名 |
| `is_session` | INTEGER | 是否为会话 |

**{Msg_MD5} 表**：每个联系人一张，表名 = `Msg_` + MD5(wxid)

有效字段（其余可忽略）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `local_id` | INTEGER PK | 本地自增id |
| `local_type` | INTEGER | 消息类型，见下表 |
| `real_sender_id` | INTEGER | 发送方，双人会话只有两个值 |
| `create_time` | INTEGER | Unix时间戳（秒） |
| `message_content` | TEXT | 正文；仅 type 1/10000 为明文，其余为压缩数据 |

忽略字段：`upload_status`（全0）、`compress_content`（全空）、`origin_source`（全2）、`WCDB_CT_*`（索引列）、`sort_seq`（≈ create_time×1000）、`source`/`server_id`/`server_seq`（服务端元数据）。`status` 只有 3/4 两值，含义待确认。

**local_type 枚举**：

| local_type | 类型 | message_content 可读性 |
|---|---|---|
| 1 | 文字 | ✅ 明文 |
| 3 | 图片 | ❌ 压缩数据 |
| 34 | 语音 | ❌ 压缩数据 |
| 42 | 名片 | ❌ 压缩数据 |
| 43 | 视频 | ❌ 压缩数据 |
| 47 | 微信表情 | ❌ 压缩数据 |
| 48 | 位置 | ❌ 压缩数据 |
| 50 | 通话 | ❌ 压缩数据 |
| 10000 | 系统通知（撤回、加好友等） | ✅ 明文 |
| 其余大数字 | 扩展类型（含引用、小程序分享等），待识别 | ❌ 压缩数据 |

只有 `local_type IN (1, 10000)` 的 `message_content` 可直接阅读或送入 LLM。

### contact.db

**contact 表**

有效字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `username` | TEXT | wxid，用于计算消息表名 |
| `nick_name` | TEXT | 微信昵称 |
| `remark` | TEXT | 备注名 |
| `alias` | TEXT | 用户自设微信号（如 `monkeykingg630`） |

忽略字段：`chat_room_*`、`delete_flag`、`head_img_md5`、`is_in_chat_room`、`verify_flag`（全0/空）；`big_head_url`、`small_head_url`、`encrypt_username`、`extra_buffer`（有值但查询不需要）。

### 首次验证（PRAGMA）

```sql
-- message_0.db
PRAGMA table_info(Name2Id);
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';
PRAGMA table_info(Msg_027779fd3f739dfd78a948752cda0a44);  -- 任意一张

-- contact/contact.db
PRAGMA table_info(contact);
```

---

## 操作流程

### 前置条件

- 微信PC版已登录（解密期间保持运行）
- 管理员权限终端

```bash
git config --global http.proxy http://127.0.0.1:7897  # 如需代理
cd ~/Repo
git clone https://github.com/ylytdeng/wechat-decrypt
cd wechat-decrypt
pip install -r requirements.txt
python main.py decrypt
```

微信4.x数据目录默认位置：`C:\Users\{用户名}\xwechat_files\`（非Documents，与3.x不同）。在微信 → 设置 → 文件管理中确认实际路径。解密完成后输出至 `wechat-decrypt/decrypted/`。

### Step 1：从 contact.db 定位联系人

```sql
-- contact/contact.db
WITH params AS (SELECT '%关键词%' AS kw)
SELECT username, nick_name, remark, alias FROM contact, params
WHERE (alias != '' OR remark != '')
  AND (nick_name LIKE kw OR remark LIKE kw OR alias LIKE kw)
ORDER BY remark;
```

结果中的 `username` 即 wxid，格式通常为 `wxid_xxxxxxxx` 或 `数字@chatroom`。

### Step 2：定位消息表

**2a. 计算表名**

```bash
python -c "import hashlib; print('Msg_' + hashlib.md5('wxid_xxxxxxxx'.encode()).hexdigest())"
```

**2b. 确认 real_sender_id 映射**

```sql
-- message_0.db
SELECT real_sender_id, message_content FROM {Msg_MD5}
WHERE local_type = 1 LIMIT 10;
```

### Step 3：查询消息

**基础查询**

```sql
SELECT local_type, real_sender_id, create_time, message_content
FROM {Msg_MD5}
WHERE local_type = 1
ORDER BY create_time DESC;
```

**按时间范围过滤**

```sql
SELECT local_type, real_sender_id, create_time, message_content
FROM {Msg_MD5}
WHERE local_type = 1
  AND create_time >= strftime('%s', '2026-03-01')
  AND create_time <  strftime('%s', '2026-04-01')
ORDER BY create_time DESC;
```

**导出双人对话（适合 LLM 分析）**

```sql
SELECT
    create_time,
    substr(strftime('%Y-%m-%d %H:%M', create_time, 'unixepoch', '+8 hours'), 3) AS time,
    CASE real_sender_id
        WHEN 10 THEN '用户'
        WHEN 1781 THEN '对方'
    END AS sender,
    message_content
FROM {Msg_MD5}
WHERE local_type = 1
ORDER BY create_time ASC;
```

`real_sender_id` 映射值从 Step 2b 确认后替换。

### Step 3：压缩为 LLM 可读格式

执行导出对话 SQL 后，在 DB Browser 底部结果区点击 **File → Export → Table as JSON**，保存为 `export.json`。

将 DB Browser 导出的 JSON 处理为紧凑对话文本，相邻消息时间间隔不超过1小时则省略时间戳。

```python
import json, sys

# 期望 JSON 字段：create_time, time, sender, message_content
THRESHOLD = 3600  # 秒，同一时段阈值

with open(sys.argv[1], encoding='utf-8') as f:
    messages = json.load(f)

output = []
last_time = None

for msg in messages:
    ts = msg['create_time']
    if last_time is None or ts - last_time > THRESHOLD:
        output.append(f"\n\n-----------------------\n[{msg['time']}]\n-----------------------")
    last_time = ts
    output.append(f"{msg['sender']}：{msg['message_content']}|")

print('\n'.join(output))
```

```bash
python compress.py export.json > chat.txt
```

---

## 技术背景

微信4.x使用SQLCipher 4加密：AES-256-CBC + HMAC-SHA512，KDF为PBKDF2-HMAC-SHA512（256,000次迭代），页面大小4096字节。`wechat-decrypt` 通过扫描进程内存匹配 `x'<64hex_enc_key><32hex_salt>'` 格式提取raw key，绕过偏移量依赖，因此对所有4.x版本均有效。

DB Browser for SQLCipher无法直接打开这些db（加密参数非标准），应使用 `wechat-decrypt` 解密后再用普通DB Browser查询。
