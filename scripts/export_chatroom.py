"""
微信群聊导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_chatroom.py --db PATH --table MSG_TABLE --id-map PATH [时间参数] > chat.txt

必填参数：
    --db        message_0.db 路径
    --table     消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    --id-map    id_map.json 路径

时间参数（三选一，默认最近1天）：
    --days N                    最近 N 天
    --since YYYY-MM-DD          起始日期（可与 --until 组合）
    --until YYYY-MM-DD          截止日期

其他参数：
    --threshold 秒数            同一时段阈值，默认 3600
    --tz 小时数                 时区偏移，默认 8（GMT+8）

进度信息输出到 stderr，正文输出到 stdout，重定向互不干扰。
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from common import add_time_args, resolve_time_range, log_time_range, compress


def build_sender_map(id_map_path: Path) -> dict[str, str]:
    with open(id_map_path, encoding="utf-8") as f:
        entries = json.load(f)
    result = {}
    for e in entries:
        username = (e.get("username") or "").strip()
        nick = (e.get("nick_name") or "").strip()
        if username:
            result[username] = nick if nick else username
    return result


def parse_content(raw) -> tuple[str | None, str] | None:
    """
    解析群聊消息格式：wxid_xxx:\\n正文

    返回值语义：
      None              → 应跳过（binary / 引用消息 / 含 null byte）
      (wxid, content)   → 有效消息；wxid 为 None 表示无发送者前缀（系统消息）
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw:
        return None

    # 含 null byte 或开头大量替换符 → binary 消息，跳过
    if "\x00" in raw or raw[:20].count("\ufffd") >= 2:
        return None

    if ":\n" in raw:
        prefix, body = raw.split(":\n", 1)
        prefix = prefix.strip()
        # wxid 格式：仅含字母、数字、下划线、连字符，长度 1–64
        if re.fullmatch(r"[\w\-]{1,64}", prefix):
            body = body.strip()
            if "\x00" in body:
                return None
            return prefix, body

    # 无 wxid 前缀（系统消息）
    content = raw.strip()
    if "\x00" in content:
        return None
    return None, content


def fetch_messages(
    db_path: Path,
    table: str,
    since_ts: int | None,
    until_ts: int | None,
) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    conditions = ["local_type = 1"]
    params = []
    if since_ts is not None:
        conditions.append("create_time >= ?")
        params.append(since_ts)
    if until_ts is not None:
        conditions.append("create_time < ?")
        params.append(until_ts)

    cur.execute(
        f"SELECT real_sender_id, create_time, message_content FROM {table}"
        f" WHERE {' AND '.join(conditions)} ORDER BY create_time ASC",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [{"sender_id": r[0], "ts": r[1], "content": r[2]} for r in rows]


def make_format_fn(sender_map: dict[str, str]):
    def format_fn(msg) -> tuple[str, str] | None:
        result = parse_content(msg["content"])
        if result is None:
            return None
        wxid, content = result
        if not content:
            return None
        if wxid:
            display = sender_map.get(wxid, wxid)
            sender = f"【{display}】"
        else:
            sender = "【?】"
        return sender, content

    return format_fn


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="message_0.db 路径")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--id-map", required=True, dest="id_map", help="id_map.json 路径")
    add_time_args(parser, default_days=1)
    return parser.parse_args()


def main():
    args = parse_args()
    tz, since_ts, until_ts = resolve_time_range(args)
    log_time_range(tz, since_ts, until_ts, args.tz)

    sender_map = build_sender_map(Path(args.id_map))
    messages = fetch_messages(Path(args.db), args.table, since_ts, until_ts)
    print(f"共 {len(messages)} 条消息", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    text, skipped = compress(messages, make_format_fn(sender_map), args.threshold, tz)
    if skipped:
        print(f"过滤 binary/引用消息：{skipped} 条", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
