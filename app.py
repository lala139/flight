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
    tickers = {
        "엔화 (100JPY/KRW)": "JPYKRW=X",
        "달러 (USD/KRW)": "USDKRW=X",
        "유로 (EUR/KRW)": "EURKRW=X",
        "베트남 동 (100VND/KRW)": "VNDKRW=X"
    }
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
    
    # 누락된 기본 리스트 키(Key) 복구 보장
    for key in ["flights", "hotels", "spots", "videos", "expenses", "photos", "schedule", "checklist"]:
        current_trip.setdefault(key, [])

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
    
    # [1] 항공권 비교
    with st.expander("✈️ 항공권 비교"):
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
            is_booked = st.checkbox("✅ 실제 구매 완료한 항공권")

            if st.form_submit_button("➕ 항공권 추가"):
                current_trip["flights"].append({
                    "출국 항공사": dep_airline,
                    "출국 시간": f"{dep_t.strftime('%H:%M')} -> {arr_t.strftime('%H:%M')}",
                    "귀국 항공사": ret_airline,
                    "귀국 시간": f"{ret_dep_t.strftime('%H:%M')} -> {ret_arr_t.strftime('%H:%M')}",
                    "총합 가격(원)": price,
                    "상태": "구매완료" if is_booked else "후보"
                })
                save_data(travels)
                st.success("항공권이 추가되었습니다!")
                st.rerun()

        if current_trip["flights"]:
            df_f = pd.DataFrame(current_trip["flights"])
            
            # 구매 확정건 별도 표시
            booked_flights = [f for f in current_trip["flights"] if f.get("상태") == "구매완료"]
            if booked_flights:
                for bf in booked_flights:
                    st.success(f"✅ **[구매 확정]** {bf['출국 항공사']} ({bf['출국 시간']}) ↔ {bf['귀국 항공사']} ({bf['귀국 시간']}) | **{int(bf['총합 가격(원)']):,}원**")

            # 전체 비교 표 (가격 오름차순 정렬)
            df_f_sorted = df_f.sort_values(by="총합 가격(원)", ascending=True).reset_index(drop=True)
            df_f_disp = df_f_sorted.copy()
            df_f_disp["총합 가격(원)"] = df_f_disp["총합 가격(원)"].apply(lambda x: f"{int(x):,}원")
            
            st.subheader("📊 등록된 항공권 비교 목록 (최저가 순)")
            st.dataframe(df_f_disp, use_container_width=True)
            
            # 최저가 추천
            cheapest = df_f_sorted.iloc[0]
            st.info(f"💡 **최저가 추천**: {cheapest['출국 항공사']} / {cheapest['귀국 항공사']} 👉 **{int(cheapest['총합 가격(원)']):,}원**")
            
            if st.button("🗑️ 항공권 전체 초기화"):
                current_trip["flights"] = []
                save_data(travels)
                st.rerun()

    # [2] 숙소 후보
    with st.expander("🏨 숙소 후보"):
        with st.form("hotel_form"):
            h_name = st.text_input("숙소 이름")
            h_loc = st.text_input("위치 / 지역")
            h_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=100000)
            h_note = st.text_area("특징 및 메모")
            h_booked = st.checkbox("✅ 실제 예약 완료한 숙소")
            
            if st.form_submit_button("➕ 숙소 추가"):
                current_trip["hotels"].append({
                    "숙소명": h_name,
                    "위치": h_loc,
                    "1박 가격(원)": h_price,
                    "메모": h_note,
                    "상태": "예약완료" if h_booked else "후보"
                })
                save_data(travels)
                st.success("숙소가 추가되었습니다!")
                st.rerun()
                
        if current_trip["hotels"]:
            booked_hotels = [h for h in current_trip["hotels"] if h.get("상태") == "예약완료"]
            if booked_hotels:
                for bh in booked_hotels:
                    st.success(f"✅ **[예약 확정]** {bh['숙소명']} ({bh['위치']}) | 1박: {int(bh['1박 가격(원)']):,}원 | 메모: {bh['메모']}")

            df_h = pd.DataFrame(current_trip["hotels"])
            st.subheader("📊 숙소 후보 목록")
            st.dataframe(df_h, use_container_width=True)

            if st.button("🗑️ 숙소 전체 초기화"):
                current_trip["hotels"] = []
                save_data(travels)
                st.rerun()

    # [3] 여행지 & 맛집
    with st.expander("📍 여행지 및 맛집"):
        with st.form("spot_form"):
            s_name = st.text_input("장소 이름")
            s_cat = st.selectbox("분류", ["관광지", "맛집/카페", "쇼핑", "기타"])
            s_note = st.text_area("추천 이유 및 메모")
            if st.form_submit_button("➕ 장소 추가"):
                current_trip["spots"].append({"장소명": s_name, "분류": s_cat, "메모": s_note})
                save_data(travels)
                st.success("장소가 추가되었습니다!")
                st.rerun()
        if current_trip["spots"]:
            st.dataframe(pd.DataFrame(current_trip["spots"]), use_container_width=True)
            if st.button("🗑️ 여행지 전체 초기화"):
                current_trip["spots"] = []
                save_data(travels)
                st.rerun()

    # [4] 💰 비용 정산
    with st.expander("💰 비용 정산"):
        with st.form("expense_form"):
            exp_payer = st.text_input("결제한 사람")
            exp_item = st.text_input("결제 항목")
            exp_amount = st.number_input("금액 (원)", min_value=0, step=1000, value=50000)
            if st.form_submit_button("➕ 지출 내역 추가"):
                current_trip["expenses"].append({"결제자": exp_payer, "항목": exp_item, "금액(원)": exp_amount})
                save_data(travels)
                st.success("내역이 추가되었습니다!")
                st.rerun()
        
        if current_trip["expenses"]:
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
    with st.expander("📺 추천 영상"):
        with st.form("video_form"):
            v_title = st.text_input("영상 설명")
            v_url = st.text_input("유튜브 URL 링크")
            if st.form_submit_button("➕ 영상 추가"):
                current_trip["videos"].append({"설명": v_title, "URL": v_url})
                save_data(travels)
                st.success("영상이 추가되었습니다!")
                st.rerun()
        if current_trip["videos"]:
            for v in current_trip["videos"]:
                st.subheader(f"🎬 {v['설명']}")
                try: st.video(v["URL"])
                except: st.warning("영상을 불러올 수 없습니다.")
            if st.button("🗑️ 영상 전체 초기화"):
                current_trip["videos"] = []
                save_data(travels)
                st.rerun()

    # [6] 📸 추억 사진첩
    with st.expander("📸 추억 사진첩"):
        uploaded_files = st.file_uploader("사진 올리기 (PNG, JPG)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
        if uploaded_files:
            cols = st.columns(3)
            for idx, file in enumerate(uploaded_files):
                with cols[idx % 3]:
                    st.image(file, use_column_width=True)

    # ------------------------------------------
    # 2. 하단 상시 고정 영역 (일자별 일정 & 준비물)
    # ------------------------------------------
    st.write("---")
    st.header("📌 기본 일정 및 준비물")

    col_left, col_right = st.columns(2)

    # 일자별 일정
    with col_left:
        st.subheader("📅 일자별 일정")
        with st.form("schedule_form"):
            sch_day = st.text_input("일자 (예: 1일차, 7월 10일)")
            sch_content = st.text_area("상세 일정 내용")
            if st.form_submit_button("➕ 일정 추가"):
                current_trip["schedule"].append({"일자": sch_day, "내용": sch_content})
                save_data(travels)
                st.success("일정이 추가되었습니다!")
                st.rerun()
        
        if current_trip["schedule"]:
            for sch in current_trip["schedule"]:
                st.markdown(f"**📌 [{sch['일자']}]**\n{sch['내용']}")
                st.write("---")
            if st.button("🗑️ 일정 전체 초기화"):
                current_trip["schedule"] = []
                save_data(travels)
                st.rerun()

    # 준비물 체크리스트
    with col_right:
        st.subheader("🎒 준비물 체크리스트")
        with st.form("chk_form"):
            chk_item = st.text_input("준비물 이름 (예: 여권, 보조배터리)")
            if st.form_submit_button("➕ 준비물 추가"):
                current_trip["checklist"].append({"아이템": chk_item, "체크": False})
                save_data(travels)
                st.rerun()
        
        if current_trip["checklist"]:
            for i, item in enumerate(current_trip["checklist"]):
                checked = st.checkbox(item["아이템"], value=item["체크"], key=f"chk_{selected_travel}_{i}")
                if checked != item["체크"]:
                    current_trip["checklist"][i]["체크"] = checked
                    save_data(travels)
            if st.button("🗑️ 준비물 전체 초기화"):
                current_trip["checklist"] = []
                save_data(travels)
                st.rerun()
