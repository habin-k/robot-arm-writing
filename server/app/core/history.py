"""글씨 쓰기 이용 내역 저장소.

사용자가 실행(execute)할 때마다 닉네임·문구·폰트·크기·여백·쓰기방식·시각을 기록한다.
서버 재시작 후에도 남도록 JSON 파일(server/writing_history.json)에 함께 저장한다.
in-memory 리스트가 원본이고 파일은 영속화용 — 앱 전체가 in-memory 상태 저장소를 쓰는
구조와 일관되게, 별도 DB 없이 가볍게 유지한다.
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

# server/app/core/history.py → parents[2] = server/
_HISTORY_FILE = Path(__file__).resolve().parents[2] / "writing_history.json"
_MAX_RECORDS = 500

_lock = threading.Lock()
_records: List[dict] = []


def _load() -> None:
    global _records
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _records = data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _records = []
    # 예전 기록(id 없는 것)에 삭제용 고유 id 를 채워 넣는다.
    for r in _records:
        if not r.get("id"):
            r["id"] = uuid.uuid4().hex[:12]


def _save() -> None:
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_records, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 저장 실패해도 서비스는 계속 (내역은 메모리에 남음)


_load()


def add_record(rec: dict) -> dict:
    """이용 기록 1건 추가. id(고유)·created_at(로컬 시각, ISO8601)을 서버가 채운다."""
    rec = {
        **rec,
        "id": uuid.uuid4().hex[:12],
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with _lock:
        _records.append(rec)
        if len(_records) > _MAX_RECORDS:
            del _records[:-_MAX_RECORDS]
        _save()
    return rec


def list_records(limit: int = 100) -> List[dict]:
    """최근 기록부터(내림차순) 최대 limit건 반환."""
    with _lock:
        return list(reversed(_records[-limit:]))


def delete_records(ids: List[str]) -> int:
    """id 목록에 해당하는 기록을 삭제하고 삭제 건수를 반환한다."""
    id_set = set(ids)
    if not id_set:
        return 0
    with _lock:
        before = len(_records)
        _records[:] = [r for r in _records if r.get("id") not in id_set]
        removed = before - len(_records)
        if removed:
            _save()
    return removed


def clear_records() -> int:
    """전체 기록을 삭제하고 삭제 건수를 반환한다."""
    with _lock:
        removed = len(_records)
        _records.clear()
        if removed:
            _save()
    return removed
