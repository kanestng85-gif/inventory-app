import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from thefuzz import process, fuzz
import io
from PIL import Image

# --- CONFIGURATION ---
# Copy the long ID from your URL: docs.google.com/spreadsheets/d/YOUR_ID/edit
SHEET_ID = "16yXbnBdkKuKCVGvhrUJ7YPFNVGBcyap3b5sbvqv0Dsg" 

# --- GOOGLE AUTHENTICATION (Using Secrets) ---
def get_google_clients():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gs_client = gspread.authorize(creds)
        vision_client = vision.ImageAnnotatorClient.from_service_account_info(creds_dict)
        
        return gs_client, vision_client
    except Exception as e:
        st.error(f"認證出錯: 請檢查 Streamlit Secrets 設定。 錯誤詳情: {e}")
        st.stop()

# --- OCR FUNCTION (TRADITIONAL CHINESE) ---
def extract_text(image_bytes, vision_client):
    image = vision.Image(content=image_bytes)
    response = vision_client.document_text_detection(
        image=image, 
        image_context={"language_hints": ["zh-Hant"]}
    )
    return response.full_text_annotation.text

# --- APP UI SETUP ---
st.set_page_config(page_title="繁體中文發票助手", layout="centered")
st.title("📦 庫存價格同步系統")
st.info("請上傳發票照片，系統將自動比對庫存項目。")

# Initialize connection
gs, vision_client = get_google_clients()

# --- INITIALIZE DATA FROM GOOGLE SHEETS ---
try:
    # Open by ID is much more stable than Open by Name
    sheet = gs.open_by_key(SHEET_ID)
    
    # Connect to the specific tabs
    inv_tab = sheet.worksheet("Cost")
    log_tab = sheet.worksheet("Invoice_Log")
    
    # Get all values as a list of lists
    data = inv_tab.get_all_values()
    
    if len(data) > 1:
        headers = data[0]
        rows = data[1:]
        df_inv = pd.DataFrame(rows, columns=headers)
        
        if 'Name' in df_inv.columns:
            inventory_list = df_inv['Name'].tolist()
        else:
            st.error(f"❌ 找不到 'Name' 欄位。目前欄位有: {list(df_inv.columns)}")
            st.stop()
    else:
        st.error("⚠️ 'Cost' 分頁中目前沒有資料。請至少在 A2 儲存格輸入一個品項。")
        st.stop()

except Exception as e:
    st.error(f"無法讀取試算表。請確認 ID 正確。")
    st.write(f"偵錯資訊: {e}")
    st.stop()

# --- FILE UPLOADER ---
uploaded_file = st.file_uploader("上傳發票照片 (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="發票預覽", use_container_width=True)
    
    if st.button("🔍 辨識文字並比對庫存"):
        with st.spinner('掃描辨識中...'):
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            ocr_text = extract_text(img_byte_arr.getvalue(), vision_client)
            
            lines = [l.strip() for l in ocr_text.split('\n') if len(l.strip()) > 1]
            st.session_state['ocr_lines'] = lines
            st.success("辨識完成！")

# --- MATCHING & SELECTION UI ---
if 'ocr_lines' in st.session_state:
    st.subheader("項目核對與入庫")
    
    for i, line in enumerate(st.session_state['ocr_lines']):
        with st.expander(f"原始文字: {line}", expanded=True):
            matches = process.extract(line, inventory_list, scorer=fuzz.partial_token_set_ratio, limit=3)
            match_options = [m[0] for m in matches]
            
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_item = st.selectbox(f"匹配庫存項目 (#{i})", options=match_options + ["-- 手動搜尋 --"], key=f"sel_{i}")
                if selected_item == "-- 手動搜尋 --":
                    selected_item = st.selectbox(f"從完整清單搜尋 (#{i})", options=inventory_list, key=f"manual_{i}")
            
            with col2:
                price = st.number_input(f"發票價格 (#{i})", min_value=0.0, step=1.0, key=f"p_{i}")
            
            if st.button(f"確認存入第 {i+1} 項", key=f"btn_{i}"):
                timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                log_tab.append_row([timestamp, selected_item, line, price])
                st.toast(f"✅ 已記錄: {selected_item}")

st.divider()
st.caption("提示：如需修改庫存清單，請直接前往 Google Sheet 修改 'Cost' 分頁。")