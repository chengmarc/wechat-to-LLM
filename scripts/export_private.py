"""
微信双人会话导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_private.py --db PATH --table MSG_TABLE --my-id MY_ID --other-id OTHER_ID [时间参数] > chat_private.txt

必填参数：
    --db        message_0.db 路径
    --table     消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    --my-id     自己的 real_sender_id（整数）
    --other-id  对方的 real_sender_id（整数）

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
from datetime import datetime, timezone, timedelta
from pathlib import Path


def fetch_messages(
    db_path: Path,
    table: str,
    my_id: int,
    other_id: int,
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

    where = " AND ".join(conditions)
    cur.execute(
        f"SELECT real_sender_id, create_time, message_content FROM {table} WHERE {where} ORDER BY create_time ASC",
        params,
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for sender_id, ts, content in rows:
        if sender_id == my_id:
            sender = "用户"
        elif sender_id == other_id:
            sender = "对方"
        else:
            continue
        if content is None:
            continue
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        content = content.strip()
        if not content:
            continue
        result.append({"sender": sender, "ts": ts, "content": content})

    return result


def compress(messages: list[dict], threshold: int, tz: timezone) -> str:
    lines = []
    last_ts = None

    for msg in messages:
        ts = msg["ts"]
        if last_ts is None or ts - last_ts > threshold:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
            tag = dt.strftime("%y-%m-%d %H:%M")
            lines.append(f"\n\n-----------------------\n[{tag}]\n-----------------------")
        last_ts = ts
        lines.append(f"{msg['sender']}：{msg['content']}|")

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="message_0.db 路径")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--my-id", required=True, type=int, dest="my_id", help="自己的 real_sender_id")
    parser.add_argument("--other-id", required=True, type=int, dest="other_id", help="对方的 real_sender_id")
    parser.add_argument("--threshold", type=int, default=3600, help="同一时段阈值（秒），默认 3600")
    parser.add_argument("--tz", type=int, default=8, help="时区偏移小时数，默认 8")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int)
    group.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--until", help="YYYY-MM-DD")
    return parser.parse_args()


def main():
    args = parse_args()
    tz = timezone(timedelta(hours=args.tz))
    now = datetime.now(tz)

    since_ts = None
    until_ts = None

    if args.since:
        since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=tz)
        since_ts = int(since_dt.timestamp())
    elif args.days:
        since_dt = (now - timedelta(days=args.days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_ts = int(since_dt.timestamp())

    if args.until:
        until_dt = datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=tz)
        until_ts = int(until_dt.timestamp())

    if since_ts and until_ts:
        since_str = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        until_str = datetime.fromtimestamp(until_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{since_str} ~ {until_str} (GMT+{args.tz})", file=sys.stderr)
    elif since_ts:
        since_str = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{since_str} ~ 现在 (GMT+{args.tz})", file=sys.stderr)
    else:
        print("查询范围：全量", file=sys.stderr)

    messages = fetch_messages(
        Path(args.db), args.table, args.my_id, args.other_id, since_ts, until_ts
    )
    print(f"共 {len(messages)} 条消息", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    print(compress(messages, args.threshold, tz))


if __name__ == "__main__":
    main()
