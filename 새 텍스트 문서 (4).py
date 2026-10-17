import streamlit as st
import pandas as pd
import os

# 데이터가 저장될 CSV 파일 이름 (친구들과 공유되는 공간)
DATA_FILE = "flights_data.csv"

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=["출국 항공사", "출국 시간", "귀국 항공사", "귀국 시간", "총합 가격(원)"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

st.title("🛫 친구들과 함께 쓰는 왕복 항공권 비교")
st.write("한국 출발 항공권 정보를 입력하면 친구들과 실시간으로 가격을 비교할 수 있습니다!")

df = load_data()

# 입력 폼
with st.form("flight_form"):
    st.subheader("1. 한국 출국편")
    dep_airline = st.selectbox("출국 항공사", ["제주항공", "에어부산", "에어서울", "이스타항공", "기타"], key="dep_air")
    
    col1, col2 = st.columns(2)
    with col1:
        dep_time = st.time_input("출발 시간", value=pd.to_datetime("07:55").time())
    with col2:
        arr_time = st.time_input("도착 시간", value=pd.to_datetime("10:30").time())

    st.subheader("2. 현지 귀국편")
    ret_airline = st.selectbox("귀국 항공사", ["제주항공", "에어부산", "에어서울", "이스타항공", "기타"], key="ret_air")
    
    col3, col4 = st.columns(2)
    with col3:
        ret_dep_time = st.time_input("귀국 출발 시간", value=pd.to_datetime("14:15").time())
    with col4:
        ret_arr_time = st.time_input("귀국 도착 시간", value=pd.to_datetime("16:40").time())

    price = st.number_input("총합 가격 (원)", min_value=0, step=1000, value=300000)
    
    submitted = st.form_submit_button("➕ 항공권 추가하기")
    if submitted:
        new_row = {
            "출국 항공사": dep_airline,
            "출국 시간": f"{dep_time.strftime('%H:%M')} -> {arr_time.strftime('%H:%M')}",
            "귀국 항공사": ret_airline,
            "귀국 시간": f"{ret_dep_time.strftime('%H:%M')} -> {ret_arr_time.strftime('%H:%M')}",
            "총합 가격(원)": price
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success("항공권이 성공적으로 추가되었습니다!")
        st.rerun()

st.markdown("---")
st.subheader("📊 등록된 항공권 비교 결과 (가격 순)")

if not df.empty:
    df_sorted = df.sort_values(by="총합 가격(원)", ascending=True).reset_index(drop=True)
    
    # 화면 표시용 포맷팅
    df_display = df_sorted.copy()
    df_display["총합 가격(원)"] = df_display["총합 가격(원)"].apply(lambda x: f"{int(x):,}원")
    
    st.dataframe(df_display, use_container_width=True)
    
    cheapest = df_sorted.iloc[0]
    formatted_price = f"{int(cheapest['총합 가격(원)']):,}원"
    st.info(f"💡 **최저가 추천**: {cheapest['출국 항공사']} ({cheapest['출국 시간']}) / {cheapest['귀국 항공사']} ({cheapest['귀국 시간']}) 👉 **{formatted_price}**")
    
    if st.button("🗑️ 모든 데이터 초기화"):
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        st.rerun()
else:
    st.write("아직 등록된 항공권이 없습니다. 위에서 정보를 입력해 주세요!")
