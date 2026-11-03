"""쇼핑리스트 Streamlit 앱."""

import json
import re
from typing import Callable

import streamlit as st

from storage import StorageError, create_item, load_items, save_items

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒")

EMPTY_NAME_WARNING = "아이템 이름을 입력해주세요."

# Streamlit은 화면 폭 640px 미만에서 st.columns를 세로로 쌓는다.
# 목록의 한 행(체크 | 이름 | 수량 | 버튼)이 모바일에서도 한 줄로 유지되도록 최소한으로 덮어쓴다.
MOBILE_CSS = """
<style>
@media (max-width: 640px) {
  div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.4rem !important;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 0 !important;
  }
  div[data-testid="stFormSubmitButton"] button { padding-left: 0.5rem; padding-right: 0.5rem; }
}
div[data-testid="stFormSubmitButton"] button p { white-space: nowrap; }
/* 긴 이름이 행을 밀어내지 않도록 줄바꿈 */
div[data-testid="stColumn"] p { overflow-wrap: anywhere; }
</style>
"""


# ---------- 상태 ----------

def init_state() -> None:
    for key in ("editing_id", "edit_error", "add_error", "save_error"):
        st.session_state.setdefault(key, None)


def get_items() -> list[dict]:
    return st.session_state["items"]


def find_in(items: list[dict], item_id: str) -> dict | None:
    return next((it for it in items if it["id"] == item_id), None)


def mutate(change: Callable[[list[dict]], object]):
    """파일에서 최신 목록을 읽어 change를 적용하고 바로 저장한다.

    탭/기기마다 따로 들고 있던 목록으로 파일을 덮어쓰면 다른 탭의 변경이 사라지므로,
    모든 변경은 '읽기 → 수정 → 저장'을 한 번에 처리한다.
    저장에 실패하면 화면 상단에 오류를 띄우고 None을 반환한다.
    """
    items = load_items()
    result = change(items)
    try:
        save_items(items)
    except StorageError as e:
        st.session_state["save_error"] = str(e)
        return None
    st.session_state["save_error"] = None
    st.session_state["items"] = items
    return result


def escape_md(text: str) -> str:
    """사용자 입력이 마크다운으로 해석되지 않도록 특수문자를 이스케이프한다."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~<>$:])", r"\\\1", text)


def clear_edit() -> None:
    st.session_state["editing_id"] = None
    st.session_state["edit_error"] = None


# ---------- 콜백 (위젯 렌더링 전에 실행되어 클릭 한 번에 반영됨) ----------

def on_add() -> None:
    name = st.session_state.get("new_name", "").strip()
    quantity = int(st.session_state.get("new_qty", 1))
    if not name:
        st.session_state["add_error"] = EMPTY_NAME_WARNING
        return
    st.session_state["add_error"] = None
    if mutate(lambda items: items.append(create_item(name, quantity)) or True):
        st.toast(f"'{name}' 추가됨", icon="✅")


def on_toggle_check(item_id: str) -> None:
    checked = bool(st.session_state[f"check_{item_id}"])

    def change(items):
        item = find_in(items, item_id)
        if item is not None:
            item["checked"] = checked

    mutate(change)


def on_start_edit(item_id: str) -> None:
    item = find_in(load_items(), item_id)
    if item is None:
        st.toast("이미 삭제된 아이템입니다.", icon="⚠️")
        return
    st.session_state["editing_id"] = item_id
    st.session_state["edit_error"] = None
    # 편집 입력창을 현재 값으로 채움
    st.session_state[f"edit_name_{item_id}"] = item["name"]
    st.session_state[f"edit_qty_{item_id}"] = item["quantity"]


def on_save_edit(item_id: str) -> None:
    name = st.session_state.get(f"edit_name_{item_id}", "").strip()
    if not name:
        st.session_state["edit_error"] = EMPTY_NAME_WARNING
        return
    quantity = int(st.session_state.get(f"edit_qty_{item_id}", 1))

    def change(items):
        item = find_in(items, item_id)
        if item is None:
            return "missing"
        item["name"] = name
        item["quantity"] = quantity
        return "saved"

    result = mutate(change)
    if result is None:
        return  # 저장 실패: 편집 상태를 유지해 입력한 내용을 잃지 않게 한다
    if result == "missing":
        st.toast("다른 곳에서 삭제된 아이템이라 저장하지 못했습니다.", icon="⚠️")
    clear_edit()


def on_cancel_edit() -> None:
    clear_edit()


def on_delete(item_id: str) -> None:
    def change(items):
        item = find_in(items, item_id)
        if item is not None:
            items.remove(item)
        return item

    removed = mutate(change)
    if st.session_state["editing_id"] == item_id:
        clear_edit()
    if removed:
        st.toast(f"'{removed['name']}' 삭제됨", icon="🗑️")


def on_delete_checked() -> None:
    def change(items):
        before = len(items)
        items[:] = [it for it in items if not it["checked"]]
        return before - len(items)

    removed = mutate(change)
    if removed is None:
        return
    if find_in(get_items(), st.session_state["editing_id"] or "") is None:
        clear_edit()
    st.toast(f"구매 완료 항목 {removed}개 삭제됨", icon="🧹")


# ---------- 화면 ----------

def render_progress() -> None:
    items = get_items()
    total = len(items)
    done = sum(1 for it in items if it["checked"])
    st.markdown(f"**{done} / {total}** 구매 완료")
    st.progress(done / total if total else 0.0)


def render_add_form() -> None:
    with st.form("add_form", clear_on_submit=True, border=False):
        col_name, col_qty, col_btn = st.columns([5, 1.6, 1.2], vertical_alignment="bottom")
        with col_name:
            st.text_input("아이템 이름", key="new_name", placeholder="추가할 아이템 (예: 우유)")
        with col_qty:
            st.number_input("수량", key="new_qty", min_value=1, value=1, step=1)
        with col_btn:
            st.form_submit_button("추가", type="primary", use_container_width=True,
                                  on_click=on_add)
    if st.session_state["add_error"]:
        st.warning(st.session_state["add_error"])
        st.session_state["add_error"] = None  # 한 번만 표시


ROW_COLS = [0.6, 5, 1.2, 1, 1]
EDIT_COLS = [0.6, 4, 1.6, 1, 1]


def render_checkbox(item: dict) -> None:
    key = f"check_{item['id']}"
    # 파일의 최신 값과 위젯 상태를 맞춘다 (다른 탭에서 바뀐 체크 상태 반영).
    st.session_state[key] = item["checked"]
    st.checkbox(
        f"{item['name']} 구매 완료",
        key=key,
        on_change=on_toggle_check,
        args=(item["id"],),
        label_visibility="collapsed",
    )


def render_view_row(item: dict) -> None:
    item_id = item["id"]
    checked = item["checked"]
    col_check, col_name, col_qty, col_edit, col_del = st.columns(
        ROW_COLS, vertical_alignment="center"
    )
    with col_check:
        render_checkbox(item)
    name = escape_md(item["name"])
    qty = f"x{item['quantity']}"
    with col_name:
        st.markdown(f":gray[~~{name}~~]" if checked else name)
    with col_qty:
        st.markdown(f":gray[{qty}]" if checked else qty)
    with col_edit:
        st.button("✏️", key=f"edit_{item_id}", help="수정",
                  on_click=on_start_edit, args=(item_id,))
    with col_del:
        st.button("🗑️", key=f"del_{item_id}", help="삭제",
                  on_click=on_delete, args=(item_id,))


def render_edit_row(item: dict) -> None:
    item_id = item["id"]
    col_check, col_name, col_qty, col_save, col_cancel = st.columns(
        EDIT_COLS, vertical_alignment="center"
    )
    with col_check:
        # 편집 중에도 체크 상태가 보이도록 유지 (일괄 삭제 대상인지 알 수 있게)
        render_checkbox(item)
    with col_name:
        st.text_input("이름 수정", key=f"edit_name_{item_id}", label_visibility="collapsed")
    with col_qty:
        st.number_input("수량 수정", min_value=1, step=1, key=f"edit_qty_{item_id}",
                        label_visibility="collapsed")
    with col_save:
        st.button("💾", key=f"save_{item_id}", help="저장", type="primary",
                  on_click=on_save_edit, args=(item_id,))
    with col_cancel:
        st.button("↩️", key=f"cancel_{item_id}", help="취소", on_click=on_cancel_edit)
    if st.session_state["edit_error"]:
        st.warning(st.session_state["edit_error"])


def render_item_list() -> None:
    items = get_items()
    if find_in(items, st.session_state["editing_id"] or "") is None:
        clear_edit()  # 편집하던 아이템이 다른 곳에서 삭제된 경우
    if not items:
        st.info("쇼핑리스트가 비어 있습니다.")
        return
    for item in items:
        if item["id"] == st.session_state["editing_id"]:
            render_edit_row(item)
        else:
            render_view_row(item)


def render_footer() -> None:
    has_checked = any(it["checked"] for it in get_items())
    st.divider()
    st.button(
        "체크된 항목 모두 삭제",
        key="delete_checked",
        on_click=on_delete_checked,
        disabled=not has_checked,
    )


def render_button_labels() -> None:
    """아이콘 버튼에 '우유 수정'처럼 아이템 이름이 들어간 접근성 이름(aria-label)을 붙인다.

    Streamlit 버튼은 aria-label을 지정할 수 없어서, key로 생기는 CSS 클래스
    (st-key-<key>)를 찾아 스크립트로 붙인다.
    """
    labels = {}
    for it in get_items():
        i, n = it["id"], it["name"]
        labels.update({
            f"edit_{i}": f"{n} 수정", f"del_{i}": f"{n} 삭제",
            f"save_{i}": f"{n} 저장", f"cancel_{i}": f"{n} 수정 취소",
        })
    # <, >, & 를 유니코드 이스케이프해서 이름에 '</script>' 같은 문자열이 있어도 스크립트가 깨지지 않게 한다.
    data = (
        json.dumps(labels, ensure_ascii=False)
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    st.html(
        f"""<script>
(() => {{
  window.__shopLabels = {data};
  const apply = () => {{
    for (const [key, label] of Object.entries(window.__shopLabels)) {{
      document.querySelectorAll('.st-key-' + CSS.escape(key) + ' button').forEach(b => {{
        if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
      }});
    }}
  }};
  apply();
  if (!window.__shopLabelObserver) {{
    let pending = false;
    window.__shopLabelObserver = new MutationObserver(() => {{
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {{ pending = false; apply(); }});
    }});
    window.__shopLabelObserver.observe(document.body, {{ childList: true, subtree: true }});
  }}
}})();
</script>""",
        unsafe_allow_javascript=True,
    )


def main() -> None:
    init_state()
    # 매 실행마다 파일에서 최신 목록을 읽는다 (다른 탭/기기의 변경 반영).
    st.session_state["items"] = load_items()
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑리스트")
    if st.session_state["save_error"]:
        st.error(st.session_state["save_error"])
    render_progress()
    render_add_form()
    render_item_list()
    render_footer()
    render_button_labels()


main()
