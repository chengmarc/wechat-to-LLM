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
from datetime import datetime, timezone, timedelta
from pathlib import Path


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


def parse_content(raw) -> tuple[str | None, str]:
    """
    解析群聊消息格式：wxid_xxx:\n正文
    返回 (wxid_or_None, 正文)；二进制/引用消息返回 (None, "")
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw:
        return None, ""

    # 含 null byte 或开头大量替换符 → binary 消息（引用/卡片），丢弃
    if "\x00" in raw or raw[:20].count("\ufffd") >= 2:
        return None, ""

    if ":\n" in raw:
        prefix, body = raw.split(":\n", 1)
        prefix = prefix.strip()
        # wxid 格式：仅含字母、数字、下划线、连字符，长度 1–64
        if re.fullmatch(r"[\w\-]{1,64}", prefix):
            body = body.strip()
            # body 含 null byte 也丢弃
            if "\x00" in body:
                return None, ""
            return prefix, body

    # 非群聊格式（双人会话或系统消息）：无 wxid，直接返回正文
    content = raw.strip()
    if "\x00" in content:
        return None, ""
    return None, content


def fetch_messages(db_path: Path, table: str, since_ts: int, until_ts: int) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT real_sender_id, create_time, message_content
        FROM {table}
        WHERE local_type = 1
          AND create_time >= ?
          AND create_time <  ?
        ORDER BY create_time ASC
        """,
        (since_ts, until_ts),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"sender_id": r[0], "ts": r[1], "content": r[2]} for r in rows]


def compress(messages: list[dict], sender_map: dict[str, str], threshold: int, tz: timezone) -> str:
    lines = []
    last_ts = None
    skipped = 0

    for msg in messages:
        ts = msg["ts"]
        wxid, content = parse_content(msg["content"])

        # 空内容 = binary/引用消息，跳过
        if not content:
            skipped += 1
            continue

        if wxid:
            display = sender_map.get(wxid)
            sender = f"【{display if display else wxid}】"
        else:
            # real_sender_id 在群聊中不可靠（数字ID），不作为显示名
            sender = "【?】"

        if last_ts is None or ts - last_ts > threshold:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
            tag = dt.strftime("%y-%m-%d %H:%M")
            lines.append(f"\n\n-----------------------\n[{tag}]\n-----------------------")

        last_ts = ts
        lines.append(f"{sender}：{content}|")

    print(f"过滤 binary/引用消息：{skipped} 条", file=sys.stderr)
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="message_0.db 路径")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--id-map", required=True, dest="id_map", help="id_map.json 路径")
    parser.add_argument("--threshold", type=int, default=3600, help="同一时段阈值（秒），默认 3600")
    parser.add_argument("--tz", type=int, default=8, help="时区偏移小时数，默认 8")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=1)
    group.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--until", help="YYYY-MM-DD")
    return parser.parse_args()


def main():
    args = parse_args()
    tz = timezone(timedelta(hours=args.tz))
    now = datetime.now(tz)

    if args.since:
        since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        since_dt = (now - timedelta(days=args.days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    until_dt = (
        datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=tz)
        if args.until
        else now
    )

    since_ts = int(since_dt.timestamp())
    until_ts = int(until_dt.timestamp())

    print(
        f"查询范围：{since_dt.strftime('%Y-%m-%d %H:%M')} ~ {until_dt.strftime('%Y-%m-%d %H:%M')} (GMT+{args.tz})",
        file=sys.stderr,
    )

    sender_map = build_sender_map(Path(args.id_map))
    messages = fetch_messages(Path(args.db), args.table, since_ts, until_ts)

    print(f"共 {len(messages)} 条消息", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    print(compress(messages, sender_map, args.threshold, tz))


if __name__ == "__main__":
    main()
