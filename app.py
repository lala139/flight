import streamlit as st
import pandas as pd
import json
import os
import requests
import yfinance as yf
import urllib.parse
import streamlit.components.v1 as components
from datetime import date

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
    
    # 누락된 데이터 구조 자동 보정
    for key in ["flights", "hotels", "spots", "videos", "expenses", "photos", "schedule", "checklist"]:
        current_trip.setdefault(key, [])

    st.title(f"📍 {current_trip['info']['name']}")
    st.caption(f"📅 여행 일정: {current_trip['info']['period']}")
    
    # ------------------------------------------
    # 상단 메인 지도 표시용 검색 쿼리 수집
    # ------------------------------------------
    map_queries = []
    
    # 1. 숙소 지도 수집 (예약 완료가 하나라도 있으면 그 숙소만, 없으면 후보지 전체)
    booked_hotels = [h for h in current_trip["hotels"] if h.get("상태") == "예약완료"]
    if booked_hotels:
        for bh in booked_hotels:
            q = bh.get("위치") or bh.get("숙소명")
            if q: map_queries.append(f"🏢 {bh['숙소명']} ({q})")
    else:
        for h in current_trip["hotels"]:
            q = h.get("위치") or h.get("숙소명")
            if q: map_queries.append(f"🏢 {h['숙소명']} ({q})")

    # 2. 장소/맛집 중 '지도에 표시' 체크된 항목 수집
    category_emojis = {"놀거리/관광지": "🎡", "맛집/카페": "🍴", "쇼핑": "🛍️", "기타": "📌"}
    for spot in current_trip["spots"]:
        if spot.get("show_on_map", False):
            cat_emoji = category_emojis.get(spot.get("분류"), "📌")
            q = spot.get("장소명")
            if q: map_queries.append(f"{cat_emoji} {q}")

    # --- 대시보드: 좌측(날씨, 환율, 현지 긴급 연락처), 우측(정사각형 구글 지도) ---
    col_dash_left, col_dash_right = st.columns([1, 1])
    
    with col_dash_left:
        city_query = current_trip['info'].get('city', 'Seoul')
        weather_info = get_weather(city_query)
        st.metric(label=f"🌤️ {city_query} 실시간 날씨", value=weather_info)
        
        st.markdown("---")
        rates = get_exchange_rates()
        st.write("🔱 **실시간 주요 환율**")
        for k, v in rates.items():
            st.caption(f"• **{k}**: {v}원")
            
        st.markdown("---")
        st.write("🚨 **현지 긴급 연락처**")
        
        # 저장된 긴급 연락처 불러오기
        embassy_info = current_trip.get("embassy", "• 대사관/영사관: \n• 현지 경찰/구급차: 110 / 119\n• 영사콜센터: +82-2-3210-0404")
        st.info(embassy_info)
        
        # 수정 기능 (팝오버 방식)
        with st.popover("✏️ 연락처 정보 수정"):
            with st.form("embassy_form"):
                new_embassy = st.text_area("긴급 연락처 메모", value=embassy_info)
                if st.form_submit_button("💾 저장"):
                    current_trip["embassy"] = new_embassy
                    save_data(travels)
                    st.success("긴급 연락처가 저장되었습니다!")
                    st.rerun()
    
    with col_dash_right:
        st.subheader("🗺️ 전체 관심 장소 지도")
        if map_queries:
            combined_query = " OR ".join(map_queries)
            encoded_query = urllib.parse.quote(combined_query)
            map_url = f"https://maps.google.com/maps?q={encoded_query}&t=&z=13&ie=UTF8&iwloc=&output=embed"
            components.iframe(map_url, width=400, height=400)
            st.caption(f"📍 지도 표시 항목: {', '.join(map_queries)}")
        else:
            default_query = urllib.parse.quote(city_query)
            map_url = f"https://maps.google.com/maps?q={default_query}&t=&z=12&ie=UTF8&iwloc=&output=embed"
            components.iframe(map_url, width=400, height=400)
            st.caption("💡 지도에 띄울 숙소나 관광지/맛집 항목을 목록에서 체크해 보세요!")

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
            is_discount = st.checkbox("🏷️ 특가 / 할인가 적용 항공권인가요?")

            if st.form_submit_button("➕ 항공권 추가"):
                current_trip["flights"].append({
                    "출국 항공사": dep_airline,
                    "출국 시간": f"{dep_t.strftime('%H:%M')} -> {arr_t.strftime('%H:%M')}",
                    "귀국 항공사": ret_airline,
                    "귀국 시간": f"{ret_dep_t.strftime('%H:%M')} -> {ret_arr_t.strftime('%H:%M')}",
                    "총합 가격(원)": price,
                    "할인여부": "할인가" if is_discount else "정가",
                    "상태": "후보"
                })
                save_data(travels)
                st.success("항공권이 추가되었습니다!")
                st.rerun()

        if current_trip["flights"]:
            st.subheader("📋 등록된 항공권 비교 목록")
            
            df_temp = pd.DataFrame(current_trip["flights"])
            df_sorted = df_temp.sort_values(by="총합 가격(원)", ascending=True).reset_index(drop=True)
            cheapest_item = df_sorted.iloc[0] if not df_sorted.empty else None

            for idx, flight in enumerate(current_trip["flights"]):
                price_fmt = f"{int(flight['총합 가격(원)']):,}원"
                is_cheapest = (cheapest_item is not None and 
                               flight['출국 항공사'] == cheapest_item['출국 항공사'] and 
                               flight['총합 가격(원)'] == cheapest_item['총합 가격(원)'])
                
                discount_tag = "🔥 [할인가]" if flight.get("할인여부") == "할인가" else "🏷️ [정가]"

                col_info, col_chk = st.columns([5, 1])
                with col_info:
                    if flight.get("상태") == "구매완료":
                        st.success(f"✅ **[구매 완료]** {discount_tag} {flight['출국 항공사']} ({flight['출국 시간']}) ↔ {flight['귀국 항공사']} ({flight['귀국 시간']}) | **{price_fmt}**")
                    elif is_cheapest:
                        st.info(f"💡 **[최저가 추천]** {discount_tag} {flight['출국 항공사']} ({flight['출국 시간']}) ↔ {flight['귀국 항공사']} ({flight['귀국 시간']}) | **{price_fmt}**")
                    else:
                        st.text(f"▫️ [후보] {discount_tag} {flight['출국 항공사']} ({flight['출국 시간']}) ↔ {flight['귀국 항공사']} ({flight['귀국 시간']}) | {price_fmt}")
                
                with col_chk:
                    is_now_booked = st.checkbox("구매완료", value=(flight.get("상태") == "구매완료"), key=f"f_status_{selected_travel}_{idx}")
                    new_status = "구매완료" if is_now_booked else "후보"
                    if new_status != flight.get("상태"):
                        current_trip["flights"][idx]["상태"] = new_status
                        save_data(travels)
                        st.rerun()

            if st.button("🗑️ 항공권 전체 초기화"):
                current_trip["flights"] = []
                save_data(travels)
                st.rerun()

    # [2] 🏢 숙소 후보
    with st.expander("🏢 숙소 후보"):
        with st.form("hotel_form"):
            h_name = st.text_input("숙소 이름")
            h_loc = st.text_input("위치 / 주소 (지도 표시용)")
            h_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=100000)
            is_h_discount = st.checkbox("🏷️ 특가 / 할인가 적용 숙소인가요?")
            h_link = st.text_input("숙소 링크 (URL)", placeholder="https://www.agoda.com 또는 https://www.airbnb.co.kr...")
            h_note = st.text_area("특징 및 메모")
            
            if st.form_submit_button("➕ 숙소 추가"):
                current_trip["hotels"].append({
                    "숙소명": h_name,
                    "위치": h_loc,
                    "1박 가격(원)": h_price,
                    "할인여부": "할인가" if is_h_discount else "정가",
                    "링크": h_link,
                    "메모": h_note,
                    "상태": "후보"
                })
                save_data(travels)
                st.success("숙소가 추가되었습니다!")
                st.rerun()
                
        if current_trip["hotels"]:
            st.subheader("📋 등록된 숙소 목록")
            
            df_h_temp = pd.DataFrame(current_trip["hotels"])
            df_h_sorted = df_h_temp.sort_values(by="1박 가격(원)", ascending=True).reset_index(drop=True)
            cheapest_hotel = df_h_sorted.iloc[0] if not df_h_sorted.empty else None

            delete_idx = None

            for idx, hotel in enumerate(current_trip["hotels"]):
                h_price_fmt = f"{int(hotel['1박 가격(원)']):,}원"
                is_cheapest_h = (cheapest_hotel is not None and 
                                 hotel['숙소명'] == cheapest_hotel['숙소명'] and 
                                 hotel['1박 가격(원)'] == cheapest_hotel['1박 가격(원)'])
                url = hotel.get("링크", "").strip()
                h_discount_tag = "🔥 [할인가]" if hotel.get("할인여부") == "할인가" else "🏷️ [정가]"

                c_text, c_actions = st.columns([4, 2])
                
                with c_text:
                    if hotel.get("상태") == "예약완료":
                        st.success(f"✅ **[예약 완료]** 🏢 **{hotel['숙소명']}** ({hotel['위치']}) | {h_discount_tag} 1박: {h_price_fmt}\n\n📝 메모: {hotel['메모']}")
                    elif is_cheapest_h:
                        st.info(f"💡 **[추천 가성비]** 🏢 **{hotel['숙소명']}** ({hotel['위치']}) | {h_discount_tag} 1박: {h_price_fmt}\n\n📝 메모: {hotel['메모']}")
                    else:
                        st.write(f"🏢 **{hotel['숙소명']}** ({hotel['위치']}) | {h_discount_tag} 1박: {h_price_fmt} | 📝 {hotel['메모']}")
                
                with c_actions:
                    sub_col1, sub_col2, sub_col3 = st.columns([1.2, 1, 0.8])
                    
                    with sub_col1:
                        is_h_booked = st.checkbox("예약완료", value=(hotel.get("상태") == "예약완료"), key=f"h_status_{selected_travel}_{idx}")
                        new_h_status = "예약완료" if is_h_booked else "후보"
                        if new_h_status != hotel.get("상태"):
                            current_trip["hotels"][idx]["상태"] = new_h_status
                            save_data(travels)
                            st.rerun()

                    with sub_col2:
                        if url:
                            if not (url.startswith("http://") or url.startswith("https://")):
                                url = "https://" + url
                            st.link_button("🔗 이동", url)
                        else:
                            st.caption("링크없음")

                    with sub_col3:
                        if st.button("🗑️", key=f"h_del_btn_{selected_travel}_{idx}"):
                            delete_idx = idx

                    edit_toggle = st.checkbox("✏️ 정보 수정", key=f"h_edit_toggle_{selected_travel}_{idx}")

                if edit_toggle:
                    with st.form(key=f"h_edit_form_{selected_travel}_{idx}"):
                        st.markdown(f"⚙️ **'🏢 {hotel['숙소명']}' 내용 수정**")
                        e_name = st.text_input("숙소 이름", value=hotel.get("숙소명", ""))
                        e_loc = st.text_input("위치 / 주소", value=hotel.get("위치", ""))
                        e_price = st.number_input("1박 가격 (원)", min_value=0, step=5000, value=int(hotel.get("1박 가격(원)", 100000)))
                        e_is_discount = st.checkbox("🏷️ 특가 / 할인가 적용", value=(hotel.get("할인여부") == "할인가"))
                        e_link = st.text_input("숙소 링크 (URL)", value=hotel.get("링크", ""))
                        e_note = st.text_area("특징 및 메모", value=hotel.get("메모", ""))
                        
                        if st.form_submit_button("💾 수정사항 저장"):
                            current_trip["hotels"][idx] = {
                                "숙소명": e_name,
                                "위치": e_loc,
                                "1박 가격(원)": e_price,
                                "할인여부": "할인가" if e_is_discount else "정가",
                                "링크": e_link,
                                "메모": e_note,
                                "상태": hotel.get("상태", "후보")
                            }
                            save_data(travels)
                            st.success("수정되었습니다!")
                            st.rerun()

                st.write("---")

            if delete_idx is not None:
                del current_trip["hotels"][delete_idx]
                save_data(travels)
                st.rerun()

            if st.button("🗑️ 숙소 전체 초기화"):
                current_trip["hotels"] = []
                save_data(travels)
                st.rerun()

    # [3] 📍 여행지 및 맛집
    with st.expander("📍 여행지 및 맛집"):
        with st.form("spot_form"):
            s_name = st.text_input("장소 이름 (예: 센소지, 도쿄 타워)")
            s_cat = st.selectbox("분류", ["놀거리/관광지", "맛집/카페", "쇼핑", "기타"])
            s_note = st.text_area("추천 이유 및 메모")
            if st.form_submit_button("➕ 장소 추가"):
                current_trip["spots"].append({
                    "장소명": s_name, 
                    "분류": s_cat, 
                    "메모": s_note,
                    "show_on_map": False
                })
                save_data(travels)
                st.success("장소가 추가되었습니다!")
                st.rerun()
                
        if current_trip["spots"]:
            st.subheader("📋 등록된 장소 목록")
            for idx, spot in enumerate(current_trip["spots"]):
                cat_name = spot.get("분류", "기타")
                emoji = category_emojis.get(cat_name, "📌")
                
                col_s_info, col_s_map = st.columns([4, 1.2])
                with col_s_info:
                    st.write(f"{emoji} **[{cat_name}] {spot['장소명']}** — 📝 {spot['메모']}")
                
                with col_s_map:
                    show_map = st.checkbox(
                        "🗺️ 지도에 표시", 
                        value=spot.get("show_on_map", False), 
                        key=f"spot_map_chk_{selected_travel}_{idx}"
                    )
                    if show_map != spot.get("show_on_map", False):
                        current_trip["spots"][idx]["show_on_map"] = show_map
                        save_data(travels)
                        st.rerun()

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
        uploaded_files = st.file_uploader(
            "사진 올리기 (PNG, JPG)", 
            accept_multiple_files=True, 
            type=['png', 'jpg', 'jpeg'],
            key=f"uploader_{selected_travel}"
        )
        if uploaded_files:
            cols = st.columns(3)
            for idx, file in enumerate(uploaded_files):
                with cols[idx % 3]:
                    st.image(file, use_column_width=True)

    # ------------------------------------------
    # 2. 하단 영역 (일자별 일정, 장소 불러오기 & 동선 지도)
    # ------------------------------------------
    st.write("---")
    st.header("📌 기본 일정 및 준비물")

    col_left, col_right = st.columns([1.2, 0.8])

    # 1) 불러올 수 있는 후보 목록 조합 (예약 완료 숙소 + 여행지/맛집)
    available_places = []
    
    # 예약 확정 숙소만 띄우기
    for h in current_trip["hotels"]:
        if h.get("상태") == "예약완료":
            available_places.append(f"🏢 {h['숙소명']}")
            
    # 여행지/맛집 불러오기
    for s in current_trip["spots"]:
        cat_e = category_emojis.get(s.get("분류"), "📌")
        available_places.append(f"{cat_e} {s['장소명']}")

    # 일자별 일정 작성 및 동선 배치
    with col_left:
        st.subheader("📅 일자별 일정 작성")
        
        with st.form("schedule_form"):
            sch_date = st.date_input("일정 날짜 선택", value=date.today())
            
            # 등록해둔 장소에서 불러오기 (다중 선택 드롭다운)
            selected_from_list = st.multiselect(
                "📥 입력했던 여행지/숙소 불러오기 (선택 시 내용에 추가됨)", 
                options=available_places
            )
            
            sch_content = st.text_area("상세 일정 내용 및 추가 메모")
            
            if st.form_submit_button("➕ 일정 추가"):
                combined_places = list(selected_from_list)
                formatted_date = sch_date.strftime("%Y-%m-%d")
                
                current_trip["schedule"].append({
                    "날짜": formatted_date,
                    "장소목록": combined_places,
                    "메모": sch_content
                })
                save_data(travels)
                st.success("일정이 추가되었습니다!")
                st.rerun()

        # 일자별 일정 및 동선 순서 배치 UI
        if current_trip["schedule"]:
            st.markdown("### 📌 일자별 상세 동선 및 지도")
            
            for sch_idx, sch in enumerate(current_trip["schedule"]):
                st.markdown(f"#### 🗓️ {sch.get('날짜', f'{sch_idx+1}일차')}")
                
                if sch.get("장소목록"):
                    st.caption("🔄 **방문 동선 순서 배치 (재선택으로 순서 변경 가능)**")
                    updated_order = st.multiselect(
                        f"[{sch.get('날짜')}] 방문 순서 조정",
                        options=sch["장소목록"],
                        default=sch["장소목록"],
                        key=f"order_select_{selected_travel}_{sch_idx}"
                    )
                    
                    if updated_order != sch["장소목록"]:
                        current_trip["schedule"][sch_idx]["장소목록"] = updated_order
                        save_data(travels)
                        st.rerun()

                if sch.get("메모"):
                    st.write(f"📝 메모: {sch['메모']}")
                
                # 일자별 동선 구글 지도 시각화
                if sch.get("장소목록"):
                    route_queries = [p.split(" ", 1)[-1] for p in sch["장소목록"]]
                    route_combined = " -> ".join(route_queries)
                    encoded_route = urllib.parse.quote(route_combined)
                    route_map_url = f"https://maps.google.com/maps?q={encoded_route}&t=&z=13&ie=UTF8&iwloc=&output=embed"
                    
                    st.caption(f"🗺️ [{sch.get('날짜')}] 이동 동선: {' ➔ '.join(sch['장소목록'])}")
                    components.iframe(route_map_url, width=500, height=300)
                
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
