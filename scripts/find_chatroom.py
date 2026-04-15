"""
按关键词搜索群聊，显示消息分布，输出即用的导出命令。
对应 export-chatroom skill 的 Step 1。

用法：
    python scripts/find_chatroom.py <关键词> [--contact-db PATH] [--msg-dbs PATH ...]
"""

import argparse
import glob
import hashlib
import os
import sys

from common import db_number, safe_filename, search_chatrooms, check_dbs
from datetime import timezone, timedelta


DEFAULT_CONTACT_DB = "wechat-decrypt/decrypted/contact/contact.db"
DEFAULT_MSG_PATTERN = "wechat-decrypt/decrypted/message/message_*.db"


def parse_args():
    parser = argparse.ArgumentParser(description="搜索群聊并输出即用的导出命令")
    parser.add_argument("keyword", help="搜索关键词（匹配 nick_name / remark）")
    parser.add_argument("--contact-db", default=DEFAULT_CONTACT_DB, dest="contact_db")
    parser.add_argument("--msg-dbs", nargs="*", default=None, dest="msg_dbs")
    parser.add_argument("--tz", type=int, default=8, help="时区偏移小时数，默认 8")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.contact_db):
        print(f"错误：contact.db 不存在：{args.contact_db}", file=sys.stderr)
        sys.exit(1)

    if args.msg_dbs is None:
        args.msg_dbs = sorted(glob.glob(DEFAULT_MSG_PATTERN), key=db_number)
    else:
        args.msg_dbs = sorted(args.msg_dbs, key=db_number)

    tz = timezone(timedelta(hours=args.tz))

    chatrooms = search_chatrooms(args.contact_db, args.keyword)
    if not chatrooms:
        print(f'未找到包含"{args.keyword}"的群聊')
        return

    for i, (wxid, nick, remark) in enumerate(chatrooms, 1):
        display = remark or nick or wxid
        table = "Msg_" + hashlib.md5(wxid.encode()).hexdigest()

        print(f"\n[{i}] {display}")
        if nick and nick != display:
            print(f"    昵称：{nick}")
        if remark and remark != display:
            print(f"    备注：{remark}")
        print(f"    wxid:  {wxid}")
        print(f"    table: {table}")

        found = check_dbs(args.msg_dbs, table, tz)
        if not found:
            print("    (所有消息库中均无此群聊的消息)")
            continue

        print("    所在库：")
        for db_path, cnt, s, u in found:
            print(f"      {os.path.basename(db_path)}: {cnt}条  {s}~{u}")

        # 群聊导出脚本只接受单个 --db，取编号最小（最新）的库
        best_db = found[0][0]
        fname = safe_filename(display)
        print(f"\n    # 导出命令（默认最近1天；--days N 或 --since 调整范围）：")
        print(f"    python scripts/export_chatroom.py \\")
        print(f"      --db {best_db} \\")
        print(f"      --table {table} \\")
        print(f"      --contact-db {args.contact_db} \\")
        print(f"      --id-map output/id_map_{fname}.json \\")
        print(f"      > output/chat_{fname}.txt 2>&1")


if __name__ == "__main__":
    main()
