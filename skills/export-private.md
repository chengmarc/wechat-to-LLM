---
name: export-private
description: 从已解密的微信数据库中查询双人会话记录，压缩导出为 LLM 可读文本。当用户需要导出与某人的聊天记录、搜索历史消息、或将双人对话用于 LLM 分析时使用此 skill。
---

# 微信双人会话导出

> **依赖**：执行前先读取 `~/.claude/skills/common.md`，获取数据库结构、Step 0 和公共参数说明。

## 操作流程

### Step 0：更新解密数据

参见 `common.md`。

### Step 1：查找联系人

```bash
cd ~/Repo/wechat-to-LLM
python scripts/find_private.py <关键词>
```

输出：wxid、消息表名、各库消息量及日期范围、sender_map 推断结果（含采样消息）、以及一条即用的 `export_private.py` 命令。

`sender_map.json` 若不存在则自动生成；已存在则直接读取展示。

### Step 2：运行导出命令

> **必须重定向到文件，禁止裸跑。** stdout 和 stderr 均不得进入上下文窗口。

核对 Step 1 输出的 sender_map（`用户` / `对方` 是否对应正确），如有误编辑 JSON 后再运行。确认无误，在命令末尾加 `> output/<名字>.txt 2>&1` 后运行。

时间范围参数（可附加在命令末尾，默认全量导出）：

| 参数 | 说明 |
|------|------|
| `--days N` | 最近 N 天 |
| `--since YYYY-MM-DD` | 从某日起 |
| `--since YYYY-MM-DD --until YYYY-MM-DD` | 指定区间 |

---

## sender_map.json 格式参考

```json
[
  {"db": "message_0.db", "my_id": 1, "other_id": 2, "_samples": {"1": ["..."], "2": ["..."]}},
  {"db": "message_1.db", "my_id": 2, "other_id": 7, "_samples": {"2": ["..."], "7": ["..."]}}
]
```

`_samples` 只读不写，导出时自动忽略。
