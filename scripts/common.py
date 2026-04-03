"""
export_private / export_chatroom 共用工具：时间参数解析、进度日志、压缩输出。
"""

import sys
from datetime import datetime, timezone, timedelta


def add_time_args(parser, default_days=None):
    """向 ArgumentParser 注入公共时间参数（--days/--since 互斥，--until，--threshold，--tz）。"""
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=default_days)
    group.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--until", help="YYYY-MM-DD")
    parser.add_argument("--threshold", type=int, default=3600, help="同一时段阈值（秒），默认 3600")
    parser.add_argument("--tz", type=int, default=8, help="时区偏移小时数，默认 8")


def resolve_time_range(args) -> tuple[timezone, int | None, int | None]:
    """
    解析时间参数，返回 (tz, since_ts, until_ts)。
    since_ts / until_ts 为 None 表示无下界 / 无上界。
    """
    tz = timezone(timedelta(hours=args.tz))
    now = datetime.now(tz)

    since_ts = None
    if args.since:
        since_ts = int(datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=tz).timestamp())
    elif args.days is not None:
        since_dt = (now - timedelta(days=args.days)).replace(hour=0, minute=0, second=0, microsecond=0)
        since_ts = int(since_dt.timestamp())

    until_ts = None
    if args.until:
        until_ts = int(datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=tz).timestamp())

    return tz, since_ts, until_ts


def log_time_range(tz: timezone, since_ts: int | None, until_ts: int | None, tz_offset: int) -> None:
    if since_ts is not None and until_ts is not None:
        s = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        u = datetime.fromtimestamp(until_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{s} ~ {u} (GMT+{tz_offset})", file=sys.stderr)
    elif since_ts is not None:
        s = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{s} ~ 现在 (GMT+{tz_offset})", file=sys.stderr)
    else:
        print("查询范围：全量", file=sys.stderr)


def compress(messages: list[dict], format_fn, threshold: int, tz: timezone) -> tuple[str, int]:
    """
    将消息列表压缩为带时段分隔的文本。

    format_fn(msg) -> (sender_label, content) | None
        返回 None 表示跳过该消息（binary / 引用 / 无效内容）。

    返回 (text, skipped_count)。
    """
    lines = []
    last_ts = None
    skipped = 0

    for msg in messages:
        result = format_fn(msg)
        if result is None:
            skipped += 1
            continue
        sender, content = result
        ts = msg["ts"]
        if last_ts is None or ts - last_ts > threshold:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
            tag = dt.strftime("%y-%m-%d %H:%M")
            lines.append(f"\n\n-----------------------\n[{tag}]\n-----------------------")
        last_ts = ts
        lines.append(f"{sender}：{content}|")

    return "\n".join(lines), skipped
