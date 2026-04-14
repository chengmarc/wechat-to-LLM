"""
微信群聊导出脚本，输出为 LLM 可读压缩文本。

用法：
    python scripts/export_chatroom.py --db PATH --table MSG_TABLE --id-map PATH [时间参数] > chat.txt

必填参数：
    --db        message_0.db 路径
    --table     消息表名，如 Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    --id-map    id_map.json 路径（若同时传 --contact-db，则自动生成此文件）

可选参数：
    --contact-db    contact.db 路径；提供时自动从消息表提取 wxid 并查询昵称，
                    生成/更新 --id-map 文件（省去手动构建 id_map 的步骤）

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

from common import add_time_args, resolve_time_range, log_time_range, fetch_messages, compress, decode_content


def build_sender_map(id_map_path: Path) -> dict[str, str]:
    with open(id_map_path, encoding="utf-8") as f:
        entries = json.load(f)
    result = {}
    for e in entries:
        username = (e.get("username") or "").strip()
        if not username:
            continue
        nick = (e.get("nick_name") or "").strip()
        result[username] = nick or username
    return result


def auto_build_id_map(db_path: Path, table: str, contact_db_path: Path, id_map_path: Path) -> dict[str, str]:
    """
    从消息表提取所有 wxid 前缀，查 contact.db 获取昵称，
    将结果写入 id_map_path，并返回 sender_map（wxid → 显示名）。
    """
    # 提取消息表中出现的所有 wxid 前缀
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT substr(message_content, 1, instr(message_content, char(58,10)) - 1) "
        f"FROM {table} WHERE local_type = 1 AND instr(message_content, char(58,10)) > 0"
    )
    raw_ids = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()

    wxids = [w for w in raw_ids if re.fullmatch(r"[\w\-]{1,64}", w)]
    if not wxids:
        print("警告：未找到任何 wxid 前缀，id_map 将为空", file=sys.stderr)
        entries = []
    else:
        placeholders = ",".join("?" * len(wxids))
        conn = sqlite3.connect(contact_db_path)
        cur = conn.cursor()
        cur.execute(
            f"SELECT username, nick_name, remark FROM contact WHERE username IN ({placeholders})",
            wxids,
        )
        rows = cur.fetchall()
        conn.close()
        entries = [{"username": r[0], "nick_name": r[1] or "", "remark": r[2] or ""} for r in rows]

    id_map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(id_map_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"id_map 已生成：{id_map_path}（{len(entries)} 个联系人）", file=sys.stderr)

    result = {}
    for e in entries:
        username = e["username"].strip()
        nick = (e.get("nick_name") or "").strip()
        result[username] = nick or username
    return result


def parse_text_content(raw) -> tuple[str | None, str] | None:
    """
    解析 type=1 群聊消息格式：wxid_xxx:\\n正文

    返回值语义：
      None              → 应跳过（binary / 含 null byte）
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


def make_format_fn(sender_map: dict[str, str]):
    def format_fn(msg) -> tuple[str, str] | None:
        local_type = msg["local_type"]

        # type=1：走原有 wxid 前缀解析逻辑（real_sender_id 在群聊中不可靠）
        if local_type == 1:
            result = parse_text_content(msg["content"])
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

        # 其他类型：用 decode_content 解码内容；sender 用 real_sender_id 查表
        # 注意：群聊 real_sender_id 对非文字消息的可靠性未经完整验证
        content = decode_content(local_type, msg["content"])
        if content is None:
            return None

        # real_sender_id 在群聊中通常是数字，无法直接映射到 wxid；只能标 [?]
        sender = "【?】"
        return sender, content

    return format_fn


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="message_0.db 路径")
    parser.add_argument("--table", required=True, help="消息表名，如 Msg_xxxx")
    parser.add_argument("--id-map", required=True, dest="id_map", help="id_map.json 路径")
    parser.add_argument("--contact-db", default=None, dest="contact_db",
                        help="contact.db 路径；提供时自动生成 id_map.json")
    add_time_args(parser, default_days=1)
    return parser.parse_args()


def main():
    args = parse_args()
    tz, since_ts, until_ts = resolve_time_range(args)
    log_time_range(tz, since_ts, until_ts)

    id_map_path = Path(args.id_map)
    if args.contact_db:
        sender_map = auto_build_id_map(
            Path(args.db), args.table, Path(args.contact_db), id_map_path
        )
    else:
        sender_map = build_sender_map(id_map_path)

    messages = fetch_messages(Path(args.db), args.table, since_ts, until_ts)
    print(f"共 {len(messages)} 条消息（含所有类型）", file=sys.stderr)

    if not messages:
        print("该时间段内无消息。", file=sys.stderr)
        return

    text, skipped = compress(messages, make_format_fn(sender_map), args.threshold, tz)
    if skipped:
        print(f"跳过不可解码消息：{skipped} 条", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
