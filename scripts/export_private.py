"""
微信双人会话导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_private.py --db PATH --table MSG_TABLE [时间参数] > chat_private.txt

必填参数：
    --db        message_0.db 路径
    --table     消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

可选参数：
    --my-id     自己的 real_sender_id，默认 10（微信 4.x 固定值）
    --other-id  对方的 real_sender_id；省略时从消息表自动推断

时间参数（三选一，默认全量导出）：
    --days N                    最近 N 天
    --since YYYY-MM-DD          起始日期（可与 --until 组合）
    --until YYYY-MM-DD          截止日期

其他参数：
    --threshold 秒数            同一时段阈值，默认 3600
    --tz 小时数                 时区偏移，默认 8（GMT+8）

进度信息输出到 stderr，正文输出到 stdout，重定向互不干扰。
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from common import add_time_args, resolve_time_range, log_time_range, compress


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


def detect_other_id(db_path: Path, table: str, my_id: int) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT real_sender_id FROM {table} WHERE local_type = 1 AND real_sender_id != ?",
        (my_id,),
    )
    ids = [r[0] for r in cur.fetchall()]
    conn.close()
    if len(ids) == 1:
        return ids[0]
    if len(ids) == 0:
        raise SystemExit("错误：消息表中未找到对方的发送者 ID，请手动指定 --other-id")
    raise SystemExit(f"错误：找到多个发送者 ID {ids}，请手动指定 --other-id")


def make_format_fn(my_id: int, other_id: int):
    def format_fn(msg) -> tuple[str, str] | None:
        sender_id = msg["sender_id"]
        if sender_id == my_id:
            label = "用户"
        elif sender_id == other_id:
            label = "对方"
        else:
            return None

        content = msg["content"]
        if content is None:
            return None
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        content = content.strip()
        if not content:
            return None
        return label, content

    return format_fn


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="message_0.db 路径")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--my-id", type=int, default=10, dest="my_id", help="自己的 real_sender_id，默认 10")
    parser.add_argument("--other-id", type=int, default=None, dest="other_id", help="对方的 real_sender_id；省略时自动推断")
    add_time_args(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    tz, since_ts, until_ts = resolve_time_range(args)
    log_time_range(tz, since_ts, until_ts, args.tz)

    other_id = args.other_id if args.other_id is not None else detect_other_id(Path(args.db), args.table, args.my_id)
    print(f"my_id={args.my_id}  other_id={other_id}", file=sys.stderr)

    messages = fetch_messages(Path(args.db), args.table, since_ts, until_ts)
    print(f"共 {len(messages)} 条消息", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    text, _ = compress(messages, make_format_fn(args.my_id, other_id), args.threshold, tz)
    print(text)


if __name__ == "__main__":
    main()
