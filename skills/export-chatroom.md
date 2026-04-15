---
name: export-chatroom
description: 从已解密的微信数据库中提取群聊记录，输出为 LLM 可读的压缩文本。当用户需要导出群聊内容、生成群聊总结、或分析群内对话时使用此 skill。
---

# 微信群聊导出

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构、Step 0 和公共参数说明。

## 群聊特有说明

- `real_sender_id` 不可靠。真实发送者 wxid 嵌在 `message_content` 前缀中：`wxid_xxx:\n正文内容`。
- 非文字消息（图片、引用等）无 wxid 前缀，发送方通过 `Name2Id` 表反查；仅无法反查时（如已离群成员）标注为 `【?】`。
- 群 username 格式：`数字@chatroom`（如 `12345678@chatroom`）。

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：查找群聊

```bash
cd ~/Repo/wechat-to-LLM
python scripts/find_chatroom.py <关键词>
```

输出：wxid、消息表名、各库消息量及日期范围、以及一条即用的 `export_chatroom.py` 命令（默认最近1天）。

### Step 2：运行导出命令

> **必须重定向到文件，禁止裸跑。** stdout 和 stderr 均不得进入上下文窗口。

在 Step 1 输出的命令末尾加 `> output/<群名>.txt 2>&1` 后运行。`--contact-db` 参数存在时自动生成/更新 `id_map.json`（后续导出可省略此参数）。

时间范围参数（替换默认的 `--days 1`）：

| 参数 | 说明 |
|------|------|
| `--days N` | 最近 N 天 |
| `--since YYYY-MM-DD` | 从某日起 |
| `--since YYYY-MM-DD --until YYYY-MM-DD` | 指定区间 |
