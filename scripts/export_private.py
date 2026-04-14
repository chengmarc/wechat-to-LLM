"""
微信双人会话导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_private.py --db PATH [PATH ...] --table MSG_TABLE --sender-map PATH [时间参数] > chat_private.txt

必填参数：
    --db            message_N.db 路径（可传多个，自动按时间戳排序合并）
    --table         消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    --sender-map    sender_map.json 路径

    若 sender_map.json 不存在，脚本自动推断并写出文件后退出，供用户核对；
    核对/修改后重新运行即可导出。

    sender_map.json 格式（每库一条，my_id/other_id 均为 real_sender_id 整数）：
        [
          {"db": "message_7.db", "my_id": 1, "other_id": 2},
          {"db": "message_6.db", "my_id": 2, "other_id": 7},
          ...
        ]

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
import json
import sqlite3
import sys
from pathlib import Path

from common import (
    add_time_args, resolve_time_range, log_time_range,
    fetch_messages_multi,
    compress, decode_content,
)


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# sender_map.json 读写
# ---------------------------------------------------------------------------

def _sample_messages(conn, table: str, sender_id: int, n: int = 5) -> list[str]:
    """从指定 sender_id 采样最多 n 条 type=1 消息内容（取时间最早的）。"""
    cur = conn.cursor()
    cur.execute(
        f"SELECT message_content FROM {table} "
        f"WHERE local_type = 1 AND real_sender_id = ? "
        f"ORDER BY create_time ASC LIMIT ?",
        (sender_id, n),
    )
    samples = []
    for (raw,) in cur.fetchall():
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if raw:
            # 群聊前缀 wxid:\n 截断；私聊无此前缀，不影响
            text = raw.split(":\n", 1)[-1].strip()
            if text:
                samples.append(text)
    return samples


def infer_sender_map(db_paths: list[Path], table: str) -> list[dict]:
    """
    按库分别扫描 type=1 消息的 distinct real_sender_id，推断 my_id / other_id。
    规律（启发式）：两个 ID 中较小的为 my_id，较大的为 other_id。
    同时为每个 sender_id 采样几条消息写入 _samples，供人工核对。
    仅在恰好找到 2 个 ID 时才为该库生成条目；其他情况跳过并输出警告。
    """
    entries = []
    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        if not _table_exists(conn, table):
            conn.close()
            continue
        cur = conn.cursor()
        cur.execute(f"SELECT DISTINCT real_sender_id FROM {table} WHERE local_type = 1")
        ids = sorted(r[0] for r in cur.fetchall())
        if len(ids) == 2:
            samples = {str(sid): _sample_messages(conn, table, sid) for sid in ids}
            entries.append({
                "db": db_path.name,
                "my_id": ids[0],
                "other_id": ids[1],
                "_samples": samples,
            })
        elif len(ids) == 1:
            print(f"警告：{db_path.name} 只有 1 个 sender_id ({ids[0]})，无法推断，已跳过", file=sys.stderr)
        else:
            print(f"警告：{db_path.name} 找到 {len(ids)} 个 sender_id {ids}，无法推断，已跳过", file=sys.stderr)
        conn.close()
    return entries


def load_sender_map(sender_map_path: Path) -> dict[str, dict[int, str]]:
    """
    读取 sender_map.json，返回 {db_name: {sender_id: label}} 映射。
    """
    with open(sender_map_path, encoding="utf-8") as f:
        entries = json.load(f)
    result: dict[str, dict[int, str]] = {}
    for e in entries:
        db_name = e["db"]
        result[db_name] = {e["my_id"]: "用户", e["other_id"]: "对方"}
    return result


# ---------------------------------------------------------------------------
# format_fn
# ---------------------------------------------------------------------------

def make_format_fn(per_db_map: dict[str, dict[int, str]], other_table_hash: str):
    """
    per_db_map: {db_name: {sender_id: '用户'/'对方'}}
    每条消息按自身的 db_path.name 查对应库的映射。
    """
    def format_fn(msg) -> tuple[str, str] | None:
        db_name = msg["db_path"].name
        db_map = per_db_map.get(db_name, {})
        label = db_map.get(msg["sender_id"])
        if label is None:
            return None

        content = decode_content(msg["local_type"], msg["content"], other_table_hash)
        if content is None:
            return None
        return f"【{label}】", content

    return format_fn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, nargs="+", help="message_N.db 路径（可传多个）")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--sender-map", required=True, dest="sender_map", help="sender_map.json 路径")
    add_time_args(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    tz, since_ts, until_ts = resolve_time_range(args)

    db_paths = [Path(p) for p in args.db]
    sender_map_path = Path(args.sender_map)

    # sender_map.json 不存在：推断并写出，让用户核对
    if not sender_map_path.exists():
        print(f"sender_map.json 不存在，正在推断…", file=sys.stderr)
        entries = infer_sender_map(db_paths, args.table)
        sender_map_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sender_map_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"已写出：{sender_map_path}", file=sys.stderr)
        print(f"请核对 my_id / other_id 是否正确，确认后重新运行导出。", file=sys.stderr)
        sys.exit(0)

    per_db_map = load_sender_map(sender_map_path)
    for db_name, m in per_db_map.items():
        print(f"  {db_name}: {m}", file=sys.stderr)

    log_time_range(tz, since_ts, until_ts)

    other_table_hash = args.table[4:] if args.table.startswith("Msg_") else ""

    messages = fetch_messages_multi(db_paths, args.table, since_ts, until_ts)
    print(f"合计 {len(messages)} 条消息（含所有类型）", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    text, skipped = compress(messages, make_format_fn(per_db_map, other_table_hash), args.threshold, tz)
    if skipped:
        print(f"跳过不可解码消息：{skipped} 条", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
