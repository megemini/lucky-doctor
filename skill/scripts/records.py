#!/usr/bin/env python3
"""
records.py - Medicine records management + drug conflict detection.

This is the "personal drug assistant" backend for the Lucky Doctor skill.
It stores user's medicine records in a local JSON file and provides:
  - CRUD: list / search / get / add / update / remove
  - Conflict detection: check a new medicine against historical records

Usage:
    python records.py list
    python records.py search <keyword>
    python records.py get <id_or_name>
    python records.py add <records.json_or_metadata.json>
    python records.py update <id> <changes.json>
    python records.py remove <id_or_name>
    python records.py check-conflict <metadata.json>
    python records.py history <id_or_name>
    python records.py on/off <id_or_name>   # activate / stop (soft)
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("lucky_doctor")

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "medicine_records.json"
CONFLICTS_FILE = Path(__file__).resolve().parent.parent / "data" / "conflicts.json"

DEFAULT_RECORD = {
    "generic_name": "",
    "ingredients": [],
    "category": "",
    "function": [],
    "manufacturer": "",
    "keywords": [],
    "indications": "",
    "contraindications": "",
    "usage_summary": "",
    "audio_path": "",
    "package_path": "",
    "status": "active",
    "speaker": "vivian",
    "language": "chinese",
}

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _load_records():
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _save_records(records):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _load_conflicts():
    if not CONFLICTS_FILE.exists():
        return {"disclaimer": "", "conflict_pairs": [], "duplicate_category_pairs": [], "categories_of_concern": []}
    with open(CONFLICTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize(text):
    if not text:
        return ""
    return str(text).strip().lower()


def _norm_ingredients(ingredients):
    return [_normalize(x) for x in ingredients if x]


def _find_by_name(records, name):
    name = _normalize(name)
    if not name:
        return None
    # exact medicine_name match
    for rec in records:
        if _normalize(rec.get("medicine_name")) == name:
            return rec
    # generic_name match
    for rec in records:
        if _normalize(rec.get("generic_name")) == name:
            return rec
    # prefix match on medicine_name (e.g. user says "感冒灵" for "感冒灵颗粒")
    prefix_hits = []
    for rec in records:
        mn = _normalize(rec.get("medicine_name"))
        if name and mn.startswith(name):
            prefix_hits.append(rec)
    return prefix_hits[0] if len(prefix_hits) == 1 else None


def _find_by_id(records, rec_id):
    for rec in records:
        if rec.get("id") == rec_id:
            return rec
    return None


# ---------------------------------------------------------------------------
# Conflict detection (deterministic rules)
# ---------------------------------------------------------------------------

def _substring_hits(needle, targets):
    """Return list of ingredient-like tokens in targets that contain needle (or vice versa)."""
    hits = []
    needle = _normalize(needle)
    if not needle:
        return hits
    for t in targets:
        t = _normalize(t)
        if needle and t and (needle in t or t in needle):
            hits.append(t)
    return hits


def check_conflict(new_record, records=None, conflicts=None):
    """Deterministic conflict check of new_record against active history records."""
    records = records if records is not None else _load_records()
    conflicts = conflicts if conflicts is not None else _load_conflicts()

    new_name = _normalize(new_record.get("medicine_name"))
    new_ingredients = _norm_ingredients(new_record.get("ingredients", []))
    new_category = _normalize(new_record.get("category"))
    new_function = [ _normalize(x) for x in new_record.get("function", []) if x ]
    new_raw = _normalize(new_record.get("medicine_name"))

    overlaps = []
    conflicts_list = []
    infos = []
    dup_records = []

    for rec in records:
        # Skip the new record itself (only relevant when adding to existing)
        if rec.get("medicine_name") and _normalize(rec.get("medicine_name")) == new_name:
            dup_records.append({
                "target": rec.get("medicine_name"),
                "id": rec.get("id"),
                "type": "duplicate_record",
                "severity": "high",
                "reason": "历史记录中已存在同名药品，可能重复保存",
            })
            continue

        rec_ingredients = _norm_ingredients(rec.get("ingredients", []))
        rec_category = _normalize(rec.get("category"))
        rec_name = rec.get("medicine_name", "")

        # 1. Ingredient overlap -> duplicate (possible duplicate medication)
        matched = set(new_ingredients) & set(rec_ingredients)
        if matched:
            overlaps.append({
                "target": rec_name,
                "id": rec.get("id"),
                "type": "duplicate",
                "severity": "high",
                "reason": "有效成分重叠，可能存在重复用药",
                "matched_ingredients": sorted(matched),
            })
            continue

        # 2. Same category with dangerous category -> info / conflict
        if new_category and rec_category and new_category == rec_category:
            infos.append({
                "target": rec_name,
                "id": rec.get("id"),
                "type": "same_category",
                "severity": "info",
                "reason": f"与历史药品\"{rec_name}\"属于同一分类({new_category})，请注意是否重复治疗",
            })

    # 3. Built-in conflict pairs (substring matching on names+ingredients+functions)
    new_tokens = [new_raw]
    new_tokens += new_ingredients
    new_tokens += new_function

    for pair in conflicts.get("conflict_pairs", []):
        a = _normalize(pair.get("a"))
        b = _normalize(pair.get("b"))
        a_hits = _substring_hits(a, new_tokens) or _substring_hits(a, [new_name])
        b_hits_between = []
        for rec in records:
            rec_tokens = [_normalize(rec.get("medicine_name", ""))]
            rec_tokens += _norm_ingredients(rec.get("ingredients", []))
            if _substring_hits(b, rec_tokens):
                b_hits_between.append(rec)

        # new matches a, history matches b
        if a_hits and b_hits_between:
            for rec in b_hits_between:
                conflicts_list.append({
                    "target": rec.get("medicine_name"),
                    "id": rec.get("id"),
                    "type": "interaction",
                    "severity": pair.get("severity", "medium"),
                    "reason": f"{pair.get('a')}与{pair.get('b')}相互作用：{pair.get('reason')}",
                })
        # new matches b, history matches a
        b_hits = _substring_hits(b, new_tokens) or _substring_hits(b, [new_name])
        if b_hits and not a_hits:
            a_hits_between = []
            for rec in records:
                rec_tokens = [_normalize(rec.get("medicine_name", ""))]
                rec_tokens += _norm_ingredients(rec.get("ingredients", []))
                if _substring_hits(a, rec_tokens):
                    a_hits_between.append(rec)
            for rec in a_hits_between:
                conflicts_list.append({
                    "target": rec.get("medicine_name"),
                    "id": rec.get("id"),
                    "type": "interaction",
                    "severity": pair.get("severity", "medium"),
                    "reason": f"{pair.get('a')}与{pair.get('b')}相互作用：{pair.get('reason')}",
                })

    # 4. Duplicate category pairs (e.g. 复方感冒药 + 对乙酰氨基酚)
    for da, db in conflicts.get("duplicate_category_pairs", []):
        da_hits = _substring_hits(da, new_tokens) or _substring_hits(da, [new_name])
        for rec in records:
            rec_tokens = [_normalize(rec.get("medicine_name", ""))]
            rec_tokens += _norm_ingredients(rec.get("ingredients", []))
            db_hits = _substring_hits(db, rec_tokens)
            if da_hits and db_hits:
                overlaps.append({
                    "target": rec.get("medicine_name"),
                    "id": rec.get("id"),
                    "type": "duplicate",
                    "severity": "high",
                    "reason": f"{da}与{db}可能含有相同成分，存在重复用药风险",
                    "matched_ingredients": [],
                })

    # Dedupe by (target + reason)
    def _dedupe(items):
        seen = set()
        out = []
        for it in items:
            key = (it.get("target"), it.get("reason"))
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    return {
        "new_medicine": new_record.get("medicine_name"),
        "duplicate_records": _dedupe(dup_records),
        "overlaps": _dedupe(overlaps),
        "conflicts": _dedupe(conflicts_list),
        "same_category": _dedupe(infos),
        "disclaimer": conflicts.get("disclaimer", ""),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def do_list():
    records = _load_records()
    if not records:
        print(json.dumps([], ensure_ascii=False, indent=2))
        return
    print(json.dumps(records, ensure_ascii=False, indent=2))


def do_search(keyword):
    keyword = _normalize(keyword)
    records = _load_records()
    results = []
    for rec in records:
        haystack = " ".join([
            str(rec.get("medicine_name", "")),
            str(rec.get("generic_name", "")),
            " ".join(rec.get("keywords", [])),
            " ".join(rec.get("ingredients", [])),
            str(rec.get("category", "")),
        ]).lower()
        if keyword in haystack:
            results.append(rec)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def do_get(key):
    records = _load_records()
    rec = _find_by_id(records, key) or _find_by_name(records, key)
    if rec is None:
        print(json.dumps({"error": f"未找到记录: {key}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(rec, ensure_ascii=False, indent=2))


def do_update(rec_id, changes_file):
    records = _load_records()
    rec = _find_by_id(records, rec_id)
    if rec is None:
        print(json.dumps({"error": f"未找到 id: {rec_id}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    changes = _load_input(changes_file, must_be_object=True)
    for k, v in changes.items():
        rec[k] = v
    rec["last_updated"] = _now()
    _save_records(records)
    print(json.dumps({"status": "updated", "id": rec_id, "record": rec}, ensure_ascii=False, indent=2))


def do_set_status(key, status):
    records = _load_records()
    rec = _find_by_id(records, key) or _find_by_name(records, key)
    if rec is None:
        print(json.dumps({"error": f"未找到记录: {key}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    rec["status"] = status
    rec["last_updated"] = _now()
    _save_records(records)
    print(json.dumps({"status": status, "id": rec.get("id"), "medicine_name": rec.get("medicine_name")}, ensure_ascii=False, indent=2))


def do_add(data):
    # Accept either a single record or a metadata dict
    record = dict(DEFAULT_RECORD)
    record.update({k: v for k, v in data.items() if v is not None})

    if not record.get("medicine_name"):
        print(json.dumps({"error": "medicine_name 不能为空"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    records = _load_records()

    # Dedup by medicine_name
    existing = _find_by_name(records, record["medicine_name"])
    if existing is not None:
        existing_id = existing.get("id")
        record["id"] = existing_id
        record["added_at"] = existing.get("added_at", _now())
        record["last_updated"] = _now()
        # preserve audio/package if not provided
        for field in ("audio_path", "package_path"):
            if not record.get(field):
                record[field] = existing.get(field, "")
        idx = records.index(existing)
        records[idx] = record
        _save_records(records)
        print(json.dumps({"status": "updated", "id": existing_id, "record": record}, ensure_ascii=False, indent=2))
        return record

    record["id"] = str(uuid.uuid4())
    record["added_at"] = record.get("added_at") or _now()
    record["last_updated"] = _now()
    records.append(record)
    _save_records(records)
    print(json.dumps({"status": "added", "id": record["id"], "record": record}, ensure_ascii=False, indent=2))
    return record


def do_remove(key):
    records = _load_records()
    rec = _find_by_id(records, key) or _find_by_name(records, key)
    if rec is None:
        print(json.dumps({"error": f"未找到记录: {key}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    records.remove(rec)
    _save_records(records)
    print(json.dumps({"status": "removed", "id": rec.get("id"), "medicine_name": rec.get("medicine_name")}, ensure_ascii=False, indent=2))


def do_history(key):
    records = _load_records()
    rec = _find_by_id(records, key) or _find_by_name(records, key)
    if rec is None:
        print(json.dumps({"error": f"未找到记录: {key}"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"record": rec, "history_note": "单机 JSON 存储，仅保存最新状态。当前为全量记录。"}, ensure_ascii=False, indent=2))


def do_check_conflict(new_file):
    new_record = _load_input(new_file, must_be_object=True)
    result = check_conflict(new_record)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _load_input(path_or_json, must_be_object=False):
    p = Path(path_or_json)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        try:
            data = json.loads(path_or_json)
        except json.JSONDecodeError:
            print(json.dumps({"error": f"无法解析输入: {path_or_json}"}, ensure_ascii=False, indent=2))
            sys.exit(1)
    if must_be_object and not isinstance(data, dict):
        print(json.dumps({"error": "输入必须是 JSON 对象"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lucky Doctor records management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    p_search = sub.add_parser("search"); p_search.add_argument("keyword")
    p_get = sub.add_parser("get"); p_get.add_argument("key")
    p_add = sub.add_parser("add"); p_add.add_argument("file")
    p_update = sub.add_parser("update"); p_update.add_argument("id"); p_update.add_argument("file")
    p_remove = sub.add_parser("remove"); p_remove.add_argument("key")
    p_check = sub.add_parser("check-conflict"); p_check.add_argument("file")
    p_history = sub.add_parser("history"); p_history.add_argument("key")
    p_on = sub.add_parser("on"); p_on.add_argument("key")
    p_off = sub.add_parser("off"); p_off.add_argument("key")

    args = parser.parse_args()

    if args.command == "list":
        do_list()
    elif args.command == "search":
        do_search(args.keyword)
    elif args.command == "get":
        do_get(args.key)
    elif args.command == "add":
        do_add(_load_input(args.file))
    elif args.command == "update":
        do_update(args.id, args.file)
    elif args.command == "remove":
        do_remove(args.key)
    elif args.command == "check-conflict":
        do_check_conflict(args.file)
    elif args.command == "history":
        do_history(args.key)
    elif args.command == "on":
        do_set_status(args.key, "active")
    elif args.command == "off":
        do_set_status(args.key, "stopped")


if __name__ == "__main__":
    main()
