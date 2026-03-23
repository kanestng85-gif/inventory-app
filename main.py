import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from thefuzz import process, fuzz
import io
from PIL import Image

# --- CONFIGURATION ---
SHEET_ID = "1zmzP5iTsaqJ6h6YMn3iNHAGXudfl48uYR9vBAXbzZso"

# --- GOOGLE AUTHENTICATION ---
def get_google_clients():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gs_client = gspread.authorize(creds)
        vision_client = vision.ImageAnnotatorClient.from_service_account_info(creds_dict)
        return gs_client, vision_client
    except Exception as e:
        st.error(f"❌ 認證失敗: {repr(e)}")
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

uploaded_file = st.file_uploader("上傳發票照片 (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="發票預覽", use_container_width=True)
    
    if st.button("🔍 辨識文字並比對庫存"):
        with st.spinner('正在從 Google 讀取資料並辨識中...'):
            try:
                # 1. Fetch Spreadsheet Data
                sheet = gs.open_by_key(SHEET_ID)
                inv_tab = sheet.worksheet("Cost")
                data = inv_tab.get_all_values()
                
                # Setup Inventory List (Headers to lowercase for matching)
                headers = [str(h).strip().lower() for h in data[0]]
                df_inv = pd.DataFrame(data[1:], columns=headers)
                
                if 'name' not in headers:
                    st.error(f"❌ 找不到 'Name' 欄位。請確認試算表 A1 為 'Name'。偵測到: {headers}")
                    st.stop()
                
                inventory_list = df_inv['name'].tolist()

                # 2. Run OCR (Now that API is enabled!)
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                ocr_text = extract_text(img_byte_arr.getvalue(), vision_client)
                
                lines = [l.strip() for l in ocr_text.split('\n') if len(l.strip()) > 1]
                
                st.session_state['ocr_lines'] = lines
                st.session_state['inventory_list'] = inventory_list
                st.success("✅ 辨識完成！")
            except Exception as e:
                st.error(f"⚠️ 發生錯誤: {repr(e)}")

# --- MATCHING UI ---
if 'ocr_lines' in st.session_state:
    st.subheader("項目核對與入庫")
    inventory_list = st.session_state['inventory_list']
    
    for i, line in enumerate(st.session_state['ocr_lines']):
        with st.expander(f"原始文字: {line}", expanded=True):
            matches = process.extract(line, inventory_list, scorer=fuzz.partial_token_set_ratio, limit=3)
            match_options = [m[0] for m in matches]
            
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_item = st.selectbox(f"匹配項目 (#{i})", options=match_options + ["-- 手動 --"], key=f"sel_{i}")
            with col2:
                price = st.number_input(f"價格 (#{i})", min_value=0.0, step=1.0, key=f"p_{i}")
            
            if st.button(f"確認存入第 {i+1} 項", key=f"btn_{i}"):
                try:
                    sheet = gs.open_by_key(SHEET_ID)
                    log_tab = sheet.worksheet("Invoice_Log")
                    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                    log_tab.append_row([timestamp, selected_item, line, str(price)])
                    st.toast(f"✅ 已存入: {selected_item}")
                except Exception as e:
                    st.error(f"存入失敗: {repr(e)}")

st.divider()
st.caption("提示：如需修改庫存清單，請前往 Google Sheet 修改 'Cost' 分頁。")