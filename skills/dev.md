---
name: dev
description: 微信导出工具开发文档。包含项目结构、消息编码实现细节（appmsg/zstd/引用/系统消息）、双人 vs 群聊差异、脚本约定与依赖说明。调试或修改脚本时读取。
---

# 微信导出工具 — 开发文档

微信 4.x 聊天记录解密导出工具，输出 LLM 可读压缩文本。解密能力来自 `ylytdeng/wechat-decrypt`，本项目提供 Claude Skill、导出脚本和 DB schema 文档。

## 项目结构

```
scripts/
  common.py            # 共用工具：时间参数解析、进度日志、消息拉取、解码、压缩输出
  export_contacts.py   # 按消息量扫描重要联系人，支持多消息库
  export_private.py    # 双人会话导出脚本
  export_chatroom.py   # 群聊导出脚本
  find_contact.py      # 搜索联系人：查找 + 输出导出命令（对应 export-contacts skill）
  find_private.py      # 搜索联系人：查找 + 生成 sender_map + 输出导出命令（对应 export-private skill）
  find_chatroom.py     # 搜索群聊：查找 + 输出导出命令（对应 export-chatroom skill）
skills/
  common.md            # Claude Skill：公共知识库（DB schema、Step 0、公共参数）
  export-contacts.md   # Claude Skill：扫描重要联系人（依赖 common）
  export-private.md    # Claude Skill：双人会话（依赖 common）
  export-chatroom.md   # Claude Skill：群聊（依赖 common）
  summary.md           # Claude Skill：群聊总结模板
  dev.md               # 本文件：开发文档
```

## 消息编码实现细节

> 操作层面（DB 路径、表格式、消息类型→输出映射、输出格式）见 `skills/common.md`。

### appmsg 扩展类型（`local_type % 2³² == 49`）

编码规律：`local_type = appmsg_inner_type × 2³² + 49`。内容为 **zstd 压缩的 appmsg XML**，`<appmsg><type>N</type>` 决定实际类型。**类型→输出映射见 `skills/common.md`**。

zstd 魔数：`\x28\xb5\x2f\xfd`（前4字节）。解压依赖 `zstandard` 库；未安装时显示 `[需安装 zstandard 库以读取此消息]`。

**群聊 appmsg 的 wxid 前缀**：群聊中 appmsg 解压后内容开头有 `wxid_xxx:\n` 前缀，私聊无。解码前需先找 `<?xml` 起始位置截断，否则 XML 解析失败。实现见 `decode_content()` 中的 `xml_start = xml_str.find("<?xml")` 处理。

#### 引用消息发送方判断（`other_table_hash`）

引用回复（type=57）的 XML 中有 `<refermsg><fromusr>wxid_xxx</fromusr>`。由于表名 = `Msg_` + MD5(对方wxid)，可直接比较：

```python
hashlib.md5(fromusr.encode()).hexdigest() == table[4:]
# True  → 被引用消息是对方发的
# False → 被引用消息是用户自己发的
```

不需要查 contact.db。`export_private.py` 通过 `other_table_hash = table[4:]` 传入 `decode_content()`。

### type=10000 系统消息

部分是完整 zstd 压缩数据，部分在 zstd 帧头后**直接拼接明文 XML**（非完整压缩帧）。
解码策略：优先 zstd 解压；失败则在原始字节中搜索 `<?xml` / `<sysmsg` 起始位置，截取后解析。

常见内容：`<sysmsg type="revokemsg">` → `[你撤回了一条消息]` / `[对方撤回了一条消息]`。

## 双人 vs 群聊的关键差异

**双人会话**：`real_sender_id` 可靠。发送方映射通过 `--sender-map sender_map.json` 管理：`find_private.py` 在展示联系人信息时自动调用 `infer_sender_map()`（位于 `common.py`）生成 sender_map.json，并将采样消息内联打印供即时核对；如有误直接编辑 JSON 再运行导出命令。

推断逻辑：主信号为**跨表出现频率**——扫描同一 DB 内所有 `Msg_*` 表，出现次数更多的 ID 为用户（用户参与所有会话故频率更高）；频率相同时回退到较小 ID。每条 entry 含 `_infer_method` 字段（`cross-table` 或 `min-id`），`_samples` 只读不写，两者导出时均自动忽略。

**群聊**：type=1 消息的 `real_sender_id` 不可靠，真实发送者 wxid 嵌在 `message_content` 前缀：

```
wxid_xxx:\n正文内容
```

解析时用 `":\n"` 分割，前缀需满足 `[\w\-]{1,64}`。SQLite 中字面量 `':\n'` 无效，用 `char(58,10)` 替代。

群聊非文字消息（图片、引用等）无 wxid 前缀，`real_sender_id` 是同一消息库 `Name2Id` 表的 rowid，可通过 rowid→user_name 反查 wxid，再映射显示名。无法反查时才标注 `【?】`（如已离群成员）。

## 脚本约定

- stdout + stderr 均重定向到同一输出文件（`> output/xxx.txt 2>&1`），不得进入上下文窗口
- 时段分隔：相邻消息间隔超过 `--threshold`（默认 3600 秒）则插入分隔线
- 默认时区 GMT+8，可用 `--tz` 调整
- 时间过滤三选一：`--days N` / `--since YYYY-MM-DD` / 不填（私聊全量，群聊默认 1 天）
- `fetch_messages` 拉取全部 local_type，不做前置过滤；类型过滤在 `decode_content()` 内处理
- `compress(messages, format_fn, threshold, tz)` 接受回调 `format_fn(msg) -> (sender, content) | None`，返回 `(text, skipped_count)`

### export_private.py

- `--db` 支持传多个路径（`nargs="+"`），内部 `fetch_messages_multi` 跨库拉取后按 `create_time` 排序合并
- `--sender-map` 必填，指向 sender_map.json；文件不存在时自动生成（含 `_samples`）并退出供核对，存在时直接读取；每条消息按自身所在库查对应映射，避免跨库 ID 冲突

### export_contacts.py

- `--msg-dbs` 建议传入所有已解密的库（`message_*.db` shell glob 自动展开），同一联系人的消息可能分散在多个库中
- 算法：扫描各 DB 所有 `Msg_*` 表 → 合并行计数 + 记录所在库编号 → 反查 contact.db（MD5 比对）→ 过滤阈值 → 降序输出，附"所在库"列
- 默认只输出双人会话；`--include-chatrooms` 加入群聊

### export_chatroom.py

- `--contact-db` 可选参数；提供时调用 `auto_build_id_map` 从消息表提取 wxid 前缀、查 contact.db、写入 `--id-map` 路径，省去手动构建 id_map 步骤

## 依赖

Python 3.10+，[zstandard](https://pypi.org/project/zstandard/)（`pip install zstandard`），sqlite3（标准库，精简 Linux 镜像需额外安装 `python3-sqlite3`）。
