"""
按关键词搜索联系人，生成 sender_map.json 并内联展示样本，输出即用的导出命令。
对应 export-private skill 的 Step 1。

用法：
    python scripts/find_private.py <关键词> [--contact-db PATH] [--msg-dbs PATH ...]
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

from common import db_number, safe_filename, search_contacts, check_dbs, infer_sender_map
from datetime import timezone, timedelta


DEFAULT_CONTACT_DB = "wechat-decrypt/decrypted/contact/contact.db"
DEFAULT_MSG_PATTERN = "wechat-decrypt/decrypted/message/message_*.db"


def parse_args():
    parser = argparse.ArgumentParser(description="搜索联系人，生成 sender_map，输出导出命令")
    parser.add_argument("keyword", help="搜索关键词（匹配 nick_name / remark）")
    parser.add_argument("--contact-db", default=DEFAULT_CONTACT_DB, dest="contact_db")
    parser.add_argument("--msg-dbs", nargs="*", default=None, dest="msg_dbs")
    parser.add_argument("--tz", type=int, default=8, help="时区偏移小时数，默认 8")
    return parser.parse_args()


def show_sender_map(sender_map_path: Path, found_dbs: list[tuple], table: str) -> None:
    """生成（若不存在）或读取 sender_map.json，内联打印供即时核对。"""
    if sender_map_path.exists():
        with open(sender_map_path, encoding="utf-8") as f:
            entries = json.load(f)
        print(f"\n    sender_map（已存在 → {sender_map_path}）：")
    else:
        db_path_objs = [Path(db_path) for db_path, *_ in found_dbs]
        entries = infer_sender_map(db_path_objs, table)
        if not entries:
            print("\n    sender_map：无法推断（各库 type=1 消息不足两个 sender_id），请手动创建。")
            return
        sender_map_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sender_map_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"\n    sender_map（新生成 → {sender_map_path}）：")

    for e in entries:
        samples = e.get("_samples") or {}
        my_s = samples.get(str(e["my_id"]), [])[:2]
        ot_s = samples.get(str(e["other_id"]), [])[:2]
        my_str = "  ".join(f"「{s[:25]}」" for s in my_s) if my_s else "（无样本）"
        ot_str = "  ".join(f"「{s[:25]}」" for s in ot_s) if ot_s else "（无样本）"
        method = e.get("_infer_method", "")
        method_tag = f"  [{method}]" if method else ""
        print(f"      {e['db']}:{method_tag}")
        print(f"        用户  (my_id={e['my_id']}):    {my_str}")
        print(f"        对方  (other_id={e['other_id']}): {ot_str}")

    print(f"    如推断有误，编辑 {sender_map_path} 后再运行导出命令。")


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

    contacts = search_contacts(args.contact_db, args.keyword)
    if not contacts:
        print(f'未找到包含"{args.keyword}"的联系人（不含群聊）')
        return

    for i, (wxid, nick, remark) in enumerate(contacts, 1):
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
            print("    (所有消息库中均无此联系人的消息)")
            continue

        print("    所在库：")
        for db_path, cnt, s, u in found:
            print(f"      {os.path.basename(db_path)}: {cnt}条  {s}~{u}")

        fname = safe_filename(display)
        sender_map_path = Path(f"output/sender_map_{fname}.json")
        show_sender_map(sender_map_path, found, table)

        db_str = " \\\n          ".join(db_path for db_path, *_ in found)
        print(f"\n    # 导出命令：")
        print(f"    python scripts/export_private.py \\")
        print(f"      --db {db_str} \\")
        print(f"      --table {table} \\")
        print(f"      --sender-map {sender_map_path} \\")
        print(f"      > output/chat_{fname}.txt 2>&1")


if __name__ == "__main__":
    main()
