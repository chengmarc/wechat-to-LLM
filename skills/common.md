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

**双人会话**：`real_sender_id` 可靠。脚本自动推断发送方：主信号为跨表出现频率（用户在同一 DB 内更多 Msg_* 表中出现），回退为较小 ID；推断结果附 `_infer_method` 字段（`cross-table` 或 `min-id`）。推断有误时手动编辑 sender_map.json 后重新运行。

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

**群聊**（发送方用 `【】` 包裹，`【?】` 表示无法反查发送方）：

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

> **首次使用 / 无备份**：若 `backup/all_keys.json` 不存在，需先在微信运行时提取密钥：
> ```bash
> cd ~/Repo/wechat-to-LLM/wechat-decrypt && python find_all_keys.py
> ```
> 提取成功后将生成的 `all_keys.json` 复制到 `backup/` 留存，再运行 `decrypt_db.py`。

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
| `--db` | ✅ | message_N.db 路径（export_private.py 可传多个，export_chatroom.py 只接受单个） |
| `--table` | ✅ | 消息表名，如 `Msg_xxxx` |
| `--days` | | 最近 N 天；与 `--since` 互斥 |
| `--since` | | 起始日期 YYYY-MM-DD |
| `--until` | | 截止日期 YYYY-MM-DD，默认当前时间 |
| `--threshold` | | 时段阈值（秒），默认 3600 |
| `--tz` | | 时区偏移小时数，默认 8 |

export_private.py 专有参数：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--sender-map` | ✅ | sender_map.json 路径；不存在时自动推断并写出后退出，存在时直接读取 |

export_chatroom.py 专有参数：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--id-map` | ✅ | id_map.json 路径；存储 wxid → 昵称映射 |
| `--contact-db` | | contact.db 路径；提供时自动从消息表提取 wxid 并生成/更新 id_map.json |

## 输出路径约定

**`export_*.py` 的输出（stdout + stderr）严禁进入上下文窗口。** 执行时必须将两个流一并重定向到 `output/`：

```bash
python scripts/export_xxx.py ... > output/<文件名>.txt 2>&1
```

`find_*.py` 的输出可正常进入上下文。

find 脚本（find_private.py / find_chatroom.py / find_contact.py）共享以下参数：

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `keyword` | ✅ | 搜索关键词（匹配 nick_name / remark） |
| `--contact-db` | | contact.db 路径，默认 `wechat-decrypt/decrypted/contact/contact.db` |
| `--msg-dbs` | | 消息库路径列表，默认自动 glob `message_*.db` |
| `--tz` | | 时区偏移小时数，默认 8；影响库扫描时显示的日期范围 |
