import io
import json
import re
import urllib.parse
import uuid
from datetime import date, datetime, time, timezone

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from PIL import Image, ImageOps

st.set_page_config(page_title="우리의 스마트 여행 플래너 ✈️", layout="wide")

# ==========================================
# Supabase 접속 정보 (Streamlit Secrets)
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].strip().rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()
except Exception:
    st.error("Supabase 접속 정보가 없어요. Streamlit 앱 Settings → Secrets에 "
             "SUPABASE_URL 과 SUPABASE_KEY 를 등록해 주세요.")
    st.stop()

BUCKET = "photos"
API_TIMEOUT = 15

# ==========================================
# 설정 / 상수
# ==========================================
LIST_KEYS = ["flights", "hotels", "spots", "videos", "expenses", "photos", "schedule", "checklist"]
CATEGORIES = {"놀거리/관광지": "🎡", "맛집/카페": "🍴", "쇼핑": "🛍️", "기타": "📌"}
AIRLINES = ["제주항공", "에어부산", "에어서울", "이스타항공", "기타"]
MODE_OPTIONS = ["📂 기존 여행 선택하기", "➕ 새 여행 만들기"]

# 이름: (야후 파이낸스 티커, 표시 배수)
RATE_TICKERS = {
    "엔화 (100JPY/KRW)": ("JPYKRW=X", 100),
    "달러 (USD/KRW)": ("USDKRW=X", 1),
    "유로 (EUR/KRW)": ("EURKRW=X", 1),
    "베트남 동 (100VND/KRW)": ("VNDKRW=X", 100),
}

# 국가별 긴급 연락처 (키워드는 영문은 단어 단위, 한글은 포함 여부로 매칭)
CONSULAR_CALL = "• 외교부 영사콜센터: +82-2-3210-0404 (24시간)"
EMBASSY_NOTE = "• 현지 한국대사관 연락처는 외교부(mofa.go.kr) 또는 '해외안전여행' 앱에서 확인하세요."
EMERGENCY_DB = [
    {
        "keywords": ["tokyo", "osaka", "fukuoka", "sapporo", "kyoto", "okinawa", "japan",
                     "도쿄", "오사카", "후쿠오카", "삿포로", "교토", "오키나와", "일본"],
        "text": "• 경찰: 110 / 소방·구급: 119",
    },
    {
        "keywords": ["new york", "los angeles", "san francisco", "hawaii", "guam", "usa", "canada",
                     "뉴욕", "로스앤젤레스", "샌프란시스코", "하와이", "괌", "미국", "캐나다"],
        "text": "• 긴급 통합 신고(경찰/구급/소방): 911",
    },
    {
        "keywords": ["paris", "london", "rome", "barcelona", "vienna", "prague", "france", "uk", "italy",
                     "spain", "europe", "파리", "런던", "로마", "바르셀로나", "비엔나", "프라하",
                     "유럽", "프랑스", "영국", "이탈리아", "스페인"],
        "text": "• 유럽 통합 긴급신고: 112",
    },
    {
        "keywords": ["danang", "da nang", "hanoi", "ho chi minh", "nha trang", "vietnam",
                     "다낭", "하노이", "호치민", "나트랑", "베트남"],
        "text": "• 경찰: 113 / 구급: 115 / 소방: 114",
    },
    {
        "keywords": ["bangkok", "phuket", "chiang mai", "thailand", "방콕", "푸켓", "치앙마이", "태국"],
        "text": "• 경찰: 191 / 구급: 1669 / 관광경찰: 1155",
    },
    {
        "keywords": ["taipei", "taiwan", "타이페이", "타이베이", "대만"],
        "text": "• 경찰: 110 / 소방·구급: 119",
    },
    {
        "keywords": ["singapore", "싱가포르"],
        "text": "• 경찰: 999 / 구급·소방: 995",
    },
]


def _kw_match(loc: str, keyword: str) -> bool:
    if keyword.isascii():
        return re.search(rf"\b{re.escape(keyword)}\b", loc) is not None
    return keyword in loc


def get_auto_emergency_contacts(location_str: str) -> str:
    loc = (location_str or "").lower()
    for entry in EMERGENCY_DB:
        if any(_kw_match(loc, k) for k in entry["keywords"]):
            return "\n".join([entry["text"], CONSULAR_CALL, EMBASSY_NOTE])
    return "\n".join(["• 현지 경찰/구급차 번호 확인 필요", CONSULAR_CALL, EMBASSY_NOTE])


# ==========================================
# 데이터 계층 (Supabase)
# ==========================================
def new_id() -> str:
    return uuid.uuid4().hex[:10]


def spot_label(spot: dict) -> str:
    return f"{CATEGORIES.get(spot.get('분류'), '📌')} {spot.get('장소명', '')}"


def hotel_label(hotel: dict) -> str:
    return f"🏢 {hotel.get('숙소명', '')}"


def normalize(data: dict) -> dict:
    """예전 형식의 데이터를 현재 구조로 보정 (모든 항목에 고유 id 부여, 같은 날짜 일정 병합)."""
    for trip in data.values():
        trip.setdefault("info", {})
        trip["info"].setdefault("id", new_id())
        trip["info"].setdefault("city", "")
        trip["info"].setdefault("period", "")
        trip.setdefault("members", [])
        trip.setdefault("embassy", "")
        for key in LIST_KEYS:
            trip.setdefault(key, [])
        for key in ["flights", "hotels", "spots", "videos", "expenses", "checklist", "photos"]:
            for item in trip[key]:
                item.setdefault("id", new_id())
        for s in trip["spots"]:
            if "장소명" not in s:
                s["장소명"] = s.get("이름", "")
            s.setdefault("show_on_map", False)
            s.setdefault("주소", "")
            s.setdefault("메모", "")
        for h in trip["hotels"]:
            h.setdefault("show_on_map", False)
            h.setdefault("상태", "후보")
            h.setdefault("메모", "")
        for v in trip["videos"]:
            if "설명" not in v:
                v["설명"] = v.get("제목", "")

        merged = {}
        for sch in trip["schedule"]:
            d = sch.get("날짜", "미분류")
            m = merged.setdefault(d, {"id": sch.get("id") or new_id(), "날짜": d, "장소목록": [], "메모": ""})
            for p in sch.get("장소목록", []):
                if p not in m["장소목록"]:
                    m["장소목록"].append(p)
            memo = sch.get("메모") or sch.get("내용") or ""
            if memo and memo not in m["메모"]:
                m["메모"] = (m["메모"] + "\n" + memo).strip()
        trip["schedule"] = sorted(merged.values(), key=lambda x: x["날짜"])
    return data


def _headers(content_type="application/json", extra=None) -> dict:
    h = {"apikey": SUPABASE_KEY}
    if SUPABASE_KEY.startswith("eyJ"):  # 예전 방식(JWT) 키일 때만 Authorization 헤더 사용
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if content_type:
        h["Content-Type"] = content_type
    if extra:
        h.update(extra)
    return h


def _check(resp, action: str) -> None:
    if not resp.ok:
        raise RuntimeError(f"{action} 실패 ({resp.status_code}): {resp.text[:300]}")


def db_read():
    url = f"{SUPABASE_URL}/rest/v1/planner_data"
    r = requests.get(url, headers=_headers(), params={"id": "eq.1", "select": "data,version"},
                     timeout=API_TIMEOUT)
    _check(r, "데이터 읽기")
    rows = r.json()
    if rows:
        return rows[0].get("data") or {}, int(rows[0].get("version") or 0)
    r = requests.post(url, headers=_headers(extra={"Prefer": "resolution=ignore-duplicates"}),
                      json={"id": 1, "data": {}}, timeout=API_TIMEOUT)
    _check(r, "초기 데이터 생성")
    return {}, 0


def db_write(data: dict, version: int) -> bool:
    """version이 그대로일 때만 저장 (그 사이 다른 사람이 저장했다면 False)."""
    url = f"{SUPABASE_URL}/rest/v1/planner_data"
    r = requests.patch(
        url,
        headers=_headers(extra={"Prefer": "return=representation"}),
        params={"id": "eq.1", "version": f"eq.{version}"},
        json={"data": data, "version": version + 1, "updated_at": datetime.now(timezone.utc).isoformat()},
        timeout=API_TIMEOUT,
    )
    _check(r, "데이터 저장")
    return len(r.json()) > 0


def load_data():
    data, ver = {}, 0
    for _ in range(3):
        raw, ver = db_read()
        before = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        data = normalize(raw)
        if json.dumps(data, sort_keys=True, ensure_ascii=False) == before:
            return data, ver
        if db_write(data, ver):  # 보정한 결과(새 id 등)를 바로 저장해 둔다
            return data, ver + 1
    return data, ver


def mutate(trip_name, fn) -> bool:
    """최신 데이터를 읽어 수정 후 저장. 동시에 누가 저장했으면 자동으로 다시 시도.
    trip_name이 None이면 fn(전체 데이터), 아니면 fn(해당 여행)."""
    for _ in range(5):
        data, ver = load_data()
        if trip_name is None:
            fn(data)
        else:
            trip = data.get(trip_name)
            if trip is None:
                return False
            fn(trip)
        if db_write(data, ver):
            return True
    st.error("다른 사람이 동시에 수정 중이라 저장하지 못했어요. 잠시 후 다시 시도해 주세요.")
    return False


def find(items: list, item_id: str):
    return next((i for i in items if i.get("id") == item_id), None)


def append_item(trip_name, list_key, record) -> bool:
    return mutate(trip_name, lambda t: t[list_key].append(record))


def set_field(trip_name, key, value) -> bool:
    return mutate(trip_name, lambda t: t.__setitem__(key, value))


def edit_item(trip_name, list_key, item_id, updates, label_fn=None) -> bool:
    def apply(t):
        item = find(t[list_key], item_id)
        if item is None:
            return
        old = label_fn(item) if label_fn else None
        item.update(updates)
        if label_fn:
            rename_place_in_schedule(t, old, label_fn(item))

    return mutate(trip_name, apply)


def remove_place_from_schedule(trip: dict, label: str) -> None:
    for sch in trip["schedule"]:
        sch["장소목록"] = [p for p in sch["장소목록"] if p != label]


def rename_place_in_schedule(trip: dict, old: str, new: str) -> None:
    if old == new:
        return
    for sch in trip["schedule"]:
        sch["장소목록"] = [new if p == old else p for p in sch["장소목록"]]


# ---------- 사진 저장소 (Supabase Storage) ----------
def storage_upload(path: str, content: bytes, mime: str) -> None:
    r = requests.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
                      headers=_headers(content_type=mime), data=content, timeout=60)
    _check(r, "사진 업로드")


def storage_delete(paths) -> None:
    paths = list(paths)
    if not paths:
        return
    try:
        requests.delete(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}",
                        headers=_headers(), json={"prefixes": paths}, timeout=API_TIMEOUT)
    except requests.RequestException:
        pass


@st.cache_data(ttl=3000, show_spinner=False)
def photo_url(path: str):
    try:
        r = requests.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{path}",
                          headers=_headers(), json={"expiresIn": 3600}, timeout=API_TIMEOUT)
        if r.ok:
            signed = r.json().get("signedURL", "")
            if signed.startswith("/storage/v1"):
                return f"{SUPABASE_URL}{signed}"
            return f"{SUPABASE_URL}/storage/v1{signed}"
    except requests.RequestException:
        pass
    return None


def prepare_image(file) -> bytes:
    """회전 보정 + 긴 변 1600px로 줄여 JPEG로 저장 (저장 용량 절약)."""
    img = ImageOps.exif_transpose(Image.open(file)).convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------- 위젯 콜백 ----------
def cb_toggle(trip_name, list_key, item_id, field, widget_key, on_val=True, off_val=False):
    checked = st.session_state[widget_key]

    def apply(trip):
        item = find(trip[list_key], item_id)
        if item is not None:
            item[field] = on_val if checked else off_val

    mutate(trip_name, apply)


def cb_delete(trip_name, list_key, item_id):
    def apply(trip):
        item = find(trip[list_key], item_id)
        if item is None:
            return
        if list_key == "spots":
            remove_place_from_schedule(trip, spot_label(item))
        elif list_key == "hotels":
            remove_place_from_schedule(trip, hotel_label(item))
        elif list_key == "photos":
            storage_delete([item.get("path", "")])
        trip[list_key] = [i for i in trip[list_key] if i.get("id") != item_id]

    mutate(trip_name, apply)


def cb_reset(trip_name, list_key):
    def apply(trip):
        if list_key == "photos":
            storage_delete([p.get("path", "") for p in trip["photos"]])
        if list_key == "spots":
            labels = {spot_label(s) for s in trip["spots"]}
            for sch in trip["schedule"]:
                sch["장소목록"] = [p for p in sch["장소목록"] if p not in labels]
        trip[list_key] = []

    mutate(trip_name, apply)


def cb_schedule_field(trip_name, sch_id, field, widget_key):
    value = st.session_state[widget_key]

    def apply(trip):
        item = find(trip["schedule"], sch_id)
        if item is not None:
            item[field] = list(value) if isinstance(value, (list, tuple)) else value

    mutate(trip_name, apply)


def reset_button(trip_name, trip_id, list_key, label):
    with st.popover(f"🗑️ {label} 전체 초기화"):
        st.warning("정말 모두 삭제할까요? 되돌릴 수 없어요.")
        st.button("네, 삭제합니다", key=f"reset_{list_key}_{trip_id}",
                  on_click=cb_reset, args=(trip_name, list_key))


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ==========================================
# 외부 데이터 (환율 / 날씨)
# ==========================================
@st.cache_data(ttl=3600)
def get_exchange_rates() -> dict:
    rates = {}
    for name, (symbol, multiplier) in RATE_TICKERS.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            rates[name] = round(float(hist["Close"].iloc[-1]) * multiplier, 2) if not hist.empty else None
        except Exception:
            rates[name] = None
    return rates


@st.cache_data(ttl=1800)
def get_weather(city_name: str) -> str:
    try:
        res = requests.get(
            f"https://wttr.in/{urllib.parse.quote(city_name)}",
            params={"format": "%C %t", "m": "", "lang": "ko"},
            timeout=3,
        )
        if res.status_code == 200:
            return res.text.strip()
    except requests.RequestException:
        pass
    return "날씨 정보 조회 불가"


# ==========================================
# 데이터 불러오기 / 사이드바
# ==========================================
try:
    travels, _db_version = load_data()
except Exception as e:  # 접속 정보 오류, 테이블/컬럼 누락 등
    st.error(f"데이터베이스에 연결하지 못했어요.\n\n{e}")
    st.stop()
travel_names = list(travels.keys())

# 새 여행 생성 직후 자동으로 그 여행을 선택 (위젯이 만들어지기 전에 상태를 세팅해야 함)
if "_pending_select" in st.session_state:
    st.session_state["mode"] = MODE_OPTIONS[0]
    st.session_state["selected_travel"] = st.session_state.pop("_pending_select")
if st.session_state.get("selected_travel") not in travel_names:
    st.session_state.pop("selected_travel", None)

st.sidebar.title("🌍 여행 선택 및 관리")
mode = st.sidebar.radio("모드 선택", MODE_OPTIONS, key="mode")
selected_travel = None

if mode == MODE_OPTIONS[1]:
    with st.sidebar.form("new_travel_form"):
        new_name = st.text_input("여행 이름 (예: 도쿄 여행, 뉴욕 여행)")
        new_city = st.text_input("영문 도시명 (날씨/긴급연락처용, 예: Tokyo, New York)")
        new_date = st.text_input("여행 기간 (예: 2026.07.10 ~ 07.15)")
        if st.form_submit_button("여행 폴더 생성"):
            new_name = new_name.strip()
            if not new_name:
                st.sidebar.error("여행 이름을 입력해 주세요.")
            elif new_name in travels:
                st.sidebar.error("이미 존재하는 여행 이름입니다.")
            else:
                target_loc = new_city.strip() or new_name
                record = {
                    "info": {"name": new_name, "city": target_loc, "period": new_date.strip()},
                    "embassy": get_auto_emergency_contacts(target_loc),
                }

                def add_trip(data, _name=new_name, _record=record):
                    if _name not in data:
                        data[_name] = normalize({_name: _record})[_name]

                mutate(None, add_trip)
                st.session_state["_pending_select"] = new_name
                st.rerun()
else:
    if travel_names:
        selected_travel = st.sidebar.selectbox("여행을 선택하세요", travel_names, key="selected_travel")
        with st.sidebar.expander("⚠️ 이 여행 삭제"):
            confirm_del = st.checkbox("정말 삭제합니다", key=f"confirm_del_{selected_travel}")
            if st.button("여행 삭제", disabled=not confirm_del):
                storage_delete([p.get("path", "") for p in travels[selected_travel]["photos"]])
                mutate(None, lambda d, _n=selected_travel: d.pop(_n, None))
                st.session_state.pop("selected_travel", None)
                st.rerun()
    else:
        st.sidebar.warning("등록된 여행이 없습니다. 새 여행을 먼저 만들어주세요!")

with st.sidebar.expander("📥 기존 데이터 가져오기 (travel_data.json)"):
    st.caption("예전에 쓰던 travel_data.json이 있다면 올려서 옮길 수 있어요. 이미 있는 여행 이름은 건너뛰고, 사진은 옮겨지지 않아요.")
    uploaded_json = st.file_uploader("travel_data.json 선택", type=["json"], key="import_json")
    if uploaded_json is not None and st.button("가져오기"):
        try:
            imported = json.load(uploaded_json)
            if not isinstance(imported, dict):
                raise ValueError("올바른 형식이 아니에요.")
        except (ValueError, UnicodeDecodeError) as e:
            st.error(f"파일을 읽지 못했어요: {e}")
        else:
            def import_trips(data, _imp=imported):
                for n, t in _imp.items():
                    if isinstance(t, dict) and n not in data:
                        t["photos"] = []
                        data[n] = t

            mutate(None, import_trips)
            st.rerun()


# ==========================================
# 대시보드
# ==========================================
def build_map_targets(trip: dict, city_query: str) -> dict:
    targets = {}
    for h in trip["hotels"]:
        if h.get("show_on_map"):
            name = h.get("숙소명", "").split("(")[0].strip()
            loc = h.get("위치", "").strip()
            if name:
                targets[f"🏢 {name}"] = f"{name} {loc}" if loc else f"{city_query} {name}"
    for s in trip["spots"]:
        if s.get("show_on_map"):
            name = s.get("장소명", "").split("(")[0].strip()
            addr = s.get("주소", "").strip()
            if name:
                emoji = CATEGORIES.get(s.get("분류"), "📌")
                targets[f"{emoji} {name}"] = f"{name} {addr}" if addr else f"{city_query} {name}"
    return targets


def render_dashboard(trip_name: str, trip: dict, trip_id: str):
    city_query = trip["info"].get("city") or "Seoul"
    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.metric(label=f"🌤️ {city_query} 실시간 날씨", value=get_weather(city_query))

        st.markdown("---")
        st.write("🔱 **실시간 주요 환율**")
        for name, value in get_exchange_rates().items():
            shown = f"{value:,.2f}원" if value else "조회 불가"
            st.caption(f"• **{name}**: {shown}")

        st.markdown("---")
        st.write("🚨 **현지 긴급 연락처**")
        st.info(trip.get("embassy", "").replace("\n", "  \n"))
        with st.popover("✏️ 연락처 정보 수정"):
            with st.form(f"embassy_form_{trip_id}"):
                new_embassy = st.text_area("긴급 연락처 메모", value=trip.get("embassy", ""))
                if st.form_submit_button("💾 저장"):
                    set_field(trip_name, "embassy", new_embassy)
                    st.rerun()
            if st.button("🔄 도시 기준 자동값으로 재설정", key=f"embassy_reset_{trip_id}"):
                set_field(trip_name, "embassy", get_auto_emergency_contacts(city_query))
                st.rerun()

    with col_right:
        st.subheader("🗺️ 장소 확인 지도")
        targets = build_map_targets(trip, city_query)
        if targets:
            label = st.selectbox("🎯 지도에 띄울 장소를 선택하세요", list(targets.keys()),
                                 key=f"map_select_{trip_id}")
            query = targets[label]
            zoom = 16
            caption = f"📍 현재 확인 중인 위치: {query}"
        else:
            query, zoom = city_query, 12
            caption = "💡 숙소나 장소 목록에서 '지도 표시'를 체크하면 여기서 선택할 수 있어요!"
        map_url = f"https://maps.google.com/maps?q={urllib.parse.quote(query)}&t=&z={zoom}&ie=UTF8&iwloc=&output=embed"
        components.iframe(map_url, height=400)
        st.caption(caption)

        if targets:
            queries = list(dict.fromkeys(targets.values()))
            if len(queries) == 1:
                all_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(queries[0], safe="")
            else:
                # 여러 곳은 '경유지'로 이어 붙이면 구글 지도에 전부 표시된다 (한 번에 최대 10곳)
                stops = "/".join(urllib.parse.quote(q, safe="") for q in queries[:10])
                all_url = f"https://www.google.com/maps/dir/{stops}"
            st.link_button(f"🗺️ 지도 표시한 장소 {min(len(queries), 10)}곳 전부 지도에서 보기", all_url)
            if len(queries) > 10:
                st.caption("구글 지도는 한 번에 10곳까지만 열려요. 앞의 10곳만 표시돼요.")
    st.markdown("---")


# ==========================================
# 탭: 항공권
# ==========================================
def render_flights(trip_name: str, trip: dict, trip_id: str):
    with st.form(f"flight_form_{trip_id}"):
        st.subheader("출국편 & 귀국편 입력")
        dep_airline = st.selectbox("출국 항공사", AIRLINES, key=f"dep_a_{trip_id}")
        c1, c2 = st.columns(2)
        with c1:
            dep_t = st.time_input("출발 시간", value=time(7, 55), key=f"dep_t_{trip_id}")
        with c2:
            arr_t = st.time_input("도착 시간", value=time(10, 30), key=f"arr_t_{trip_id}")

        ret_airline = st.selectbox("귀국 항공사", AIRLINES, key=f"ret_a_{trip_id}")
        c3, c4 = st.columns(2)
        with c3:
            ret_dep_t = st.time_input("귀국 출발 시간", value=time(14, 15), key=f"ret_dep_t_{trip_id}")
        with c4:
            ret_arr_t = st.time_input("귀국 도착 시간", value=time(16, 40), key=f"ret_arr_t_{trip_id}")

        price = st.number_input("총합 가격 (원)", min_value=0, step=1000, value=300000, key=f"f_price_{trip_id}")
        is_discount = st.checkbox("🏷️ 특가 / 할인가 적용 항공권인가요?", key=f"f_disc_{trip_id}")

        if st.form_submit_button("➕ 항공권 추가"):
            append_item(trip_name, "flights", {
                "id": new_id(),
                "출국 항공사": dep_airline,
                "출국 시간": f"{dep_t:%H:%M} -> {arr_t:%H:%M}",
                "귀국 항공사": ret_airline,
                "귀국 시간": f"{ret_dep_t:%H:%M} -> {ret_arr_t:%H:%M}",
                "총합 가격(원)": price,
                "할인여부": "할인가" if is_discount else "정가",
                "상태": "후보",
            })
            st.rerun()

    flights = trip["flights"]
    if not flights:
        return
    st.subheader("📋 등록된 항공권 비교 목록")
    cheapest_id = min(flights, key=lambda f: f["총합 가격(원)"])["id"] if len(flights) > 1 else None

    for f in flights:
        price_fmt = f"{int(f['총합 가격(원)']):,}원"
        tag = "🔥 [할인가]" if f.get("할인여부") == "할인가" else "🏷️ [정가]"
        text = f"{tag} {f['출국 항공사']} ({f['출국 시간']}) ↔ {f['귀국 항공사']} ({f['귀국 시간']}) | **{price_fmt}**"

        col_info, col_chk, col_del = st.columns([5, 1.2, 0.6])
        with col_info:
            if f.get("상태") == "구매완료":
                st.success(f"✅ **[구매 완료]** {text}")
            elif f["id"] == cheapest_id:
                st.info(f"💡 **[최저가 추천]** {text}")
            else:
                st.write(f"▫️ [후보] {text}")
        with col_chk:
            key = f"f_status_{f['id']}"
            st.checkbox("구매완료", value=(f.get("상태") == "구매완료"), key=key,
                        on_change=cb_toggle, args=(trip_name, "flights", f["id"], "상태", key, "구매완료", "후보"))
        with col_del:
            st.button("🗑️", key=f"f_del_{f['id']}", on_click=cb_delete, args=(trip_name, "flights", f["id"]))
    reset_button(trip_name, trip_id, "flights", "항공권")


# ==========================================
# 탭: 숙소
# ==========================================
def render_hotels(trip_name: str, trip: dict, trip_id: str):
    with st.form(f"hotel_form_{trip_id}", clear_on_submit=True):
        h_name = st.text_input("숙소 이름")
        h_loc = st.text_input("위치 / 주소 (지도 표시용)")
        h_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=100000)
        is_disc = st.checkbox("🏷️ 특가 / 할인가 적용 숙소인가요?")
        h_link = st.text_input("숙소 링크 (URL)", placeholder="https://www.agoda.com 또는 https://www.airbnb.co.kr")
        h_note = st.text_area("특징 및 메모")
        if st.form_submit_button("➕ 숙소 추가"):
            if not h_name.strip():
                st.error("숙소 이름을 입력해 주세요.")
            else:
                append_item(trip_name, "hotels", {
                    "id": new_id(), "숙소명": h_name.strip(), "위치": h_loc.strip(),
                    "1박 가격(원)": h_price, "할인여부": "할인가" if is_disc else "정가",
                    "링크": normalize_url(h_link), "메모": h_note, "상태": "후보", "show_on_map": False,
                })
                st.rerun()

    hotels = trip["hotels"]
    if not hotels:
        return
    st.subheader("📋 등록된 숙소 목록")
    cheapest_id = min(hotels, key=lambda h: h["1박 가격(원)"])["id"] if len(hotels) > 1 else None

    for h in hotels:
        hid = h["id"]
        price_fmt = f"{int(h['1박 가격(원)']):,}원"
        tag = "🔥 [할인가]" if h.get("할인여부") == "할인가" else "🏷️ [정가]"
        loc = f" ({h['위치']})" if h.get("위치") else ""
        body = f"🏢 **{h['숙소명']}**{loc} | {tag} 1박: {price_fmt}\n\n📝 메모: {h.get('메모', '')}"

        c_text, c_actions = st.columns([3, 3])
        with c_text:
            if h.get("상태") == "예약완료":
                st.success(f"✅ **[예약 완료]** {body}")
            elif hid == cheapest_id:
                st.info(f"💡 **[추천 가성비]** {body}")
            else:
                st.write(body)
        with c_actions:
            a1, a2, a3, a4 = st.columns([1, 1, 1, 0.8])
            with a1:
                key = f"h_status_{hid}"
                st.checkbox("예약완료", value=(h.get("상태") == "예약완료"), key=key,
                            on_change=cb_toggle, args=(trip_name, "hotels", hid, "상태", key, "예약완료", "후보"))
            with a2:
                key = f"h_map_{hid}"
                st.checkbox("지도 표시", value=h.get("show_on_map", False), key=key,
                            on_change=cb_toggle, args=(trip_name, "hotels", hid, "show_on_map", key))
            with a3:
                if h.get("링크"):
                    st.link_button("🔗 이동", normalize_url(h["링크"]))
                else:
                    st.caption("링크없음")
            with a4:
                st.button("🗑️", key=f"h_del_{hid}", on_click=cb_delete, args=(trip_name, "hotels", hid))

        with st.expander("✏️ 정보 수정"):
            with st.form(f"h_edit_form_{hid}"):
                e_name = st.text_input("숙소 이름", value=h.get("숙소명", ""))
                e_loc = st.text_input("위치 / 주소", value=h.get("위치", ""))
                e_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=int(h.get("1박 가격(원)", 0)))
                e_disc = st.checkbox("🏷️ 특가 / 할인가 적용", value=(h.get("할인여부") == "할인가"))
                e_link = st.text_input("숙소 링크 (URL)", value=h.get("링크", ""))
                e_note = st.text_area("특징 및 메모", value=h.get("메모", ""))
                if st.form_submit_button("💾 수정사항 저장"):
                    if not e_name.strip():
                        st.error("숙소 이름은 비워둘 수 없어요.")
                    else:
                        edit_item(trip_name, "hotels", hid, {
                            "숙소명": e_name.strip(), "위치": e_loc.strip(), "1박 가격(원)": e_price,
                            "할인여부": "할인가" if e_disc else "정가",
                            "링크": normalize_url(e_link), "메모": e_note,
                        }, label_fn=hotel_label)
                        st.rerun()
        st.write("---")
    reset_button(trip_name, trip_id, "hotels", "숙소")


# ==========================================
# 탭: 장소 및 일정
# ==========================================
def render_spots(trip_name: str, trip: dict, trip_id: str):
    st.subheader("📍 관광지 및 맛집 등록")
    with st.form(f"spot_form_{trip_id}", clear_on_submit=True):
        s_name = st.text_input("장소 이름 (예: 센소지, 도쿄 타워)")
        s_addr = st.text_input("상세 주소 (지도 검색용)")
        s_cat = st.selectbox("분류", list(CATEGORIES.keys()))
        s_note = st.text_area("추천 이유 및 메모")
        if st.form_submit_button("➕ 장소 추가"):
            if not s_name.strip():
                st.error("장소 이름을 입력해 주세요.")
            else:
                append_item(trip_name, "spots", {
                    "id": new_id(), "장소명": s_name.strip(), "주소": s_addr.strip(),
                    "분류": s_cat, "메모": s_note, "show_on_map": False,
                })
                st.rerun()

    if not trip["spots"]:
        return
    st.subheader("📋 등록된 장소 목록")
    for s in trip["spots"]:
        sid = s["id"]
        addr = f"\n📍 주소: {s['주소']}" if s.get("주소") else ""
        c_info, c_act = st.columns([3.5, 1.5])
        with c_info:
            st.write(f"{CATEGORIES.get(s.get('분류'), '📌')} **[{s.get('분류', '기타')}] {s['장소명']}**{addr}\n\n📝 {s.get('메모', '')}")
        with c_act:
            key = f"spot_map_{sid}"
            st.checkbox("🗺️ 지도 표시", value=s.get("show_on_map", False), key=key,
                        on_change=cb_toggle, args=(trip_name, "spots", sid, "show_on_map", key))
            st.button("🗑️ 삭제", key=f"spot_del_{sid}", on_click=cb_delete, args=(trip_name, "spots", sid))

        with st.expander("✏️ 정보 수정"):
            with st.form(f"spot_edit_form_{sid}"):
                e_name = st.text_input("장소 이름", value=s["장소명"])
                e_addr = st.text_input("상세 주소", value=s.get("주소", ""))
                cats = list(CATEGORIES.keys())
                e_cat = st.selectbox("분류", cats, index=cats.index(s["분류"]) if s.get("분류") in cats else 0)
                e_note = st.text_area("추천 이유 및 메모", value=s.get("메모", ""))
                if st.form_submit_button("💾 수정사항 저장"):
                    if not e_name.strip():
                        st.error("장소 이름은 비워둘 수 없어요.")
                    else:
                        edit_item(trip_name, "spots", sid, {
                            "장소명": e_name.strip(), "주소": e_addr.strip(), "분류": e_cat, "메모": e_note,
                        }, label_fn=spot_label)
                        st.rerun()
        st.write("---")
    reset_button(trip_name, trip_id, "spots", "장소")


def render_schedule(trip_name: str, trip: dict, trip_id: str):
    st.subheader("📅 일자별 일정 작성 및 동선")
    available = [hotel_label(h) for h in trip["hotels"] if h.get("상태") == "예약완료"]
    available += [spot_label(s) for s in trip["spots"]]

    with st.form(f"schedule_form_{trip_id}", clear_on_submit=True):
        sch_date = st.date_input("일정 날짜 선택", value=date.today())
        picked = st.multiselect("📥 저장된 장소 불러오기 (선택한 순서가 방문 순서)", options=available)
        memo = st.text_area("상세 일정 내용 및 메모")
        if st.form_submit_button("➕ 일정 추가"):
            d = sch_date.strftime("%Y-%m-%d")

            def apply(t, _d=d, _picked=list(picked), _memo=memo.strip()):
                entry = next((x for x in t["schedule"] if x["날짜"] == _d), None)
                if entry is None:
                    entry = {"id": new_id(), "날짜": _d, "장소목록": [], "메모": ""}
                    t["schedule"].append(entry)
                    t["schedule"].sort(key=lambda x: x["날짜"])
                for p in _picked:
                    if p not in entry["장소목록"]:
                        entry["장소목록"].append(p)
                if _memo:
                    entry["메모"] = (entry["메모"] + "\n" + _memo).strip()

            mutate(trip_name, apply)
            st.rerun()
    return available


def render_daily_routes(trip_name: str, trip: dict, trip_id: str, available: list):
    if not trip["schedule"]:
        return
    st.markdown("---")
    st.markdown("### 📌 일자별 상세 동선")
    for sch in trip["schedule"]:
        sid = sch["id"]
        st.markdown(f"#### 🗓️ {sch['날짜']}")

        options = list(dict.fromkeys(sch["장소목록"] + available))
        order_key = f"order_{sid}"
        st.multiselect(
            "방문 장소 / 순서 (뺐다가 다시 고르면 맨 뒤로 가요)",
            options=options, default=sch["장소목록"], key=order_key,
            on_change=cb_schedule_field, args=(trip_name, sid, "장소목록", order_key),
        )
        if sch["장소목록"]:
            st.caption(f"🗺️ 이동 동선: {' ➔ '.join(sch['장소목록'])}")

        memo_key = f"memo_{sid}"
        st.text_area("📝 메모", value=sch.get("메모", ""), key=memo_key,
                     on_change=cb_schedule_field, args=(trip_name, sid, "메모", memo_key))
        st.button("🗑️ 이 날짜 일정 삭제", key=f"sch_del_{sid}",
                  on_click=cb_delete, args=(trip_name, "schedule", sid))
        st.write("---")
    reset_button(trip_name, trip_id, "schedule", "일정")


# ==========================================
# 탭: 비용 정산
# ==========================================
def compute_settlement(participants: list, expenses: list):
    paid = {p: 0.0 for p in participants}
    owed = {p: 0.0 for p in participants}
    for e in expenses:
        amount = float(e.get("금액(원)", 0))
        targets = [t for t in (e.get("대상") or participants) if t in owed] or participants
        payer = e.get("결제자")
        if payer in paid:
            paid[payer] += amount
        share = amount / len(targets)
        for t in targets:
            owed[t] += share

    net = {p: paid[p] - owed[p] for p in participants}
    creditors = sorted([[n, v] for n, v in net.items() if v > 1], key=lambda x: -x[1])
    debtors = sorted([[n, -v] for n, v in net.items() if v < -1], key=lambda x: -x[1])
    transfers = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        transfers.append((debtors[i][0], creditors[j][0], amount))
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] < 1:
            i += 1
        if creditors[j][1] < 1:
            j += 1
    return paid, owed, net, transfers


def render_expenses(trip_name: str, trip: dict, trip_id: str):
    st.subheader("💰 비용 정산")
    members = trip["members"]
    expenses = trip["expenses"]

    with st.expander("👥 참여자 설정", expanded=not members):
        with st.form(f"members_form_{trip_id}"):
            raw = st.text_input("참여자 이름 (쉼표로 구분)", value=", ".join(members), placeholder="철수, 영희, 민수")
            if st.form_submit_button("💾 저장"):
                new_members = list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))
                set_field(trip_name, "members", new_members)
                st.rerun()

    participants = list(dict.fromkeys(members + [e["결제자"] for e in expenses if e.get("결제자")]))
    if not participants:
        st.info("먼저 위에서 참여자를 등록해 주세요.")
        return

    with st.form(f"expense_form_{trip_id}", clear_on_submit=True):
        payer = st.selectbox("결제한 사람", participants)
        item = st.text_input("결제 항목")
        amount = st.number_input("금액 (원)", min_value=0, step=1000, value=50000)
        targets = st.multiselect("함께 부담할 사람", participants, default=participants)
        if st.form_submit_button("➕ 지출 내역 추가"):
            if not item.strip():
                st.error("결제 항목을 입력해 주세요.")
            elif not targets:
                st.error("부담할 사람을 한 명 이상 선택해 주세요.")
            else:
                append_item(trip_name, "expenses", {"id": new_id(), "결제자": payer, "항목": item.strip(),
                                                    "금액(원)": amount, "대상": targets})
                st.rerun()

    if not expenses:
        return

    st.markdown("##### 🧾 지출 내역")
    for e in expenses:
        who = ", ".join(e.get("대상") or participants)
        c1, c2 = st.columns([6, 1])
        with c1:
            st.write(f"**{e['항목']}** — {e['결제자']} 결제 | {int(e['금액(원)']):,}원 | 부담: {who}")
        with c2:
            st.button("🗑️", key=f"exp_del_{e['id']}", on_click=cb_delete, args=(trip_name, "expenses", e["id"]))

    total = sum(e["금액(원)"] for e in expenses)
    st.markdown(f"**💵 총 지출 금액: {int(total):,}원**")

    paid, owed, net, transfers = compute_settlement(participants, expenses)
    df = pd.DataFrame({
        "이름": participants,
        "낸 금액(원)": [int(paid[p]) for p in participants],
        "부담 금액(원)": [int(round(owed[p])) for p in participants],
        "정산(원)": [int(round(net[p])) for p in participants],
    })
    st.dataframe(df, hide_index=True)
    st.caption("정산(원): + 는 받을 돈, − 는 보낼 돈")

    if transfers:
        st.success("💡 **정산 방법**\n\n" + "\n".join(f"- {a} → {b}: **{int(round(m)):,}원**" for a, b, m in transfers))
    else:
        st.success("모두 정산이 끝났어요! 🎉")
    reset_button(trip_name, trip_id, "expenses", "지출 내역")


# ==========================================
# 탭: 준비물 / 영상 / 사진
# ==========================================
def render_checklist(trip_name: str, trip: dict, trip_id: str):
    st.subheader("🎒 준비물 체크리스트")
    with st.form(f"chk_form_{trip_id}", clear_on_submit=True):
        name = st.text_input("준비물 이름 (예: 여권)")
        assignee = st.text_input("담당자 (선택)")
        if st.form_submit_button("➕ 추가"):
            if not name.strip():
                st.error("준비물 이름을 입력해 주세요.")
            else:
                label = f"{name.strip()} ({assignee.strip()})" if assignee.strip() else name.strip()
                append_item(trip_name, "checklist", {"id": new_id(), "아이템": label, "체크": False})
                st.rerun()

    for item in trip["checklist"]:
        c1, c2 = st.columns([8, 1])
        with c1:
            key = f"chk_{item['id']}"
            st.checkbox(item.get("아이템", ""), value=item.get("체크", False), key=key,
                        on_change=cb_toggle, args=(trip_name, "checklist", item["id"], "체크", key))
        with c2:
            st.button("🗑️", key=f"chk_del_{item['id']}", on_click=cb_delete, args=(trip_name, "checklist", item["id"]))
    if trip["checklist"]:
        reset_button(trip_name, trip_id, "checklist", "준비물")


def render_videos(trip_name: str, trip: dict, trip_id: str):
    st.subheader("📺 추천 유튜브 영상 모음")
    with st.form(f"video_form_{trip_id}", clear_on_submit=True):
        title = st.text_input("영상 설명")
        url = st.text_input("유튜브 URL 링크")
        if st.form_submit_button("➕ 영상 추가"):
            if not url.strip():
                st.error("URL을 입력해 주세요.")
            else:
                append_item(trip_name, "videos", {"id": new_id(), "설명": title.strip(), "URL": normalize_url(url)})
                st.rerun()

    for v in trip["videos"]:
        st.markdown("---")
        st.write(f"🎬 **{v.get('설명') or v.get('URL', '')}**")
        st.video(v.get("URL", ""))
        st.button("🗑️ 삭제", key=f"v_del_{v['id']}", on_click=cb_delete, args=(trip_name, "videos", v["id"]))
    if trip["videos"]:
        st.markdown("---")
        reset_button(trip_name, trip_id, "videos", "영상")


def render_photos(trip_name: str, trip: dict, trip_id: str):
    st.subheader("📸 추억 사진첩")
    st.caption("여행 중 찍은 소중한 순간들을 사진으로 남겨보세요! (사진은 자동으로 줄여서 저장돼요)")

    with st.form(f"photo_form_{trip_id}", clear_on_submit=True):
        files = st.file_uploader("사진 올리기", accept_multiple_files=True, type=["png", "jpg", "jpeg"])
        if st.form_submit_button("📤 업로드") and files:
            records, failed = [], []
            with st.spinner("사진을 올리는 중..."):
                for f in files:
                    try:
                        content = prepare_image(f)
                        pid = new_id()
                        path = f"{trip_id}/{pid}.jpg"
                        storage_upload(path, content, "image/jpeg")
                        records.append({"id": pid, "path": path, "name": f.name})
                    except Exception as e:
                        failed.append(f"{f.name}: {e}")
            if records:
                mutate(trip_name, lambda t, _r=records: t["photos"].extend(_r))
            if failed:
                st.session_state["_photo_errors"] = failed
            st.rerun()

    for msg in st.session_state.pop("_photo_errors", []):
        st.error(f"업로드 실패 — {msg}")

    photos = trip["photos"]
    cols = st.columns(3)
    for i, p in enumerate(photos):
        with cols[i % 3]:
            url = photo_url(p["path"])
            if url:
                st.image(url, caption=p.get("name", ""), use_container_width=True)
            else:
                st.caption(f"⚠️ {p.get('name', '')} 불러오기 실패")
            st.button("🗑️ 삭제", key=f"photo_del_{p['id']}", on_click=cb_delete, args=(trip_name, "photos", p["id"]))
    if photos:
        reset_button(trip_name, trip_id, "photos", "사진")


# ==========================================
# 메인 화면
# ==========================================
if not selected_travel:
    st.title("🛫 환영합니다! 친구들과 함께 만드는 여행 플래너입니다.")
    st.info("👈 왼쪽 사이드바에서 **새 여행 만들기**를 통해 여행을 시작해 보세요!")
else:
    current_trip = travels[selected_travel]
    trip_id = current_trip["info"]["id"]

    if not current_trip.get("embassy"):
        auto_contacts = get_auto_emergency_contacts(current_trip["info"].get("city") or selected_travel)
        set_field(selected_travel, "embassy", auto_contacts)
        current_trip["embassy"] = auto_contacts

    st.title(f"📍 {current_trip['info']['name']}")
    st.caption(f"📅 여행 일정: {current_trip['info'].get('period', '')}")

    render_dashboard(selected_travel, current_trip, trip_id)

    tab_fh, tab_spot, tab_exp, tab_chk, tab_video, tab_photo = st.tabs([
        "✈️ 항공권 & 숙소", "📍 장소 및 일정", "💰 비용 정산", "🎒 준비물", "📺 유튜브 영상", "📸 추억 사진첩",
    ])

    with tab_fh:
        sub_f, sub_h = st.tabs(["✈️ 항공권 비교", "🏢 숙소 후보"])
        with sub_f:
            render_flights(selected_travel, current_trip, trip_id)
        with sub_h:
            render_hotels(selected_travel, current_trip, trip_id)

    with tab_spot:
        col_l, col_r = st.columns([1.1, 0.9])
        with col_l:
            render_spots(selected_travel, current_trip, trip_id)
        with col_r:
            available_places = render_schedule(selected_travel, current_trip, trip_id)
        render_daily_routes(selected_travel, current_trip, trip_id, available_places)

    with tab_exp:
        render_expenses(selected_travel, current_trip, trip_id)
    with tab_chk:
        render_checklist(selected_travel, current_trip, trip_id)
    with tab_video:
        render_videos(selected_travel, current_trip, trip_id)
    with tab_photo:
        render_photos(selected_travel, current_trip, trip_id)
