"""
按消息量列出重要联系人，支持多个消息库（message_0.db、message_1.db 等）。

用法：
    python scripts/export_contacts.py \\
      --contact-db PATH \\
      --msg-dbs PATH [PATH ...] \\
      [--threshold N] \\
      [--include-chatrooms]

示例：
    python scripts/export_contacts.py \\
      --contact-db ~/Repo/wechat-decrypt/decrypted/contact/contact.db \\
      --msg-dbs ~/Repo/wechat-decrypt/decrypted/message/message_0.db \\
               ~/Repo/wechat-decrypt/decrypted/message/message_1.db \\
               ~/Repo/wechat-decrypt/decrypted/message/message_2.db \\
               ... \\
      --threshold 100

输出字段（tab 分隔）：
    排名  消息数  显示名  wxid  消息表
"""

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path


def get_contacts(contact_db_path: Path) -> list[dict]:
    conn = sqlite3.connect(contact_db_path)
    cur = conn.cursor()
    cur.execute("SELECT username, nick_name, remark FROM contact WHERE username != ''")
    rows = cur.fetchall()
    conn.close()
    return [{"username": r[0], "nick_name": r[1] or "", "remark": r[2] or ""} for r in rows]


def get_table_counts(db_path: Path) -> dict[str, int]:
    """返回 {table_name: row_count}，只含 Msg_ 开头的表。"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")
    tables = [r[0] for r in cur.fetchall()]
    counts = {}
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
    conn.close()
    return counts


def merge_table_counts(db_paths: list[Path]) -> dict[str, int]:
    """合并多个消息库的行计数（同一联系人的消息可能分散在 message_0～7 中）。"""
    merged: dict[str, int] = {}
    for db_path in db_paths:
        print(f"扫描 {db_path.name} ...", file=sys.stderr)
        for table, count in get_table_counts(db_path).items():
            merged[table] = merged.get(table, 0) + count
    return merged


def display_name(c: dict) -> str:
    return c["remark"] or c["nick_name"] or c["username"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-db", required=True, dest="contact_db", help="contact.db 路径")
    parser.add_argument("--msg-dbs", required=True, nargs="+", dest="msg_dbs",
                        help="消息库路径列表，如 message_0.db message_1.db")
    parser.add_argument("--threshold", type=int, default=50,
                        help="最低消息数阈值，默认 50")
    parser.add_argument("--include-chatrooms", action="store_true", dest="include_chatrooms",
                        help="包含群聊（默认只显示双人会话）")
    return parser.parse_args()


def main():
    args = parse_args()

    contacts = get_contacts(Path(args.contact_db))
    print(f"联系人总数：{len(contacts)}", file=sys.stderr)

    # 构建 MD5(username) → contact 反查表
    hash_to_contact: dict[str, dict] = {}
    for c in contacts:
        h = hashlib.md5(c["username"].encode()).hexdigest()
        hash_to_contact[h] = c

    table_counts = merge_table_counts([Path(p) for p in args.msg_dbs])

    results = []
    for table, count in table_counts.items():
        table_hash = table[4:]  # 去掉 'Msg_' 前缀
        contact = hash_to_contact.get(table_hash)
        if contact is None:
            continue  # 无对应联系人（已删除等），跳过
        if not args.include_chatrooms and contact["username"].endswith("@chatroom"):
            continue
        if count < args.threshold:
            continue
        results.append({
            "display": display_name(contact),
            "username": contact["username"],
            "table": table,
            "count": count,
        })

    results.sort(key=lambda x: x["count"], reverse=True)

    if not results:
        print(f"未找到消息数 ≥ {args.threshold} 的联系人。", file=sys.stderr)
        return

    print(f"共找到 {len(results)} 个联系人（阈值 {args.threshold} 条）\n", file=sys.stderr)

    # 表头
    count_w = max(len(str(r["count"])) for r in results)
    rank_w = len(str(len(results)))
    print(f"{'#':>{rank_w}}  {'消息数':>{count_w}}  显示名\t\twxid\t\t消息表")
    print("-" * 80)

    for i, r in enumerate(results, 1):
        print(f"{i:>{rank_w}}  {r['count']:>{count_w}}  {r['display']}\t{r['username']}\t{r['table']}")


if __name__ == "__main__":
    main()
