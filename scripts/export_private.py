"""
微信双人会话导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_private.py --db PATH [PATH ...] --table MSG_TABLE [时间参数] > chat_private.txt

必填参数：
    --db        message_N.db 路径（可传多个，自动按时间戳排序合并）
    --table     消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

可选参数：
    --my-id     自己的 real_sender_id；省略时自动推断（两者中较小的）
    --other-id  对方的 real_sender_id；省略时自动推断（两者中较大的）

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
import sys
from pathlib import Path

from common import (
    add_time_args, resolve_time_range, log_time_range,
    fetch_messages_multi, detect_sender_ids_multi,
    compress, decode_content,
)


def make_format_fn(my_id: int, other_id: int, other_table_hash: str):
    """
    other_table_hash: 消息表名去掉 'Msg_' 前缀（即对方 wxid 的 MD5），
    用于正确标注引用消息中的发送方。
    """
    def format_fn(msg) -> tuple[str, str] | None:
        sender_id = msg["sender_id"]
        if sender_id == my_id:
            label = "用户"
        elif sender_id == other_id:
            label = "对方"
        else:
            return None

        content = decode_content(msg["local_type"], msg["content"], other_table_hash)
        if content is None:
            return None
        return label, content

    return format_fn


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, nargs="+", help="message_N.db 路径（可传多个）")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--my-id", type=int, default=None, dest="my_id", help="自己的 real_sender_id；省略时自动推断")
    parser.add_argument("--other-id", type=int, default=None, dest="other_id", help="对方的 real_sender_id；省略时自动推断")
    add_time_args(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    tz, since_ts, until_ts = resolve_time_range(args)
    log_time_range(tz, since_ts, until_ts)

    db_paths = [Path(p) for p in args.db]

    if args.my_id is not None and args.other_id is not None:
        my_id, other_id = args.my_id, args.other_id
    else:
        my_id, other_id = detect_sender_ids_multi(db_paths, args.table)
        if args.my_id is not None:
            my_id = args.my_id
        if args.other_id is not None:
            other_id = args.other_id
    print(f"--my-id={my_id}  --other-id={other_id}", file=sys.stderr)

    # 消息表名去掉 'Msg_' 前缀即为对方 wxid 的 MD5，用于引用消息发送方判断
    other_table_hash = args.table[4:] if args.table.startswith("Msg_") else ""

    messages = fetch_messages_multi(db_paths, args.table, since_ts, until_ts)
    print(f"合计 {len(messages)} 条消息（含所有类型）", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    text, skipped = compress(messages, make_format_fn(my_id, other_id, other_table_hash), args.threshold, tz)
    if skipped:
        print(f"跳过不可解码消息：{skipped} 条", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
