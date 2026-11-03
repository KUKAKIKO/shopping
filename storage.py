"""쇼핑리스트 데이터 저장/불러오기."""

import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "shopping_list.json"

_TRUE_STRINGS = {"true", "1", "yes", "y", "on"}


class StorageError(Exception):
    """데이터 파일을 저장하지 못했을 때 발생한다."""


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return False


def _to_quantity(value) -> int:
    if isinstance(value, bool):  # bool은 int의 하위 타입이라 먼저 걸러낸다
        return 1
    try:
        qty = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 1
    return qty if qty >= 1 else 1


def normalize_items(raw) -> list[dict]:
    """파일에서 읽은 데이터를 PRD 4장 데이터 모델에 맞게 정리한다.

    - dict가 아니거나 이름이 비어 있는 항목은 버린다.
    - 이름이 숫자면 문자열로 바꾼다.
    - quantity / checked / created_at은 올바른 타입으로 바꾸고, 바꿀 수 없으면 기본값을 쓴다.
    - id가 없거나 중복이면 새 id를 붙인다.
    """
    if not isinstance(raw, list):
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, bool) or not isinstance(name, (str, int, float)):
            continue
        name = str(name).strip()
        if not name:
            continue
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id.strip() or item_id in seen:
            item_id = _new_id()
            while item_id in seen:
                item_id = _new_id()
        seen.add(item_id)
        created_at = entry.get("created_at")
        items.append({
            "id": item_id,
            "name": name,
            "quantity": _to_quantity(entry.get("quantity", 1)),
            "checked": _to_bool(entry.get("checked", False)),
            "created_at": created_at if isinstance(created_at, str) else _now(),
        })
    return items


def load_items() -> list[dict]:
    """JSON 파일에서 아이템 목록을 불러온다.

    파일이 없거나 손상되면 빈 리스트를 반환한다.
    내용을 정리하면서 값이 바뀌었다면(예: 새 id 부여) 파일에도 반영해,
    다음에 불러올 때 같은 id가 유지되게 한다.
    """
    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []
    items = normalize_items(raw)
    if items != raw:
        try:
            save_items(items)
        except StorageError:
            pass  # 읽기는 성공했으니 화면은 보여주고, 저장 오류는 다음 변경 때 알린다
    return items


def save_items(items: list[dict]) -> None:
    """아이템 목록을 JSON 파일로 저장한다.

    임시 파일에 먼저 쓴 뒤 원래 파일과 교체해, 저장 도중 중단돼도 기존 파일이 깨지지 않게 한다.
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=DATA_FILE.parent, prefix=".shopping_list.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, DATA_FILE)
        tmp_path = None
    except OSError as e:
        reason = e.strerror or e.__class__.__name__
        raise StorageError(
            "변경 내용을 저장하지 못했습니다. "
            f"'{DATA_FILE.name}' 파일이 다른 프로그램에서 열려 있거나 쓰기 권한이 없는지 확인해주세요. "
            f"(원인: {reason})"
        ) from e
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def create_item(name: str, quantity: int = 1) -> dict:
    """PRD 4장 데이터 모델에 맞는 새 아이템을 만든다."""
    return {
        "id": _new_id(),
        "name": name,
        "quantity": quantity,
        "checked": False,
        "created_at": _now(),
    }
