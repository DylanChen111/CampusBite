"""SQLite connection and validated, transactional fixture initialization."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .seed import NOTICE, UPDATED_AT, VERSION, seed_data
from .validation import DataValidationError, decode_row, validate_record

DEFAULT_DB = Path(__file__).resolve().parents[1] / "storage" / "campusbite.sqlite3"
JSON_FIELDS = {"business_hours", "meal_periods", "taste_tags", "dietary_tags",
               "ingredients", "avoid_tags", "allergens", "possible_allergens"}


@contextmanager
def connection(path=DEFAULT_DB, *, create=False):
    path = Path(path).resolve()
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        raise FileNotFoundError(f"数据库尚未初始化: {path}")
    uri = path.as_uri() + ("?mode=rwc" if create else "?mode=ro")
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def insert_record(conn, table, record):
    if table not in {"restaurants", "dishes"}:
        raise DataValidationError("未知数据表")
    validate_record(record, "restaurant" if table == "restaurants" else "dish")
    fields = list(record)
    values = [json.dumps(record[f], ensure_ascii=False) if f in JSON_FIELDS and record[f] is not None
              else record[f] for f in fields]
    # Table and column names come only from validated internal records.
    allowed = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if not set(fields) <= allowed:
        raise DataValidationError("未知数据表或字段")
    existing = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record["id"],)).fetchone()
    if existing is not None:
        if decode_row(existing, "restaurant" if table == "restaurants" else "dish") != record:
            raise DataValidationError(f"{table}: ID {record['id']} 与已有记录冲突，不覆盖现有数据")
        return
    conn.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)


def validate_database(conn):
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise DataValidationError("数据库完整性检查失败")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise DataValidationError("存在无效外键")
    counts = {}
    for table, kind in (("restaurants", "restaurant"), ("dishes", "dish")):
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for row in rows:
            decode_row(row, kind)
        counts[table] = len(rows)
    info = conn.execute("SELECT * FROM dataset_info WHERE id = 1").fetchone()
    if info is None or info["data_version"] != VERSION or info["is_mock"] != 1:
        raise DataValidationError("缺少或不兼容的数据版本说明")
    return counts


def initialize(path=DEFAULT_DB, *, records=None):
    restaurants, dishes = seed_data() if records is None else records
    for kind, items in (("restaurant", restaurants), ("dish", dishes)):
        seen = set()
        for record in items:
            validate_record(record, kind)
            if record["id"] in seen:
                raise DataValidationError(f"{kind}: 重复 ID {record['id']}")
            seen.add(record["id"])
    with connection(path, create=True) as conn:
        conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        with conn:
            info = conn.execute("SELECT * FROM dataset_info WHERE id = 1").fetchone()
            if info is not None and info["data_version"] != VERSION:
                raise DataValidationError("已有数据版本不兼容，须人工制定迁移方案")
            conn.execute("INSERT OR IGNORE INTO dataset_info VALUES (1, 1, ?, 1, ?, ?, ?)",
                         (VERSION, NOTICE, "虚构校园演示参考点，非用户当前位置", UPDATED_AT))
            for table, items in (("restaurants", restaurants), ("dishes", dishes)):
                for record in items:
                    insert_record(conn, table, record)
            return validate_database(conn)
