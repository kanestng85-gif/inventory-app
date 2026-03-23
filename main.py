import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account # Updated library for better stability
from google.cloud import vision
import io
from PIL import Image
from thefuzz import process, fuzz

# --- CONFIGURATION ---
SHEET_ID = "1zmzP5iTsaqJ6h6YMn3iNHAGXudfl48uYR9vBAXbzZso"

# --- AUTHENTICATION ---
def get_google_clients():
    try:
        # Load credentials directly from the dictionary in secrets
        info = st.secrets["gcp_service_account"]
        
        # Define specific scopes
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/cloud-platform"
        ]
        
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        
        # Authorize Clients
        gs_client = gspread.authorize(creds)
        vision_client = vision.ImageAnnotatorClient(credentials=creds)
        
        return gs_client, vision_client
    except Exception as e:
        st.error(f"❌ Authentication Failed: {repr(e)}")
        return None, None

# --- APP UI ---
st.set_page_config(page_title="庫存系統", layout="centered")
st.title("📦 庫存價格同步系統")

clients = get_google_clients()
if clients:
    gs, vision_client = clients
    try:
        sheet = gs.open_by_key(SHEET_ID)
        inv_tab = sheet.worksheet("Cost")
        log_tab = sheet.worksheet("Invoice_Log")
        st.success("✅ Connected to Database")
    except Exception as e:
        st.error(f"⚠️ Connection Error: {repr(e)}")
        st.stop()

# --- FILE UPLOADER ---
uploaded_file = st.file_uploader("Upload Invoice", type=["jpg", "jpeg", "png"])

if uploaded_file and clients:
    img = Image.open(uploaded_file)
    st.image(img, use_container_width=True)
    
    if st.button("🔍 Scan & Match"):
        with st.spinner('Reading Data...'):
            try:
                # 1. Fetch Inventory
                data = inv_tab.get_all_values()
                headers = [str(h).strip().lower() for h in data[0]]
                df_inv = pd.DataFrame(data[1:], columns=headers)
                inventory_list = df_inv['name'].tolist()

                # 2. OCR
                content = uploaded_file.getvalue()
                image = vision.Image(content=content)
                response = vision_client.document_text_detection(image=image, image_context={"language_hints": ["zh-Hant"]})
                
                lines = [l.strip() for l in response.full_text_annotation.text.split('\n') if len(l.strip()) > 1]
                st.session_state['ocr_lines'] = lines
                st.session_state['inventory_list'] = inventory_list
            except Exception as e:
                st.error(f"Scan failed: {repr(e)}")

# Matching logic remains the same...
if 'ocr_lines' in st.session_state:
    st.subheader("Results")
    for i, line in enumerate(st.session_state['ocr_lines']):
        with st.expander(f"Found: {line}"):
            matches = process.extract(line, st.session_state['inventory_list'], limit=3)
            match_options = [m[0] for m in matches]
            sel = st.selectbox(f"Match (#{i})", options=match_options + ["-- Manual --"], key=f"sel_{i}")
            p = st.number_input(f"Price (#{i})", min_value=0.0, key=f"p_{i}")
            if st.button(f"Save Item {i+1}", key=f"btn_{i}"):
                ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                log_tab.append_row([ts, sel, line, str(p)])
                st.toast(f"✅ Saved: {sel}")