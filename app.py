import streamlit as st
import pandas as pd
import json
import os
import requests
import yfinance as yf
from datetime import date

# --- 데이터 저장 파일 (JSON) ---
DB_FILE = "travel_data.json"

@st.cache_data
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 기존 데이터와 새 키 호환성 자동 보정
            for trip in data.values():
                for h in trip.get("hotels", []):
                    if "가격" not in h and "1박 가격(원)" in h:
                        h["가격"] = h["1박 가격(원)"]
                    h.setdefault("가격", 100000)
                for f_item in trip.get("flights", []):
                    if "가격" not in f_item and "총합 가격(원)" in f_item:
                        f_item["가격"] = f_item["총합 가격(원)"]
                    f_item.setdefault("가격", 300000)
                for s_item in trip.get("spots", []):
                    if "이름" not in s_item and "장소명" in s_item:
                        s_item["이름"] = s_item["장소명"]
                    s_item.setdefault("이름", "장소")
            return data
    return {}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 카테고리 이모지 정의 ---
CATEGORY_EMOJIS = {"놀거리/관광지": "🎡", "맛집/카페": "🍴", "쇼핑": "🛍️", "기타": "📌"}

# --- 긴급 연락처 데이터베이스 ---
def get_auto_emergency_contacts(loc):
    loc = loc.lower()
    if any(k in loc for k in ["tokyo", "osaka", "fukuoka", "japan", "도쿄", "오사카", "후쿠오카", "일본"]):
        return "• 경찰: 110 / 소방·구급: 119\n• 주일 한국대사관: +81-3-3452-7401\n• 영사콜센터: +82-2-3210-0404"
    elif any(k in loc for k in ["new york", "la", "usa", "guam", "미국", "괌"]):
        return "• 긴급 통합 신고(경찰/구급): 911\n• 주미 한국대사관: +1-202-939-5600\n• 영사콜센터: +82-2-3210-0404"
    elif any(k in loc for k in ["paris", "london", "rome", "europe", "프랑스", "영국", "이탈리아", "유럽"]):
        return "• 유럽 통합 긴급신고: 112\n• 영사콜센터: +82-2-3210-0404"
    elif any(k in loc for k in ["danang", "hanoi", "vietnam", "다낭", "하노이", "베트남"]):
        return "• 경찰: 113 / 구급: 115\n• 주베트남 한국대사관: +84-24-3831-5111\n• 영사콜센터: +82-2-3210-0404"
    return "• 현지 긴급번호 확인 필요\n• 외교부 영사콜센터: +82-2-3210-0404"

# --- 캐시 적용 환율 및 날씨 ---
@st.cache_data(ttl=3600)
def get_exchange_rates():
    tickers = {"엔화 (100JPY)": "JPYKRW=X", "달러 (USD)": "USDKRW=X"}
    rates = {}
    for name, symbol in tickers.items():
        try:
            data = yf.Ticker(symbol).history(period="1d")
            if not data.empty:
                val = data['Close'].iloc[-1]
                if "100" in name: val *= 100
                rates[name] = round(val, 2)
        except:
            rates[name] = "조회 불가"
    return rates

@st.cache_data(ttl=1800)
def get_weather(city_name):
    try:
        res = requests.get(f"https://wttr.in/{city_name}?format=%C+%t", timeout=2)
        if res.status_code == 200:
            return res.text.strip()
    except:
        pass
    return "날씨 정보 조회 불가"

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="스마트 여행 플래너 ✈️", layout="wide")
travels = load_data()

# ==========================================
# 사이드바: 여행 선택 및 관리
# ==========================================
st.sidebar.title("🌍 여행 선택 및 관리")
travel_names = list(travels.keys())
selected_travel = None

mode = st.sidebar.radio("모드 선택", ["📂 기존 여행 선택하기", "➕ 새 여행 만들기"])

if mode == "➕ 새 여행 만들기":
    with st.sidebar.form("new_travel_form"):
        new_name = st.text_input("여행 이름 (예: 도쿄 여행)")
        new_city = st.text_input("영문 도시명 (예: Tokyo)")
        new_date = st.text_input("여행 기간 (예: 2026.07.10 ~ 07.15)")
        if st.form_submit_button("생성") and new_name:
            if new_name in travels:
                st.sidebar.error("이미 존재하는 이름입니다.")
            else:
                target_loc = new_city or new_name
                travels[new_name] = {
                    "info": {"name": new_name, "city": target_loc, "period": new_date},
                    "embassy": get_auto_emergency_contacts(target_loc),
                    "flights": [], "hotels": [], "spots": [], "videos": [],
                    "expenses": [], "checklist": [], "schedule": []
                }
                save_data(travels)
                st.sidebar.success("생성 완료!")
                st.rerun()
else:
    if travel_names:
        selected_travel = st.sidebar.selectbox("여행 선택", travel_names)
    else:
        st.sidebar.warning("등록된 여행이 없습니다.")

# ==========================================
# 메인 화면
# ==========================================
if not selected_travel:
    st.title("🛫 스마트 여행 플래너에 오신 것을 환영합니다!")
    st.info("👈 왼쪽 사이드바에서 여행을 만들거나 선택해 주세요.")
else:
    trip = travels[selected_travel]
    for key in ["flights", "hotels", "spots", "videos", "expenses", "checklist", "schedule"]:
        trip.setdefault(key, [])

    st.title(f"📍 {trip['info']['name']}")
    st.caption(f"📅 일정: {trip['info']['period']}")
    
    # 상시 대시보드
    st.markdown("---")
    city_q = trip['info'].get('city', 'Seoul')
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(label=f"🌤️ {city_q} 날씨", value=get_weather(city_q))
    with c2:
        st.write("🔱 **환율 정보**")
        for k, v in get_exchange_rates().items():
            st.caption(f"• {k}: {v}원")
    with c3:
        st.write("🚨 **긴급 연락처**")
        embassy_text = trip.get("embassy", "")
        st.text(embassy_text.split('\n')[0])
        with st.popover("✏️ 수정"):
            with st.form("emb_form"):
                new_emb = st.text_area("연락처", value=embassy_text)
                if st.form_submit_button("저장"):
                    trip["embassy"] = new_emb
                    save_data(travels)
                    st.success("저장됨")
                    st.rerun()
    st.markdown("---")

    # 탭 메뉴 분리
    tab_f, tab_s, tab_e, tab_c, tab_v, tab_p = st.tabs([
        "✈️ 항공권 & 숙소", "📍 장소 및 일정", "💰 비용", "🎒 준비물", "📺 영상", "📸 사진첩"
    ])

    # 1. 항공권 & 숙소
    with tab_f:
        sub_f, sub_h = st.tabs(["✈️ 항공권", "🏢 숙소"])
        with sub_f:
            with st.form("f_form"):
                dep = st.selectbox("출국 항공사", ["제주항공", "에어부산", "에어서울", "기타"])
                ret = st.selectbox("귀국 항공사", ["제주항공", "에어부산", "에어서울", "기타"])
                price = st.number_input("가격 (원)", min_value=0, step=1000, value=300000)
                if st.form_submit_button("추가"):
                    trip["flights"].append({"출국": dep, "귀국": ret, "가격": price, "상태": "후보"})
                    save_data(travels)
                    st.rerun()
            
            if trip["flights"]:
                for idx, f in enumerate(trip["flights"]):
                    cols = st.columns([4, 1])
                    with cols[0]:
                        f_price = f.get('가격', f.get('총합 가격(원)', 0))
                        st.write(f"▫️ {f['출국']} ↔ {f['귀국']} | {f_price:,}원 ({f.get('상태', '후보')})")
                    with cols[1]:
                        if st.button("삭제", key=f"del_f_{idx}"):
                            trip["flights"].pop(idx)
                            save_data(travels)
                            st.rerun()
                if st.button("항공권 초기화"):
                    trip["flights"] = []
                    save_data(travels)
                    st.rerun()

        with sub_h:
            with st.form("h_form"):
                h_name = st.text_input("숙소 이름")
                h_loc = st.text_input("위치")
                h_price = st.number_input("1박 가격", min_value=0, step=5000, value=100000)
                if st.form_submit_button("추가"):
                    trip["hotels"].append({"숙소명": h_name, "위치": h_loc, "가격": h_price, "상태": "후보"})
                    save_data(travels)
                    st.rerun()

            if trip["hotels"]:
                for idx, h in enumerate(trip["hotels"]):
                    cols = st.columns([4, 1])
                    with cols[0]:
                        h_price = h.get('가격', h.get('1박 가격(원)', 0))
                        st.write(f"🏢 {h['숙소명']} ({h['위치']}) - {h_price:,}원")
                    with cols[1]:
                        if st.button("삭제", key=f"del_h_{idx}"):
                            trip["hotels"].pop(idx)
                            save_data(travels)
                            st.rerun()
                if st.button("숙소 초기화"):
                    trip["hotels"] = []
                    save_data(travels)
                    st.rerun()

    # 2. 장소 및 일정
    with tab_s:
        c_l, c_r = st.columns(2)
        with c_l:
            with st.form("spot_form"):
                s_name = st.text_input("장소 이름")
                s_cat = st.selectbox("분류", list(CATEGORY_EMOJIS.keys()))
                if st.form_submit_button("장소 추가") and s_name:
                    trip["spots"].append({"이름": s_name, "분류": s_cat})
                    save_data(travels)
                    st.rerun()
            
            if trip["spots"]:
                for idx, s in enumerate(trip["spots"]):
                    emoji = CATEGORY_EMOJIS.get(s['분류'], "📌")
                    s_name = s.get('이름', s.get('장소명', ''))
                    cols = st.columns([4, 1])
                    cols[0].write(f"{emoji} [{s['분류']}] {s_name}")
                    if cols[1].button("삭제", key=f"del_s_{idx}"):
                        trip["spots"].pop(idx)
                        save_data(travels)
                        st.rerun()

        with c_r:
            with st.form("sch_form"):
                sch_date = st.date_input("날짜", value=date.today())
                sch_text = st.text_input("일정 내용")
                if st.form_submit_button("일정 추가") and sch_text:
                    trip["schedule"].append({"날짜": sch_date.strftime("%Y-%m-%d"), "내용": sch_text})
                    save_data(travels)
                    st.rerun()

            if trip["schedule"]:
                for idx, sc in enumerate(trip["schedule"]):
                    cols = st.columns([4, 1])
                    cols[0].write(f"🗓️ **{sc['날짜']}**: {sc['내용']}")
                    if cols[1].button("삭제", key=f"del_sc_{idx}"):
                        trip["schedule"].pop(idx)
                        save_data(travels)
                        st.rerun()

    # 3. 비용 정산
    with tab_e:
        with st.form("exp_form"):
            payer = st.text_input("결제자")
            item = st.text_input("항목")
            amount = st.number_input("금액", min_value=0, step=1000)
            if st.form_submit_button("지출 추가") and item:
                trip["expenses"].append({"결제자": payer, "항목": item, "금액": amount})
                save_data(travels)
                st.rerun()

        if trip["expenses"]:
            df_e = pd.DataFrame(trip["expenses"])
            st.dataframe(df_e, use_container_width=True)
            total = df_e["금액"].sum()
            st.markdown(f"**💵 총 지출: {total:,}원**")
            if st.button("지출 초기화"):
                trip["expenses"] = []
                save_data(travels)
                st.rerun()

    # 4. 준비물
    with tab_c:
        with st.form("chk_form"):
            c_item = st.text_input("준비물 입력")
            if st.form_submit_button("추가") and c_item:
                trip["checklist"].append({"아이템": c_item, "체크": False})
                save_data(travels)
                st.rerun()

        if trip["checklist"]:
            for idx, c in enumerate(trip["checklist"]):
                checked = st.checkbox(c["아이템"], value=c["체크"], key=f"chk_{idx}")
                if checked != c["체크"]:
                    trip["checklist"][idx]["체크"] = checked
                    save_data(travels)
                    st.rerun()

    # 5. 유튜브 영상
    with tab_video:
        with st.form("v_form"):
            v_title = st.text_input("영상 제목")
            v_url = st.text_input("유튜브 링크")
            if st.form_submit_button("영상 추가") and v_url:
                trip["videos"].append({"제목": v_title, "URL": v_url})
                save_data(travels)
                st.rerun()

        if trip["videos"]:
            for idx, v in enumerate(trip["videos"]):
                st.write(f"🎬 **{v['제목']}**")
                try: st.video(v["URL"])
                except: pass
                if st.button("삭제", key=f"del_v_{idx}"):
                    trip["videos"].pop(idx)
                    save_data(travels)
                    st.rerun()

    # 6. 추억 사진첩
    with tab_photo:
        st.subheader("📸 추억 사진첩")
        files = st.file_uploader("사진 업로드", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
        if files:
            for f in files:
                st.image(f, caption=f.name, use_column_width=True)
                st.markdown("---")
