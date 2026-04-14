---
name: common
description: 微信聊天记录导出工具的公共知识库。包含数据库结构、消息类型说明、Step 0 解密更新和公共脚本参数说明。export-private、export-chatroom、export-contacts 均依赖本文件，执行那些 skill 前必须先读取本文件。
---

# 微信导出工具 — 公共知识库

适用环境：Windows，微信 PC 版 4.x，依赖内置 submodule `wechat-decrypt/` 完成解密前置步骤。

---

## 数据库结构

解密后文件位于 `wechat-decrypt/decrypted/`（相对于项目根目录）：

- `contact/contact.db`：联系人表，字段 `username`（wxid）/ `nick_name` / `remark` / `alias`
- `message/message_N.db`：消息库（N 从 0 开始，0 为最新，编号越大越早）；每个联系人一张表，表名 = `Msg_` + MD5(wxid)

消息表有效字段：`local_id` / `local_type` / `real_sender_id` / `create_time`（Unix 秒）/ `message_content`

## 消息类型 → 导出输出

**基础类型**

| local_type | 类型 | 导出输出 |
|---|---|---|
| 1 | 文字 | 原文 |
| 3 | 图片 | `[图片]` |
| 34 | 语音 | `[语音]` |
| 42 | 名片 | `[名片]` |
| 43 | 视频 | `[视频]` |
| 47 | 微信表情（内置） | `[表情]` |
| 48 | 位置 | `[位置]` |
| 50 | 通话 | `[通话]` |
| 10000 | 系统通知 | `[撤回了一条消息]` 等 |

**appmsg 扩展类型**（编码规律：`local_type = inner_type × 2³² + 49`）

| inner type | local_type | 类型 | 导出输出 |
|---|---|---|---|
| 4 | 17179869233 | 外链/视频分享（B站等） | `[分享] title url` |
| 5 | 21474836529 | 图文分享（小红书等） | `[分享] title url` |
| 6 | 25769803825 | 文件 | `[分享] title` |
| 8 | 34359738417 | 文件（含自定义表情包） | `[文件]` |
| 19 | 81604378673 | 聊天记录 | `[分享] title` |
| 24 | 103079215153 | 文件 | `[文件]` |
| 33 | 141733920817 | 小程序 | `[分享] title` |
| 36 | 154618822705 | 小程序 | `[分享] title` |
| 57 | 244813135921 | 引用回复 | `[引用] 「sender：内容」 正文` |
| 62 | 266287972401 | 拍一拍 | `[拍一拍]` |
| 2000 | 8589934592049 | 转账 | `[分享] title` |
| 2001 | 8594229559345 | 红包 | `[分享] title` |
| 其他 | `N×2³²+49` | 视频号/群公告/礼物等 | `[分享] title`（无 title 时跳过） |

## 双人 vs 群聊关键差异

**双人会话**：`real_sender_id` 可靠。脚本自动推断发送方（较小 ID 为自己）；推断失败时用 `--my-id` / `--other-id`。

**群聊**：type=1 消息的真实 wxid 嵌在内容前缀 `wxid_xxx:\n`，`real_sender_id` 不可靠。非文字消息的 `real_sender_id` 是同库 `Name2Id` 表的 rowid，可反查 wxid 后映射显示名；仅无法反查时标 `【?】`。

## 输出格式

**双人会话**（发送方固定为 `用户` / `对方`）：

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
【用户】：消息内容 ⏎
【对方】：消息内容 ⏎
```

**群聊**（发送方用 `【】` 包裹，`【?】` 表示非文字消息）：

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
【昵称】：消息内容 ⏎
【?】：消息内容 ⏎
```

---

## Step 0：更新解密数据（每次必做，不得跳过）

> **注意**：解密使用 `python decrypt_db.py`，而非 `python main.py`。
> `main.py` 启动的是实时监听模式，不会输出完整的 decrypted/ 目录。

```bash
cd ~/Repo/wechat-to-LLM

# 如果 backup/all_keys.json 存在且 wechat-decrypt/all_keys.json 不存在，先复制
cp backup/all_keys.json wechat-decrypt/all_keys.json

cd wechat-decrypt && python decrypt_db.py && cd ..
```

`all_keys.json` 已列入 `wechat-decrypt/.gitignore`，复制后不会被提交。

解密完成后，建议快速验证各库是否有效（0 张表 = 解密失败，需重跑）：

```bash
python -c "
import sqlite3, glob, os
pattern = 'wechat-decrypt/decrypted/message/message_*.db'
for db in sorted(glob.glob(pattern)):
    n = sqlite3.connect(db).execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]
    print(f'{os.path.basename(db)}: {n} 张表')
"
```

> **常见问题**：历史失败的解密会留下空文件（0 字节），表现为 0 张表。重跑 `decrypt_db.py` 会覆盖这些文件。

---

## 公共脚本参数

两个导出脚本（export_private.py / export_chatroom.py）共享以下参数：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--db` | ✅ | message_N.db 路径 |
| `--table` | ✅ | 消息表名，如 `Msg_xxxx` |
| `--days` | | 最近 N 天；与 `--since` 互斥 |
| `--since` | | 起始日期 YYYY-MM-DD |
| `--until` | | 截止日期 YYYY-MM-DD，默认当前时间 |
| `--threshold` | | 时段阈值（秒），默认 3600 |
| `--tz` | | 时区偏移小时数，默认 8 |

进度信息输出到 stderr，正文输出到 stdout，重定向互不干扰。
