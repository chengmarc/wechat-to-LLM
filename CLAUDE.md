# wechat-to-LLM

微信 4.x 聊天记录解密导出工具，输出 LLM 可读压缩文本。解密能力来自 `ylytdeng/wechat-decrypt`，本项目提供 Claude Skill、导出脚本和 DB schema 文档。

## 项目结构

```
scripts/
  common.py            # 共用工具：时间参数解析、进度日志、compress()
  export_private.py    # 双人会话导出脚本
  export_chatroom.py   # 群聊导出脚本
skills/
  skill-private.md     # Claude Skill：双人会话
  skill-chatroom.md    # Claude Skill：群聊
```

`common.py` 提供：`add_time_args` / `resolve_time_range` / `log_time_range` / `compress`。
`compress(messages, format_fn, threshold, tz)` 接受回调 `format_fn(msg) -> (sender, content) | None`，返回 `(text, skipped_count)`。

## 数据库结构

解密后两个 SQLite 库，位于 `wechat-decrypt/decrypted/`：

- `contact/contact.db`：联系人表，字段 `username`（wxid）/ `nick_name` / `remark` / `alias`
- `message/message_0.db`：消息库，每个联系人一张表，表名 = `Msg_` + MD5(wxid)

消息表有效字段：`local_id` / `local_type` / `real_sender_id` / `create_time`（Unix 秒）/ `message_content`

只有 `local_type IN (1, 10000)` 的 `message_content` 为明文（文字消息 + 系统通知）。

## 双人 vs 群聊的关键差异

**双人会话**：`real_sender_id` 可靠，直接用于区分发送方。

**群聊**：`real_sender_id` 不可靠，真实发送者 wxid 嵌在 `message_content` 前缀：

```
wxid_xxx:\n正文内容
```

解析时用 `":\n"` 分割，前缀需满足 `[\w\-]{1,64}`。SQLite 中字面量 `':\n'` 无效，用 `char(58,10)` 替代。

## 导出脚本约定

- 进度信息 → `stderr`，正文 → `stdout`，重定向互不干扰
- 时段分隔：相邻消息间隔超过 `--threshold`（默认 3600 秒）则插入分隔线
- 默认时区 GMT+8，可用 `--tz` 调整
- 时间过滤三选一：`--days N` / `--since YYYY-MM-DD` / 不填（私聊全量，群聊默认 1 天）

## 输出格式

```
-----------------------
[yy-MM-dd HH:mm]
-----------------------
用户：消息内容|
对方：消息内容|
```

群聊发送者用 `【昵称】` 包裹；未在 id_map 中的 wxid 直接显示原始 ID。

## Skills 安装

```bash
cp skills/skill-private.md ~/.claude/skills/
cp skills/skill-chatroom.md ~/.claude/skills/
```

## 依赖

纯 Python 标准库，无第三方依赖。Python 3.10+（使用了 `int | None` 类型注解语法）。
