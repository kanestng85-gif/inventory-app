import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
import io
from PIL import Image
from thefuzz import process, fuzz

# --- CONFIGURATION ---
SHEET_ID = "1zmzP5iTsaqJ6h6YMn3iNHAGXudfl48uYR9vBAXbzZso"

# --- GOOGLE AUTHENTICATION ---
def get_google_clients():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        # Explicitly define scopes for both Sheets and Drive
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/cloud-platform"
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gs_client = gspread.authorize(creds)
        
        # Initialize Vision client
        vision_client = vision.ImageAnnotatorClient.from_service_account_info(creds_dict)
        
        return gs_client, vision_client
    except Exception as e:
        st.error(f"❌ Authentication Failed: {repr(e)}")
        return None, None

def extract_text(image_bytes, vision_client):
    image = vision.Image(content=image_bytes)
    response = vision_client.document_text_detection(
        image=image, 
        image_context={"language_hints": ["zh-Hant"]}
    )
    return response.full_text_annotation.text

# --- APP UI ---
st.set_page_config(page_title="庫存系統", layout="centered")
st.title("📦 庫存價格同步系統")

gs, vision_client = get_google_clients()

# Connect to Sheet once at the start
if gs:
    try:
        sheet = gs.open_by_key(SHEET_ID)
        inv_tab = sheet.worksheet("Cost")
        log_tab = sheet.worksheet("Invoice_Log")
    except Exception as e:
        st.error(f"⚠️ Connection Error: {repr(e)}")
        st.stop()

uploaded_file = st.file_uploader("上傳發票照片", type=["jpg", "jpeg", "png"])

if uploaded_file and gs:
    img = Image.open(uploaded_file)
    st.image(img, caption="發票預覽", use_container_width=True)
    
    if st.button("🔍 辨識文字並比對庫存"):
        with st.spinner('辨識中...'):
            try:
                # Get Inventory
                data = inv_tab.get_all_values()
                headers = [str(h).strip().lower() for h in data[0]]
                df_inv = pd.DataFrame(data[1:], columns=headers)
                inventory_list = df_inv['name'].tolist()

                # OCR
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                ocr_text = extract_text(img_byte_arr.getvalue(), vision_client)
                
                lines = [l.strip() for l in ocr_text.split('\n') if len(l.strip()) > 1]
                st.session_state['ocr_lines'] = lines
                st.session_state['inventory_list'] = inventory_list
                st.success("辨識完成！")
            except Exception as e:
                st.error(f"發生錯誤: {repr(e)}")

# UI for matching results (same as before)
if 'ocr_lines' in st.session_state:
    st.subheader("項目核對與入庫")
    for i, line in enumerate(st.session_state['ocr_lines']):
        with st.expander(f"原始文字: {line}", expanded=True):
            matches = process.extract(line, st.session_state['inventory_list'], limit=3)
            match_options = [m[0] for m in matches]
            col1, col2 = st.columns([2, 1])
            with col1:
                sel = st.selectbox(f"匹配項目 (#{i})", options=match_options + ["-- 手動 --"], key=f"sel_{i}")
            with col2:
                p = st.number_input(f"價格 (#{i})", min_value=0.0, key=f"p_{i}")
            if st.button(f"確認存入第 {i+1} 項", key=f"btn_{i}"):
                ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                log_tab.append_row([ts, sel, line, str(p)])
                st.toast(f"✅ 已存入: {sel}")