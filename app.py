import streamlit as st
import pandas as pd
import json
import os
import requests
import yfinance as yf

# --- 데이터 저장 파일 (JSON) ---
DB_FILE = "travel_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 실시간 환율 및 날씨 함수 ---
@st.cache_data(ttl=3600)
def get_exchange_rates():
    tickers = {"엔화 (100JPY/KRW)": "JPYKRW=X", "달러 (USD/KRW)": "USDKRW=X", "유로 (EUR/KRW)": "EURKRW=X", "베트남 동 (100VND/KRW)": "VNDKRW=X"}
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

def get_weather(city_name):
    try:
        url = f"https://wttr.in/{city_name}?format=%C+%t"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return res.text.strip()
    except:
        pass
    return "날씨 정보 조회 불가"

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="우리의 스마트 여행 플래너 ✈️", layout="wide")
travels = load_data()

# ==========================================
# 사이드바: 여행 선택 및 새 여행 만들기
# ==========================================
st.sidebar.title("🌍 여행 선택 및 관리")
travel_names = list(travels.keys())
selected_travel = None

mode = st.sidebar.radio("모드 선택", ["📂 기존 여행 선택하기", "➕ 새 여행 만들기"])

if mode == "➕ 새 여행 만들기":
    with st.sidebar.form("new_travel_form"):
        new_name = st.text_input("여행 이름 (예: 도쿄 여행, 뉴욕 여행)")
        new_city = st.text_input("영문 도시명 (날씨용, 예: Tokyo, New York, Osaka)")
        new_date = st.text_input("여행 기간 (예: 2026.07.10 ~ 07.15)")
        create_btn = st.form_submit_button("여행 폴더 생성")
        
        if create_btn and new_name:
            if new_name in travels:
                st.sidebar.error("이미 존재하는 여행 이름입니다.")
            else:
                travels[new_name] = {
                    "info": {"name": new_name, "city": new_city if new_city else new_name, "period": new_date},
                    "flights": [], "hotels": [], "spots": [], "videos": [],
                    "expenses": [], "photos": [], "schedule": [], "checklist": []
                }
                save_data(travels)
                st.sidebar.success(f"'{new_name}' 생성 완료!")
                st.rerun()
else:
    if travel_names:
        selected_travel = st.sidebar.selectbox("여행을 선택하세요", travel_names)
    else:
        st.sidebar.warning("등록된 여행이 없습니다. 새 여행을 먼저 만들어주세요!")

# ==========================================
# 메인 화면
# ==========================================
if not selected_travel:
    st.title("🛫 환영합니다! 친구들과 함께 만드는 여행 플래너입니다.")
    st.info("👈 왼쪽 사이드바에서 **'새 여행 만들기'**를 통해 여행을 시작해 보세요!")
else:
    current_trip = travels[selected_travel]
    
    st.title(f"📍 {current_trip['info']['name']}")
    st.caption(f"📅 여행 일정: {current_trip['info']['period']}")
    
    # --- 실시간 대시보드 (날씨 & 환율) ---
    col_w, col_e = st.columns(2)
    with col_w:
        city_query = current_trip['info'].get('city', 'Seoul')
        weather_info = get_weather(city_query)
        st.metric(label=f"🌤️ {city_query} 실시간 날씨", value=weather_info)
    
    with col_e:
        rates = get_exchange_rates()
        rate_str = " | ".join([f"{k}: {v}원" for k, v in rates.items()])
        st.write("🔱 **실시간 주요 환율**")
        st.info(rate_str)
        
    st.markdown("---")

    # ------------------------------------------
    # 1. 상단 아코디언 버튼 영역 (접고 펼치기)
    # ------------------------------------------
    
    # [1] 항공권 비교 & 구매 완료 표시
    with st.expander("✈️ 항공권 비교 (구매 확정 표시 기능 포함)"):
        with st.form("flight_form"):
            st.subheader("한국 출국편 & 현지 귀국편 입력")
            dep_airline = st.selectbox("출국 항공사", ["제주항공", "에어부산", "에어서울", "이스타항공", "기타"], key="dep_a")
            c1, c2 = st.columns(2)
            with c1: dep_t = st.time_input("출발 시간", value=pd.to_datetime("07:55").time())
            with c2: arr_t = st.time_input("도착 시간", value=pd.to_datetime("10:30").time())
            
            ret_airline = st.selectbox("귀국 항공사", ["제주항공", "에어부산", "에어서울", "이스타항공", "기타"], key="ret_a")
            c3, c4 = st.columns(2)
            with c3: ret_dep_t = st.time_input("귀국 출발 시간", value=pd.to_datetime("14:15").time())
            with c4: ret_arr_t = st.time_input("귀국 도착 시간", value=pd.to_datetime("16:40").time())
            
            price = st.number_input("총합 가격 (원)", min_value=0, step=1000, value=300000)
            is_booked = st.checkbox("✅ 이 항공권을 실제 구매 완료했나요?")

            if st.form_submit_button("➕ 항공권 추가"):
                current_trip["flights"].append({
                    "출국 항공사": dep_airline,
                    "출국 시간": f"{dep_t.strftime('%H:%M')} -> {arr_t.strftime('%H:%M')}",
                    "귀국 항공사": ret_airline,
                    "귀국 시간": f"{ret_dep_t.strftime('%H:%M')} -> {ret_arr_t.strftime('%H:%M')}",
                    "총합 가격(원)": price,
                    "구매여부": "구매완료" if is_booked else "후보"
                })
                save_data(travels)
                st.success("추가되었습니다!")
                st.rerun()

        if current_trip["flights"]:
            st.subheader("📋 항공권 목록")
            for idx, flight in enumerate(current_trip["flights"]):
                price_formatted = f"{int(flight['총합 가격(원)']):,}원"
                
                # 구매 완료 항목은 초록색 카드 강조
                if flight.get("구매여부") == "구매완료":
                    st.success(
                        f"✅ **[구매 확정 항공권]** {flight['출국 항공사']} ({flight['출국 시간']}) ↔ {flight['귀국 항공사']} ({flight['귀국 시간']}) | **{price_formatted}**"
                    )
                else:
                    st.info(
                        f"🔹 **[후보]** {flight['출국 항공사']} ({flight['출국 시간']}) ↔ {flight['귀국 항공사']} ({flight['귀국 시간']}) | **{price_formatted}**"
                    )
                
                # 구매 여부 상태 변경 체크박스
                col_status, col_blank = st.columns([1, 4])
                with col_status:
                    is_now_booked = st.checkbox("구매 완료 상태 지정", value=(flight.get("구매여부") == "구매완료"), key=f"f_booked_{idx}")
                    new_status = "구매완료" if is_now_booked else "후보"
                    if new_status != flight.get("구매여부"):
                        current_trip["flights"][idx]["구매여부"] = new_status
                        save_data(travels)
                        st.rerun()

            if st.button("🗑️ 항공권 전체 초기화"):
                current_trip["flights"] = []
                save_data(travels)
                st.rerun()

    # [2] 숙소 후보 & 예약 완료 표시
    with st.expander("🏨 숙소 후보 (예약 확정 표시 기능 포함)"):
        with st.form("hotel_form"):
            h_name = st.text_input("숙소 이름")
            h_loc = st.text_input("위치 / 지역")
            h_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=100000)
            h_note = st.text_area("특징 및 메모")
            h_booked = st.checkbox("✅ 이 숙소를 실제로 예약 완료했나요?")
            
            if st.form_submit_button("➕ 숙소 추가"):
                current_trip["hotels"].append({
                    "숙소명": h_name,
                    "위치": h_loc,
                    "1박 가격(원)": h_price,
                    "메모": h_note,
                    "예약여부": "예약완료" if h_booked else "후보"
                })
                save_data(travels)
                st.success("추가되었습니다!")
                st.rerun()
                
        if current_trip["hotels"]:
            st.subheader("📋 숙소 목록")
            for idx, hotel in enumerate(current_trip["hotels"]):
                h_price_fmt = f"{int(hotel['1박 가격(원)']):,}원"
                
                # 예약 완료 항목은 초록색 카드 강조
                if hotel.get("예약여부") == "예약완료":
                    st.success(
                        f"✅ **[예약 확정 숙소]** {hotel['숙소명']} ({hotel['위치']}) | 1박: {h_price_fmt}\n\n📝 메모: {hotel['메모']}"
                    )
                else:
                    st.info(
                        f"🔹 **[후보]** {hotel['숙소명']} ({hotel['위치']}) | 1박: {h_price_fmt}\n\n📝 메모: {hotel['메모']}"
                    )
                    
                col_h_status, _ = st.columns([1, 4])
                with col_h_status:
                    is_h_booked = st.checkbox("예약 완료 상태 지정", value=(hotel.get("예약여부") == "예약완료"), key=f"h_booked_{idx}")
                    new_h_status = "예약완료" if is_h_booked else "후보"
                    if new_h_status != hotel.get("예약여부"):
                        current_trip["hotels"][idx]["예약여부"] = new_h_status
                        save_data(travels)
                        st.rerun()

            if st.button("🗑️ 숙소 전체 초기화"):
                current_trip["hotels"] = []
                save_data(travels)
                st.rerun()

    # [3] 여행지 & 맛집
    with st.expander("📍 여행지 및 맛집 (클릭해서 열기/닫기)"):
        with st.form("spot_form"):
            s_name = st.text_input("장소 이름")
            s_cat = st.selectbox("분류", ["관광지", "맛집/카페", "쇼핑", "기타"])
            s_note = st.text_area("추천 이유 및 메모")
            if st.form_submit_button("➕ 장소 추가"):
                current_trip["spots"].append({"장소명": s_name, "분류": s_cat, "메모": s_note})
                save_data(travels)
                st.success("추가되었습니다!")
                st.rerun()
        if current_trip["spots"]:
            st.dataframe(pd.DataFrame(current_trip["spots"]), use_container_width=True)
            if st.button("🗑️ 여행지 전체 초기화"):
                current_trip["spots"] = []
                save_data(travels)
                st.rerun()

    # [4] 💰 비용 정산 (1/N 내역)
    with st.expander("💰 비용 정산 및 지출 내역 (클릭해서 열기/닫기)"):
        with st.form("expense_form"):
            exp_payer = st.text_input("결제한 사람 (예: 민지)")
            exp_item = st.text_input("결제 항목 (예: 1일차 저녁 식사)")
            exp_amount = st.number_input("금액 (원)", min_value=0, step=1000, value=50000)
            if st.form_submit_button("➕ 지출 내역 추가"):
                current_trip.setdefault("expenses", []).append({"결제자": exp_payer, "항목": exp_item, "금액(원)": exp_amount})
                save_data(travels)
                st.success("추가되었습니다!")
                st.rerun()
        
        if current_trip.get("expenses"):
            df_e = pd.DataFrame(current_trip["expenses"])
            st.dataframe(df_e, use_container_width=True)
            total_exp = df_e["금액(원)"].sum()
            
            st.markdown(f"**💵 총 지출 금액: {total_exp:,}원**")
            num_people = st.number_input("함께한 총 인원수 (1/N 계산용)", min_value=1, value=2)
            per_person = int(total_exp / num_people)
            st.success(f"💡 **1인당 정산 금액**: **{per_person:,}원**")
            
            if st.button("🗑️ 지출 내역 전체 초기화"):
                current_trip["expenses"] = []
                save_data(travels)
                st.rerun()

    # [5] 📺 추천 영상
    with st.expander("📺 추천 영상 (클릭해서 열기/닫기)"):
        with st.form("video_form"):
            v_title = st.text_input("영상 설명")
            v_url = st.text_input("유튜브 URL 링크")
            if st.form_submit_button("➕ 영상 추가"):
                current_trip["videos"].append({"설명": v_title, "URL": v_url})
                save_data(travels)
                st.success
