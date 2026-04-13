# wechat-to-LLM

微信 4.x 聊天记录解密导出工具，输出 LLM 可读压缩文本。解密能力来自 `ylytdeng/wechat-decrypt`，本项目提供 Claude Skill、导出脚本和 DB schema 文档。

## 项目结构

```
scripts/
  common.py            # 共用工具：时间参数解析、进度日志、compress()、decode_content()
  export_private.py    # 双人会话导出脚本
  export_chatroom.py   # 群聊导出脚本
skills/
  skill-private.md     # Claude Skill：双人会话
  skill-chatroom.md    # Claude Skill：群聊
```

`common.py` 提供：`add_time_args` / `resolve_time_range` / `log_time_range` / `compress` / `decode_content`。
`compress(messages, format_fn, threshold, tz)` 接受回调 `format_fn(msg) -> (sender, content) | None`，返回 `(text, skipped_count)`。

## 数据库结构

解密后两个 SQLite 库，位于 `wechat-decrypt/decrypted/`：

- `contact/contact.db`：联系人表，字段 `username`（wxid）/ `nick_name` / `remark` / `alias`
- `message/message_0.db`：消息库，每个联系人一张表，表名 = `Msg_` + MD5(wxid)

消息表有效字段：`local_id` / `local_type` / `real_sender_id` / `create_time`（Unix 秒）/ `message_content`

## local_type 完整枚举

| local_type | 类型 | message_content | 导出输出 |
|---|---|---|---|
| 1 | 文字 | UTF-8 明文 | 原文 |
| 3 | 图片 | binary blob | `[图片]` |
| 34 | 语音 | binary blob | `[语音]` |
| 42 | 名片 | binary blob | `[名片]` |
| 43 | 视频 | binary blob | `[视频]` |
| 47 | 微信表情 | binary blob | `[表情]` |
| 48 | 位置 | binary blob | `[位置]` |
| 50 | 通话 | binary blob | `[通话]` |
| 10000 | 系统通知 | 见下方说明 | `[撤回了一条消息]` 等 |
| `N × 2³² + 49` | appmsg 扩展类型 | zstd 压缩 XML | 见下方说明 |

### appmsg 扩展类型（大数字）

所有 `local_type % (2³²) == 49` 的消息均为 **zstd 压缩的 appmsg XML**。

**编码规律**：`local_type = appmsg_inner_type × 2³² + 49`

解压后是标准 XML，`<appmsg><type>N</type>` 决定实际类型：

| appmsg inner type | 类型 | local_type 示例 | 导出输出 |
|---|---|---|---|
| 4 | 外链/视频分享（B站等） | 17179869233 | `[分享] {title} {url}` |
| 5 | 小程序/图文分享（小红书等）| 21474836529 | `[分享] {title} {url}` |
| 57 | 引用回复 | 244813135921 | `「引用 {发送方}：{被引用内容}」{回复正文}` |
| 其他 | 卡片/小程序等 | — | `[分享] {title}`（无 URL 时） |

zstd 魔数：`\x28\xb5\x2f\xfd`（前4字节）。解压依赖 `zstandard` 库；未安装时显示 `[需安装 zstandard 库以读取此消息]`。

### type=10000 系统消息

部分系统消息是 zstd 压缩数据，部分是在 zstd 帧头后**直接拼接明文 XML**（非完整压缩帧）。
解码策略：优先 zstd 解压；失败则在原始字节中搜索 `<?xml` / `<sysmsg` 的起始位置，截取后解析。

常见内容：`<sysmsg type="revokemsg">` → `[你撤回了一条消息]` / `[对方撤回了一条消息]`。

## 引用消息发送方判断（`other_table_hash`）

引用回复的 XML 里有 `<refermsg><fromusr>wxid_xxx</fromusr>`，需要判断这个 wxid 是"用户"还是"对方"。

由于表名 = `Msg_` + MD5(对方wxid)，可以直接比较：

```python
hashlib.md5(fromusr.encode()).hexdigest() == table[4:]
# True  → 被引用消息是对方发的
# False → 被引用消息是用户自己发的
```

不需要查 contact.db，不需要额外参数。`export_private.py` 通过 `other_table_hash = table[4:]` 传入 `decode_content()`。

## 双人 vs 群聊的关键差异

**双人会话**：`real_sender_id` 可靠。自己固定为 `10`（微信 4.x 实测），对方为另一个值，脚本可自动推断。

**群聊**：type=1 消息的 `real_sender_id` 不可靠，真实发送者 wxid 嵌在 `message_content` 前缀：

```
wxid_xxx:\n正文内容
```

解析时用 `":\n"` 分割，前缀需满足 `[\w\-]{1,64}`。SQLite 中字面量 `':\n'` 无效，用 `char(58,10)` 替代。

群聊非文字消息（图片、引用等）无 wxid 前缀，`real_sender_id` 可靠性未经完整验证，导出时发送方标注为 `【?】`。

## 导出脚本约定

- 进度信息 → `stderr`，正文 → `stdout`，重定向互不干扰
- 时段分隔：相邻消息间隔超过 `--threshold`（默认 3600 秒）则插入分隔线
- 默认时区 GMT+8，可用 `--tz` 调整
- 时间过滤三选一：`--days N` / `--since YYYY-MM-DD` / 不填（私聊全量，群聊默认 1 天）
- `fetch_messages` 拉取全部 local_type，不做前置过滤；类型过滤在 `decode_content()` 内处理

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

Python 3.10+，[zstandard](https://pypi.org/project/zstandard/)（`pip install zstandard`）。
