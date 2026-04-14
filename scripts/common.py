"""
export_private / export_chatroom 共用工具：时间参数解析、进度日志、压缩输出、消息解码。
"""

import hashlib
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# zstandard 是可选依赖；缺失时大数字类型消息会显示提示而非内容
try:
    import zstandard as _zstd
    _DCTX = _zstd.ZstdDecompressor()
    _HAS_ZSTD = True
except ImportError:
    _DCTX = None
    _HAS_ZSTD = False

_ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'

# binary 媒体类型 → 只标注类型，不可读内容
_MEDIA_LABELS: dict[int, str] = {
    3: '[图片]',
    34: '[语音]',
    43: '[视频]',
    47: '[表情]',
    48: '[位置]',
    50: '[通话]',
    42: '[名片]',
}


# ---------------------------------------------------------------------------
# 时间参数
# ---------------------------------------------------------------------------

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


def log_time_range(tz: timezone, since_ts: int | None, until_ts: int | None) -> None:
    tz_offset = int(tz.utcoffset(None).total_seconds() // 3600)
    if since_ts is not None and until_ts is not None:
        s = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        u = datetime.fromtimestamp(until_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{s} ~ {u} (GMT+{tz_offset})", file=sys.stderr)
    elif since_ts is not None:
        s = datetime.fromtimestamp(since_ts, tz=tz).strftime("%Y-%m-%d %H:%M")
        print(f"查询范围：{s} ~ 现在 (GMT+{tz_offset})", file=sys.stderr)
    else:
        print("查询范围：全量", file=sys.stderr)


# ---------------------------------------------------------------------------
# 消息解码
# ---------------------------------------------------------------------------

def _try_decompress(blob: bytes) -> bytes | None:
    """如果 blob 是 zstd 压缩数据，返回解压结果；否则返回 None。"""
    if _HAS_ZSTD and len(blob) >= 4 and blob[:4] == _ZSTD_MAGIC:
        try:
            return _DCTX.decompress(blob)
        except Exception:
            return None
    return None


def _raw_to_str(raw: Any) -> str | None:
    """将原始字段值转为字符串（自动尝试 zstd 解压）。"""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        dec = _try_decompress(raw)
        data = dec if dec is not None else raw
        return data.decode("utf-8", errors="replace")
    return str(raw)


def _parse_share_xml(xml_text: str) -> str:
    """从分享消息 XML 中提取标题，返回人类可读字符串。"""
    try:
        sub = ET.fromstring(xml_text)
        title_el = sub.find(".//title")
        if title_el is not None and title_el.text:
            return f"[分享] {title_el.text.strip()}"
    except ET.ParseError:
        pass
    return "[分享]"


def _decode_ref_content(ref_type: int, ref_content_el: ET.Element | None) -> str:
    """解码 <refermsg> 中被引用消息的内容文本。"""
    if ref_type in _MEDIA_LABELS:
        return _MEDIA_LABELS[ref_type]

    raw_ref = (ref_content_el.text or "").strip() if ref_content_el is not None else ""

    if ref_type == 1:
        # 文字消息；但可能自身又是一个 appmsg XML（引用了分享链接）
        if raw_ref.startswith("<?xml") or raw_ref.startswith("<msg"):
            return _parse_share_xml(raw_ref)
        return raw_ref if raw_ref else "[消息]"

    if ref_type == 49:
        # appmsg 类型；content 是 XML
        if raw_ref.startswith("<?xml") or raw_ref.startswith("<msg"):
            return _parse_share_xml(raw_ref)
        return "[分享]"

    return "[消息]"


def _decode_appmsg_xml(xml_text: str, other_table_hash: str | None = None) -> str | None:
    """
    解析 appmsg 消息的 XML，返回人类可读字符串。

    other_table_hash: 对方 wxid 的 MD5（即消息表名去掉 'Msg_' 前缀），
    用于判断引用消息的发送方。双人聊天必传；群聊可不传。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    appmsg = root.find("appmsg")
    if appmsg is None:
        return None

    type_el = appmsg.find("type")
    atype_str = (type_el.text or "").strip() if type_el is not None else ""
    atype = int(atype_str) if atype_str.isdigit() else 0

    title_el = appmsg.find("title")
    title = (title_el.text or "").strip() if title_el is not None else ""

    # ---- 引用回复 (appmsg type=57) ----------------------------------------
    if atype == 57:
        refermsg = appmsg.find("refermsg")
        if refermsg is None:
            return title or None

        ref_type_el = refermsg.find("type")
        ref_type_str = (ref_type_el.text or "").strip() if ref_type_el is not None else ""
        ref_type = int(ref_type_str) if ref_type_str.isdigit() else 0

        ref_content_el = refermsg.find("content")
        ref_fromusr_el = refermsg.find("fromusr")
        ref_fromusr = (ref_fromusr_el.text or "").strip() if ref_fromusr_el is not None else ""

        ref_content = _decode_ref_content(ref_type, ref_content_el)

        # 判断被引用消息的发送方
        if other_table_hash and ref_fromusr:
            ref_label = "对方" if hashlib.md5(ref_fromusr.encode()).hexdigest() == other_table_hash else "用户"
        else:
            ref_label = "?"

        reply_text = title if title else "[回复]"
        return f"「引用 {ref_label}：{ref_content}」{reply_text}"

    # ---- 链接/卡片分享 (appmsg type=4,5,1,6,…) ----------------------------
    url_el = appmsg.find("url")
    url = (url_el.text or "").strip() if url_el is not None else ""

    if title and url:
        return f"[分享] {title} {url}"
    if title:
        return f"[分享] {title}"

    return None


def _decode_system(raw: Any) -> str | None:
    """解码 type=10000 系统消息。"""
    text = _raw_to_str(raw)
    if not text:
        return None
    text = text.strip()

    # 搜索 XML 起始位置（部分 system 消息在 zstd 帧头后紧跟 XML）
    for marker in ("<?xml", "<sysmsg"):
        idx = text.find(marker)
        if idx > 0:
            text = text[idx:]
            break

    if "<sysmsg" in text:
        try:
            root = ET.fromstring(text)
            content_el = root.find(".//content")
            if content_el is not None and content_el.text:
                return f"[{content_el.text.strip()}]"
        except ET.ParseError:
            pass

    return None


def decode_content(
    local_type: int,
    raw: Any,
    other_table_hash: str | None = None,
) -> str | None:
    """
    将 SQLite 行中的 (local_type, message_content) 解码为人类可读字符串。
    返回 None 表示此消息应被完全跳过（对话流中不留痕迹）。

    other_table_hash: 对方 wxid 的 MD5（消息表名去掉 'Msg_' 前缀），
    仅双人聊天需要，用于正确标注引用消息发送方。
    """
    # 文字消息
    if local_type == 1:
        text = _raw_to_str(raw)
        if not text:
            return None
        text = text.strip()
        return text if text else None

    # 系统通知
    if local_type == 10000:
        return _decode_system(raw)

    # 媒体类型（binary blob，只标注类型）
    if local_type in _MEDIA_LABELS:
        return _MEDIA_LABELS[local_type]

    # 扩展类型：local_type % 2^32 == 49 → appmsg（zstd 压缩 XML）
    # 编码规律：local_type = appmsg_inner_type × 2^32 + 49
    if local_type > 100 and local_type % (2 ** 32) == 49:
        if not isinstance(raw, bytes):
            return None
        dec = _try_decompress(raw)
        if dec is None:
            if not _HAS_ZSTD:
                return "[需安装 zstandard 库以读取此消息]"
            return None  # 解压失败，静默跳过
        return _decode_appmsg_xml(dec.decode("utf-8", errors="replace"), other_table_hash)

    # 未知类型，静默跳过
    return None


# ---------------------------------------------------------------------------
# 消息拉取
# ---------------------------------------------------------------------------

def detect_sender_ids(db_path: Path, table: str) -> tuple[int, int]:
    """
    自动推断双人会话的 (my_id, other_id)。
    规律：两个 real_sender_id 中较小的为 my_id，较大的为 other_id。
    若找不到恰好两个发送者，抛出 SystemExit 提示手动指定。
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT real_sender_id FROM {table} WHERE local_type = 1")
    ids = sorted(r[0] for r in cur.fetchall())
    conn.close()
    if len(ids) == 2:
        return ids[0], ids[1]
    raise SystemExit(
        f"错误：找到 {len(ids)} 个发送者 ID {ids}，无法自动推断，请手动指定 --my-id / --other-id"
    )


def fetch_messages(
    db_path: Path,
    table: str,
    since_ts: int | None,
    until_ts: int | None,
) -> list[dict]:
    """从消息表拉取指定时间范围内的全部消息（不做类型过滤）。"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    conditions = []
    params = []
    if since_ts is not None:
        conditions.append("create_time >= ?")
        params.append(since_ts)
    if until_ts is not None:
        conditions.append("create_time < ?")
        params.append(until_ts)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    cur.execute(
        f"SELECT real_sender_id, create_time, message_content, local_type FROM {table}"
        f"{where} ORDER BY create_time ASC",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"sender_id": r[0], "ts": r[1], "content": r[2], "local_type": r[3]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 压缩输出
# ---------------------------------------------------------------------------

def compress(messages: list[dict], format_fn, threshold: int, tz: timezone) -> tuple[str, int]:
    """
    将消息列表压缩为带时段分隔的文本。

    format_fn(msg) -> (sender_label, content) | None
        返回 None 表示跳过该消息。

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
