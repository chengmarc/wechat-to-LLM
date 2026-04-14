---
name: common
description: 微信聊天记录导出工具的公共知识库。包含数据库结构、消息类型枚举、Step 0 解密更新、公共脚本参数说明。export-private 和 export-chatroom 均依赖本文件，执行那两个 skill 前必须先读取本文件。
---

# 微信导出工具 — 公共知识库

适用环境：Windows，微信 PC 版 4.x，依赖 `ylytdeng/wechat-decrypt` 完成解密前置步骤。

## 前置条件

参见 `ylytdeng/wechat-decrypt` 完成解密。解密输出位于 `wechat-decrypt/decrypted/`，结构：

```
decrypted/
├── contact/
│   └── contact.db
└── message/
    ├── message_0.db   # 最新
    ├── message_1.db
    └── ...            # 编号不设上限，越大越早
```

---

## Step 0：更新解密数据（每次必做，不得跳过）

> **注意**：解密使用 `python decrypt_db.py`，而非 `python main.py`。
> `main.py` 启动的是实时监听模式，不会输出完整的 decrypted/ 目录。

```bash
cd ~/Repo/wechat-decrypt
python decrypt_db.py
```

解密完成后，建议快速验证各库是否有效（0 张表 = 解密失败，需重跑）：

```bash
python -c "
import sqlite3, glob, os
pattern = os.path.expanduser('~/Repo/wechat-decrypt/decrypted/message/message_*.db')
for db in sorted(glob.glob(pattern)):
    n = sqlite3.connect(db).execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]
    print(f'{os.path.basename(db)}: {n} 张表')
"
```

> **常见问题**：历史失败的解密会留下空文件（0 字节），表现为 0 张表。重跑 `decrypt_db.py` 会覆盖这些文件。

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

### message/message_N.db — 消息（编号不设上限，message_0 最新）

**Msg_{MD5} 表**：每个联系人一张，表名 = `Msg_` + MD5(wxid)。

有效字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `local_id` | INTEGER PK | 本地自增 id |
| `local_type` | INTEGER | 消息类型 |
| `real_sender_id` | INTEGER | 发送方 ID（双人会话可靠，群聊不可靠） |
| `create_time` | INTEGER | Unix 时间戳（秒） |
| `message_content` | TEXT/BLOB | 正文；仅 type 1/10000 为明文 |

忽略字段：`upload_status`（全 0）、`compress_content`（全空）、`sort_seq`（≈ create_time×1000）、`WCDB_CT_*`、`source`、`server_id`、`server_seq`。

---

## local_type 完整枚举

| local_type | 类型 | 导出输出 |
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
| `N × 2³² + 49` | appmsg 扩展类型 | 自动解码，见下 |

### appmsg 扩展类型（`local_type % 2³² == 49`）

所有此类消息均为 **zstd 压缩的 appmsg XML**，内部 `<appmsg><type>N</type>` 决定实际类型：

| appmsg inner type | 类型 | 导出输出 |
|---|---|---|
| 4 | 外链/视频分享（B站等） | `[分享] {title} {url}` |
| 5 | 小程序/图文分享（小红书等）| `[分享] {title} {url}` |
| 57 | 引用回复 | `[引用] [{发送方}：{被引用内容}] {回复正文}` |
| 其他 | 卡片/小程序等 | `[分享] {title}`（无 URL 时） |

编码规律：`local_type = appmsg_inner_type × 2³² + 49`。zstd 魔数：`\x28\xb5\x2f\xfd`（前4字节）。需安装 `zstandard`（`pip install zstandard`）。

### type=10000 系统消息

部分为完整 zstd 压缩数据，部分在 zstd 帧头后**直接拼接明文 XML**（非完整压缩帧）。常见内容：`<sysmsg type="revokemsg">` → `[你撤回了一条消息]` / `[对方撤回了一条消息]`。

---

## 公共脚本参数

两个导出脚本共享以下参数：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--db` | ✅ | message_0.db 路径 |
| `--table` | ✅ | 消息表名，如 `Msg_xxxx` |
| `--days` | | 最近 N 天；与 `--since` 互斥 |
| `--since` | | 起始日期 YYYY-MM-DD |
| `--until` | | 截止日期 YYYY-MM-DD，默认当前时间 |
| `--threshold` | | 时段阈值（秒），默认 3600 |
| `--tz` | | 时区偏移小时数，默认 8 |

进度信息输出到 stderr，正文输出到 stdout，重定向互不干扰。

---

## 输出格式（通用结构）

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
发送方：消息内容|
发送方：消息内容|
```

相邻消息时间间隔超过阈值（默认 1 小时）则插入新时间段分隔线。时间戳为 GMT+8（可通过 `--tz` 调整）。
