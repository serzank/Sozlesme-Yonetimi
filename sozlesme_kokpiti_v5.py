import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from evds import evdsAPI
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import urllib3
import requests
from bs4 import BeautifulSoup
import io
import google.generativeai as genai
import calendar
import time
import re
import plotly.graph_objects as go
import json

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# --- KÜTÜPHANE KONTROLÜ ---
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import xlsxwriter
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ve GÜVENLİK (SECRETS) ---
try:
    MY_API_KEY = st.secrets["EVDS_KEY"]
except:
    MY_API_KEY = None 

try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
except:
    GEMINI_API_KEY = None

try:
    ALPHA_VANTAGE_KEY = st.secrets["ALPHA_VANTAGE_KEY"]
except:
    ALPHA_VANTAGE_KEY = None

try:
    FRED_API_KEY = st.secrets["FRED_KEY"]
except:
    FRED_API_KEY = None

# --- Sayfa Ayarları ---
st.set_page_config(page_title="PNX | Procurement Nexus", layout="wide", page_icon="💠")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    .kutu, .kutu-enerji { padding: 15px; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; color: #1E3D59 !important; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; color: #1E3D59 !important; }
    .kutu *, .kutu-enerji *, .kutu b, .kutu-enerji b { color: #1E3D59 !important; }
    .pozitif { color: #27AE60 !important; font-weight: bold; font-size: 18px; }
    .negatif { color: #C0392B !important; font-weight: bold; font-size: 18px; }
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; text-decoration: none; }
    div[data-testid="stNumberInput"] label { font-size: 13px !important; color: #333 !important; }
    .badge-live { background-color: #27AE60; color: white !important; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; vertical-align: middle; }
    .badge-tcmb { background-color: #1E3D59; color: white !important; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: bold; vertical-align: middle; margin-left: 5px; }
    .badge-est { background-color: #F39C12; color: white !important; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: bold; vertical-align: middle; margin-left: 5px; }
    div[data-testid="stDateInput"] { width: 100% !important; }
    .stButton button { width: 100%; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---

WEIGHT_KEYS = ["mix", "tufe", "ufe", "hufe", "iscilik", "usd", "eur", "altin", "benzin", "dizel", "brent", "jet_fuel", "abd", "euro_enf", "abd_enf", "bakir", "alum", "gaz", "celik", "scrap_steel", "scrap_alum", "propan", "lityum", "demir", "nikel", "cinko", "pamuk", "bugday", "kakao", "plastik"]

def get_cross_currency_rate(base_curr, target_curr, start_dt, end_dt):
    if base_curr == target_curr:
        return 0.0, 1.0, 1.0 
    
    ticker_symbol = f"{base_curr}{target_curr}=X"
    try:
        ticker = yf.Ticker(ticker_symbol)
        df_fx = ticker.history(start=start_dt, end=end_dt)
        if not df_fx.empty:
            p_start = float(df_fx['Close'].iloc[0])
            p_end = float(df_fx['Close'].iloc[-1])
            pct_change = ((p_end - p_start) / p_start) * 100
            return pct_change, p_start, p_end
    except Exception:
        pass
    return 0.0, 1.0, 1.0

def extract_text_from_pdf(uploaded_file):
    if not HAS_PYPDF or uploaded_file is None:
        return ""
    try:
        reader = pypdf.PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except Exception as e:
        st.error(f"PDF okuma hatası: {str(e)}")
        return ""

def clean_str(text):
    if not text:
        return ""
    tr_map = {
        "İ": "I", "ı": "i", "Ğ": "G", "ğ": "g", 
        "Ü": "U", "ü": "u", "Ş": "S", "ş": "s", 
        "Ö": "O", "ö": "o", "Ç": "C", "ç": "c"
    }
    for tr, en in tr_map.items():
        text = str(text).replace(tr, en)
    return text.encode("latin-1", errors="replace").decode("latin-1")

def create_executive_pdf_report(sozlesme_tipi, sozlesme_tutari, zam, fark, yeni, etkiler, jarvis_comment, start_date, end_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 61, 89)
    
    pdf.cell(0, 10, clean_str("COST NEXUS | EXECUTIVE PROCUREMENT REPORT"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, clean_str(f"Rapor Tarihi: {datetime.today().strftime('%d.%m.%Y')} | Donem: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    pdf.set_draw_color(39, 174, 96)
    pdf.set_line_width(0.8)
    pdf.line(10, 30, 200, 30)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 61, 89)
    pdf.cell(0, 8, clean_str("1. SOZLESME VE HAKEDIS OZETI"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 10)
    pdf.set_fill_color(248, 249, 250)
    
    safe_sozlesme_tipi = clean_str(sozlesme_tipi)
    
    pdf.cell(60, 8, clean_str(" Sozlesme Turu:"), 1, 0, "L", fill=True)
    pdf.cell(130, 8, f" {safe_sozlesme_tipi}", 1, 1, "L")
    pdf.cell(60, 8, clean_str(" Baslangic Tutari:"), 1, 0, "L", fill=True)
    pdf.cell(130, 8, clean_str(f" {tr_fmt(sozlesme_tutari)} TL"), 1, 1, "L")
    pdf.cell(60, 8, clean_str(" Toplam Eskalasyon Orani:"), 1, 0, "L", fill=True)
    pdf.cell(130, 8, clean_str(f" %{zam:.2f}"), 1, 1, "L")
    pdf.cell(60, 8, clean_str(" Fiyat Farkı Yuksekligi:"), 1, 0, "L", fill=True)
    pdf.cell(130, 8, clean_str(f" {tr_fmt(fark)} TL"), 1, 1, "L")
    pdf.cell(60, 8, clean_str(" GUNCEL HAKEDIS TUTARI:"), 1, 0, "L", fill=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(130, 8, clean_str(f" {tr_fmt(yeni)} TL"), 1, 1, "L")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 61, 89)
    pdf.cell(0, 8, clean_str("2. AKTIF SEPET VE MALIYET ETKI DETAYLARI"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(30, 61, 89)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(70, 7, clean_str(" Girdi Kalemi"), 1, 0, "L", fill=True)
    pdf.cell(40, 7, clean_str(" Degisim (%)"), 1, 0, "C", fill=True)
    pdf.cell(40, 7, clean_str(" Sepet Agirligi (%)"), 1, 0, "C", fill=True)
    pdf.cell(40, 7, clean_str(" Net Etki (%)"), 1, 1, "C", fill=True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    for ad, deg, agr in etkiler:
        if agr > 0:
            clean_ad = clean_str(ad)
            pdf.cell(70, 6, f" {clean_ad}", 1, 0, "L")
            pdf.cell(40, 6, f" %{deg:+.2f}", 1, 0, "C")
            pdf.cell(40, 6, f" %{agr:.0f}", 1, 0, "C")
            pdf.cell(40, 6, f" %{(deg*agr)/100:+.2f}", 1, 1, "C")
    pdf.ln(5)
    
    if jarvis_comment:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 61, 89)
        pdf.cell(0, 8, clean_str("3. JARVIS AI FINANSAL EVALUATION & RISK DEGERLENDIRMESI"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(50, 50, 50)
        clean_comment = clean_str(jarvis_comment)
        pdf.multi_cell(0, 5, clean_comment, border=1)
        pdf.ln(10)
        
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(30, 61, 89)
    pdf.cell(63, 6, clean_str("Hazirlayan (Purchasing Spec.)"), 0, 0, "C")
    pdf.cell(63, 6, clean_str("Inceleyen (Procurement Mgr.)"), 0, 0, "C")
    pdf.cell(63, 6, clean_str("Onaylayan (CFO / Committee)"), 0, 1, "C")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(63, 15, "Imza: ....................", 0, 0, "C")
    pdf.cell(63, 15, "Imza: ....................", 0, 0, "C")
    pdf.cell(63, 15, "Imza: ....................", 0, 1, "C")
    
    return bytes(pdf.output())

def ai_kapsam_analizi(kapsam_metni, api_key):
    if not api_key or not kapsam_metni.strip():
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        prompt = f"""
        Sen TAV Havalimanları Holding kıdemli Satın Alma ve Maliyet Mühendisisin.
        Aşağıda verilen İş Kapsamı / İhale Şartnamesi metnini analiz et ve bu işin maliyet yapısını oluşturan hammadde/girdi ağırlıklarını %100 toplam verecek şekilde dağıt.

        KULLANILABİLİR KALEMLER (Sadece bu anahtarları kullan):
        "mix", "tufe", "ufe", "hufe", "iscilik", "usd", "eur", "altin", "benzin", "dizel", "brent", "jet_fuel", "euro_enf", "abd_enf", "bakir", "alum", "gaz", "celik", "scrap_steel", "scrap_alum", "propan", "lityum", "demir", "nikel", "cinko", "pamuk", "bugday", "kakao", "plastik"

        İŞ KAPSAMI METNİ:
        "{kapsam_metni}"

        ÇIKTI FORMATI:
        Sadece ve sadece geçerli bir JSON objesi dön. Başka hiçbir açıklama yazma.
        Örnek: {{"bakir": 30, "celik": 20, "eur": 20, "iscilik": 20, "dizel": 10}}
        Toplam tam olarak 100 olmalıdır.
        """
        res = model.generate_content(prompt)
        clean_json = re.sub(r'```json|```', '', res.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Kapsam analizi yapılırken hata oluştu: {str(e)}")
        return None

# --- FRED ENDEKS BAZLI YÜZDE DEĞİŞİM MOTORU ---
@st.cache_data(ttl=3600)
def get_global_inflation_change(api_key, series_id, target_start_date, target_end_date):
    if not api_key:
        return 0.0, 0.0, 0.0

    try:
        s_date = (target_start_date - timedelta(days=90)).strftime("%Y-%m-%d")
        e_date = datetime.today().strftime("%Y-%m-%d")
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&observation_start={s_date}&observation_end={e_date}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            obs = res.json().get("observations", [])
            valid = []
            for o in obs:
                if o["value"] not in [None, ".", ""]:
                    valid.append((pd.to_datetime(o["date"]), float(o["value"])))

            if valid:
                df = pd.DataFrame(valid, columns=["Date", "Value"]).set_index("Date")

                past = df[df.index <= pd.Timestamp(target_start_date)]
                latest = df[df.index <= pd.Timestamp(target_end_date)]

                ilk = float(past.iloc[-1]["Value"]) if not past.empty else float(df.iloc[0]["Value"])
                son = float(latest.iloc[-1]["Value"]) if not latest.empty else float(df.iloc[-1]["Value"])

                deg = ((son - ilk) / ilk) * 100 if ilk > 0 else 0.0

                return round(ilk, 2), round(son, 2), round(deg, 2)

    except:
        pass

    return 0.0, 0.0, 0.0

def get_fred_index_change(api_key, series_id, target_start_date):
    _, _, degisim = get_global_inflation_change(
        api_key,
        series_id,
        target_start_date,
        datetime.today().date())
        
    return degisim

def render_svg_logo():
    return """
    <svg width="100%" height="auto" viewBox="0 0 280 70" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:#1E3D59;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#2C3E50;stop-opacity:1" />
        </linearGradient>
      </defs>
      <path d="M40 35 L70 35" stroke="#27AE60" stroke-width="2" />
      <path d="M40 35 L30 15" stroke="#27AE60" stroke-width="1" />
      <path d="M40 35 L30 55" stroke="#27AE60" stroke-width="1" />
      <polygon points="40,15 57,25 57,45 40,55 23,45 23,25" fill="#1E3D59" stroke="#27AE60" stroke-width="2" />
      <text x="75" y="32" font-family="Verdana" font-weight="900" font-size="28" fill="#1E3D59" letter-spacing="-1">COST NEXUS</text>
      <text x="75" y="50" font-family="Arial" font-size="11" fill="#888" font-weight="bold" letter-spacing="1">PROCUREMENT</text>
      <text x="162" y="50" font-family="Arial" font-size="11" fill="#27AE60" font-weight="bold" letter-spacing="1">VISION</text>
    </svg>
    """

def tr_fmt(deger):
    try:
        if pd.isna(deger) or deger is None: deger = 0.0
        s = "{:,.2f}".format(float(deger))
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

def safe_float(val):
    try:
        if val is None: return 0.0
        if pd.isna(val): return 0.0
        return float(val)
    except: return 0.0

# --- EMTİA KART BİLEŞENİ ---
def emtia_karti(col, baslik, key):
    val = piyasa.get(key, {"ilk": 0.0, "son": 0.0, "degisim": 0.0})
    ilk = safe_float(val["ilk"])
    son = safe_float(val["son"])
    deg = safe_float(val["degisim"])
    
    key_eski = f"e_{key}_{d_key}"
    key_yeni = f"y_{key}_{d_key}"
    
    with col:
        st.markdown(f"<div class='kutu-enerji'><b>{baslik}</b>", unsafe_allow_html=True)
        st.markdown("<label style='font-size:13px;'>Geçmiş Fiyat <span class='badge-est'>Düzenle</span></label>", unsafe_allow_html=True)
        e_input = st.number_input("eski", value=ilk, format="%.2f", key=key_eski, label_visibility="collapsed")
        
        badge_txt = "CANLI" if son > 0 else "DÜZENLE"
        st.markdown(f"<label style='font-size:13px;'>Güncel Fiyat <span class='badge-live'>{badge_txt}</span></label>", unsafe_allow_html=True)
        y_input = st.number_input("yeni", value=son, format="%.2f", key=key_yeni, label_visibility="collapsed")
        
        if e_input > 0 and abs(e_input - ilk) > 0.01:
            deg = ((y_input - e_input) / e_input * 100)
            
        renk = "pozitif" if deg >= 0 else "negatif"
        st.markdown(f"<div style='text-align:right;'><span class='{renk}'>%{deg:+.2f}</span></div></div>", unsafe_allow_html=True)
        
    return deg

# --- ALTIN GEÇMİŞİ EVDS MOTORU ---
@st.cache_data(ttl=600)
def get_evds_gold_history(api_key, d_start):
    price = 0.0
    if not api_key: return price
    try:
        evds = evdsAPI(api_key)
        s_date_str = (d_start - timedelta(days=7)).strftime("%d-%m-%Y")
        e_date_str = d_start.strftime("%d-%m-%Y")
        series = ["TP.MK.KUL.YTL"]
        df = evds.get_data(series, startdate=s_date_str, enddate=e_date_str)
        if df is not None and not df.empty:
             col = [c for c in df.columns if "TP" in c][0]
             df[col] = pd.to_numeric(df[col], errors='coerce')
             df.dropna(subset=[col], inplace=True)
             if not df.empty: price = float(df.iloc[-1][col])
    except: pass
    return price

# --- 2. ÜFE: EVDS API ÜZERİNDEN ---
@st.cache_data(ttl=3600)
def get_evds_ufe_data(api_key, start_date, end_date):
    ufe_val = 0.0
    if not api_key: return ufe_val
    try:
        evds_service = evdsAPI(api_key)
        s_date = start_date - relativedelta(months=2)
        e_date = end_date + relativedelta(months=1)
        
        start_q = s_date.replace(day=1).strftime("%d-%m-%Y")
        next_month = e_date + relativedelta(months=1)
        last_day_date = next_month.replace(day=1) - timedelta(days=1)
        end_q = last_day_date.strftime("%d-%m-%Y")

        raw_df = evds_service.get_data(["TP.TUFE1YI.T1"], startdate=start_q, enddate=end_q)
        if raw_df is not None and not raw_df.empty:
            tarih_col = next((c for c in raw_df.columns if "TARIH" in c.upper() or "DATE" in c.upper()), None)
            val_col = [c for c in raw_df.columns if c != tarih_col][0]
            
            raw_df['Tarih_Dt'] = pd.to_datetime(raw_df[tarih_col], errors='coerce')
            raw_df[val_col] = pd.to_numeric(raw_df[val_col].astype(str).str.replace(',', '.'), errors='coerce')
            raw_df = raw_df.dropna(subset=['Tarih_Dt', val_col]).sort_values('Tarih_Dt')
            raw_df['Period'] = raw_df['Tarih_Dt'].dt.to_period('M')

            p_start = pd.Period(start_date, freq='M')
            p_end = pd.Period(end_date, freq='M')

            matches_s = raw_df[raw_df['Period'] <= p_start]
            start_row = matches_s.iloc[-1] if not matches_s.empty else raw_df.iloc[0]

            matches_e = raw_df[raw_df['Period'] <= p_end]
            latest_row = matches_e.iloc[-1] if not matches_e.empty else raw_df.iloc[-1]

            v_start = safe_float(start_row[val_col])
            v_end = safe_float(latest_row[val_col])

            if v_start > 0 and v_end > 0:
                ufe_val = round(((v_end / v_start) - 1) * 100, 2)
    except: pass
    return ufe_val

# --- SÖZLEŞME AĞIRLIK MANTIĞI ---
def get_auto_weights(contract_type):
    w = {
        "mix": 0, "tufe": 0, "ufe": 0, "hufe": 0,
        "iscilik": 0, "usd": 0, "eur": 0, "altin": 0,
        "benzin": 0, "dizel": 0, "brent": 0, "abd": 0,
        "jet_fuel": 0, "euro_enf": 0, "abd_enf": 0,
        "bakir": 0, "alum": 0, "gaz": 0, "celik": 0, "demir": 0, "nikel": 0, "cinko": 0,
        "pamuk": 0, "bugday": 0, "kakao": 0, "plastik": 0, "propan": 0, "scrap_steel": 0,
        "scrap_alum": 0, "lityum": 0, "gumus": 0, "coal": 0, "eugas": 0, "naphtha": 0
    }
    if contract_type == "Personel Taşımacılık":
        w["dizel"] = 35; w["iscilik"] = 40; w["tufe"] = 25
    elif contract_type == "Yiyecek-İçecek Hizmetleri":
        w["tufe"] = 30; w["iscilik"] = 30; w["hufe"] = 10; w["usd"] = 10; w["bugday"] = 10; w["kakao"] = 10
    elif contract_type == "Yazılım / Lisans":
        w["usd"] = 60; w["eur"] = 20; w["tufe"] = 20
    elif contract_type == "Bilişim Sarf (Donanım)":
        w["usd"] = 100
    elif contract_type == "Güvenlik Hizmetleri":
        w["iscilik"] = 85; w["tufe"] = 10; w["hufe"] = 5
    elif contract_type == "İnşaat & Tesisat / Mekanik":
        w["celik"] = 20; w["bakir"] = 15; w["scrap_steel"] = 15; w["demir"] = 10; w["iscilik"] = 20; w["tufe"] = 20
    elif contract_type == "Tekstil & Üniforma":
        w["pamuk"] = 40; w["iscilik"] = 40; w["tufe"] = 20
    elif contract_type == "Ambalaj & Plastik":
        w["plastik"] = 40; w["naphtha"] = 10; w["usd"] = 30; w["tufe"] = 20
    elif contract_type == "Serzan'ın Klasiği (TÜFE+ÜFE)":
        w["mix"] = 100
    else: 
        w["tufe"] = 30; w["iscilik"] = 30; w["usd"] = 20; w["eur"] = 10; w["hufe"] = 10
    return w

# --- ASGARİ ÜCRET HESAPLAYICI ---
def get_asgari_ucret_degisim(d_start, d_end):
    maas_tablosu = [
        (date(2026, 1, 1), 28732.0),
        (date(2025, 7, 1), 22102.0),
        (date(2025, 1, 1), 22102.0),
        (date(2024, 1, 1), 17002.12),
        (date(2023, 7, 1), 11402.32),
        (date(2023, 1, 1), 8506.80),
        (date(2022, 7, 1), 5500.35),
        (date(2022, 1, 1), 4253.40),
        (date(2021, 1, 1), 2825.90)
    ]
    def get_val(tarih):
        for baslangic, ucret in maas_tablosu:
            if tarih >= baslangic: return ucret
        return 2825.90
    ucret_start = get_val(d_start)
    ucret_end = get_val(d_end)
    degisim = 0.0
    if ucret_start > 0: degisim = ((ucret_end - ucret_start) / ucret_start) * 100
    return degisim, ucret_start, ucret_end

# --- GOOGLE SHEET H-ÜFE ÇEKİCİ ---
@st.cache_data(ttl=300)
def get_google_sheet_data():
    try:
        sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKKPo73sRdzL227kxw9PRvtd6teIyu74v0bw4NCZUCDmJBXgKxZ3AHYmD4zrkalxVgkOSc1lK6p7PF/pub?output=csv"
        df = pd.read_csv(sheet_url)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')
        
        df['Tarih'] = pd.to_datetime(df['Tarih'], format='%Y-%m-%d', errors='coerce')
        df = df.dropna(subset=['Tarih']).sort_values('Tarih')
        df['Donem'] = df['Tarih'].dt.strftime('%Y-%m')
        
        for col in df.columns:
            if col not in ['Tarih', 'Donem']:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

# --- DOVIZ.COM CANLI SCRAPER ---
@st.cache_data(ttl=60)
def doviz_com_canli_cek():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    data = {"USD": 0.0, "EUR": 0.0, "BRENT_PETROL": 0.0, "ALTIN": 0.0}
    
    try:
        res = requests.get("https://www.doviz.com", headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            usd_box = soup.find("span", {"data-socket-key": "USD", "data-socket-attr": "s"})
            eur_box = soup.find("span", {"data-socket-key": "EUR", "data-socket-attr": "s"})
            altin_box = soup.find("span", {"data-socket-key": "gram-altin", "data-socket-attr": "s"})
            
            if usd_box: data["USD"] = float(usd_box.get_text().replace(".", "").replace(",", "."))
            if eur_box: data["EUR"] = float(eur_box.get_text().replace(".", "").replace(",", "."))
            if altin_box: data["ALTIN"] = float(altin_box.get_text().replace(".", "").replace(",", "."))
    except: pass

    try:
        res_brent = requests.get("https://www.doviz.com/emtia/brent-petrol", headers=headers, timeout=5)
        if res_brent.status_code == 200:
            soup = BeautifulSoup(res_brent.content, "html.parser")
            brent_box = soup.find("span", {"data-socket-key": "brent-petrol", "data-socket-attr": "s"})
            if not brent_box:
                brent_box = soup.find("div", {"class": "value"})
            if brent_box:
                raw_val = brent_box.get_text().replace("$", "").replace(".", "").replace(",", ".").strip()
                data["BRENT_PETROL"] = float(raw_val)
    except: pass

    return data

# --- TRADINGECONOMICS CANLI SCRAPER ---
@st.cache_data(ttl=60)
def trading_economics_live_all():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    live_data = {
        "CRUDE_OIL": 88.80, "BRENT_PETROL": 96.67, "DOGALGAZ": 2.8913, "GASOLINE": 3.3711,
        "HEATING_OIL": 4.1926, "COAL": 130.75, "EUGAS": 62.11, "UKGAS": 150.35, "ETHANOL": 1.9350,
        "NAPHTHA": 833.63, "PROPAN": 0.77, "URANIUM": 85.85, "METHANOL": 2692.00, "LNG_JKM": 21.83,
        "ONS_ALTIN": 4053.97, "GUMUS": 58.306, "BAKIR": 6.3203, "STEEL_CNY": 3066.00, "LITYUM": 145500.0,
        "DEMIR_CNY": 746.00, "PLATIN": 1610.00, "COBALT": 53823.59, "HRC_STEEL": 1194.12,
        "SCRAP_ALUM": 2347.92, "DEMIR": 98.47, "SILICON": 8245.00, "SCRAP_STEEL": 402.50, "TITANIUM": 46.00,
        "ALUMINYUM": 2480.0, "NIKEL": 16500.0, "CINKO": 2800.0, "PAMUK": 78.0, "BUGDAY": 580.0, "KAKAO": 7800.0, "PLASTIK": 1150.0
    }
    
    try:
        url = "https://tradingeconomics.com/commodities"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        name = cols[0].get_text().strip().lower()
                        val_str = cols[1].get_text().strip().replace(',', '')
                        try:
                            val = float(val_str)
                            if "brent" in name: live_data["BRENT_PETROL"] = val
                            elif "crude oil" in name: live_data["CRUDE_OIL"] = val
                            elif "natural gas" in name: live_data["DOGALGAZ"] = val
                            elif "copper" in name: live_data["BAKIR"] = val
                            elif "aluminum" in name: live_data["ALUMINYUM"] = val
                            elif "gold" in name: live_data["ONS_ALTIN"] = val
                            elif "silver" in name: live_data["GUMUS"] = val
                            elif "propane" in name: live_data["PROPAN"] = val
                            elif "scrap steel" in name: live_data["SCRAP_STEEL"] = val
                            elif "scrap aluminum" in name: live_data["SCRAP_ALUM"] = val
                            elif "lithium" in name: live_data["LITYUM"] = val
                            elif "coal" in name: live_data["COAL"] = val
                            elif "eu gas" in name: live_data["EUGAS"] = val
                            elif "naphtha" in name: live_data["NAPHTHA"] = val
                            elif "hrc steel" in name: live_data["HRC_STEEL"] = val
                        except: pass
    except: pass

    return live_data

@st.cache_data(ttl=600)
def guncel_akaryakit_cek():
    url = "https://www.doviz.com/akaryakit-fiyatlari/istanbul-avrupa"
    headers = {'User-Agent': 'Mozilla/5.0'}
    fiyatlar = {"benzin": 0.0, "motorin": 0.0}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find('table')
            if table:
                rows = table.find('tbody').find_all('tr')
                if rows:
                    cols = rows[0].find_all('td')
                    if len(cols) >= 3:
                        raw_benzin = cols[1].get_text().replace('₺', '').strip().replace(',', '.')
                        raw_motorin = cols[2].get_text().replace('₺', '').strip().replace(',', '.')
                        fiyatlar["benzin"] = float(raw_benzin)
                        fiyatlar["motorin"] = float(raw_motorin)
    except: pass
    return fiyatlar

# --- GOOGLE SHEET TABANLI KUSURSUZ TÜFE VE H-ÜFE MOTORU ---
@st.cache_data(ttl=0)
def get_sheets_tufe_data(sheet_url, start_date, end_date):
    res = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Yok"}
    if not sheet_url: return res
    try:
        csv_url = sheet_url.split("/edit")[0] + "/export?format=csv" if "edit" in sheet_url else sheet_url
            
        df_raw = pd.read_csv(csv_url)
        if df_raw.empty:
            res["Msg"] = "Sheet verisi boş."
            return res
            
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.dropna(how='all')
        
        tarih_col = df_raw.columns[0]
        tufe_col = df_raw.columns[1]

        df_clean = pd.DataFrame()
        df_clean['Tarih_Dt'] = pd.to_datetime(df_raw[tarih_col], errors='coerce')
        
        cleaned_vals = (
            df_raw[tufe_col]
            .astype(str)
            .str.strip()
            .str.replace("\u00A0", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(',', '.', regex=False)
        )
        df_clean['TUFE_COL'] = pd.to_numeric(cleaned_vals, errors='coerce')
        df_clean = df_clean.dropna(subset=['Tarih_Dt', 'TUFE_COL']).sort_values('Tarih_Dt')

        if df_clean.empty:
            res["Msg"] = "Tarih veya TÜFE değerleri sayısal formata çevrilemedi."
            return res

        df_clean['Period'] = df_clean['Tarih_Dt'].dt.to_period('M')

        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')

        matches_s = df_clean[df_clean['Period'] <= p_start]
        start_row = matches_s.iloc[-1] if not matches_s.empty else df_clean.iloc[0]

        matches_e = df_clean[df_clean['Period'] <= p_end]
        latest_row = matches_e.iloc[-1] if not matches_e.empty else df_clean.iloc[-1]

        v_start = float(start_row["TUFE_COL"])
        v_end = float(latest_row["TUFE_COL"])

        tufe_diff = round(((v_end / v_start) - 1) * 100, 2)
        
        if v_start > 0 and v_end > 0:
            res.update({
                "TUFE": tufe_diff,
                "Status": True,
                "Msg": f"Sheet Enflasyon Dönemi: {start_row['Period']} ({v_start}) ➡️ {latest_row['Period']} ({v_end})"
            })
        else:
            res["Msg"] = f"Değerler sıfır: v_start={v_start}, v_end={v_end}"
    except Exception as e:
        res["Msg"] = f"Sheet Okuma Hatası: {str(e)}"
    return res

@st.cache_data(ttl=600)
def get_evds_fuel_history(api_key, d_start):
    res = {"benzin": 0.0, "motorin": 0.0}
    if not api_key: return res
    try:
        evds = evdsAPI(api_key)
        s_date_str = (d_start - timedelta(days=30)).strftime("%d-%m-%Y")
        e_date_str = d_start.strftime("%d-%m-%Y")
        series = ["TP.AK.U95", "TP.AK.MTR"]
        df = evds.get_data(series, startdate=s_date_str, enddate=e_date_str)
        if df is not None and not df.empty:
            cols_b = [c for c in df.columns if "TP_AK_U95" in c or "TP.AK.U95" in c]
            if cols_b:
                s_b = pd.to_numeric(df[cols_b[0]].astype(str).str.replace(',', '.'), errors='coerce').dropna()
                if not s_b.empty: res["benzin"] = float(s_b.iloc[-1])
            cols_m = [c for c in df.columns if "TP_AK_MTR" in c or "TP.AK.MTR" in c]
            if cols_m:
                s_m = pd.to_numeric(df[cols_m[0]].astype(str).str.replace(',', '.'), errors='coerce').dropna()
                if not s_m.empty: res["motorin"] = float(s_m.iloc[-1])
    except: pass
    return res

# ============================================================================
# SOL MENÜ (SIDEBAR) TANIMLARI
# ============================================================================
with st.sidebar:
    st.markdown(render_svg_logo(), unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)
    
    st.info("ℹ️ Merhaba Sir, finansal düğümlerin çözüldüğü yerdesiniz.")
    
    sozlesme_tipi = st.selectbox(
        "📄 Sözleşme Türü",
        ["Serzan'ın Klasiği (TÜFE+ÜFE)", "Manuel Giriş", "Personel Taşımacılık", "Yiyecek-İçecek Hizmetleri", "Yazılım / Lisans", "Bilişim Sarf (Donanım)", "Güvenlik Hizmetleri", "İnşaat & Tesisat / Mekanik", "Tekstil & Üniforma", "Ambalaj & Plastik"]
    )
    
    c_tutar1, c_tutar2 = st.columns([2, 1])
    tutar_giris = c_tutar1.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    sozlesme_periyodu = c_tutar2.selectbox("Periyot", ["Yıllık", "Aylık"])
    
    try: 
        sozlesme_tutari = float(tutar_giris.replace(".", "").replace(",", "."))
    except: 
        sozlesme_tutari = 0.0

    st.markdown("---")
    st.markdown("##### 🌍 Sözleşme & Saha Para Birimi")
    c_fx1, c_fx2 = st.columns(2)
    # KZT, GEL, BHD ve SAR hem Sözleşme hem de Saha para birimi listesine eklendi
    contract_curr = c_fx1.selectbox("Sözleşme Döviz Türü", ["EUR", "USD", "TRY", "GBP", "KZT", "GEL", "BHD", "SAR"], index=0)
    cost_curr = c_fx2.selectbox("Saha / Masraf Birimi", ["TRY", "KZT", "GEL", "EUR", "USD", "BHD", "SAR"], index=0)      


# ============================================================================
# SEPET AĞIRLIKLARI STATE YÖNETİMİ
# ============================================================================
if 'last_sozlesme_tipi' not in st.session_state or st.session_state.last_sozlesme_tipi != sozlesme_tipi:
    st.session_state.last_sozlesme_tipi = sozlesme_tipi
    auto_w = get_auto_weights(sozlesme_tipi)
    for k in WEIGHT_KEYS:
        st.session_state[f"w_{k}"] = float(auto_w.get(k, 0))

# ============================================================================
# ANA EKRAN - ÜST KISIM (TARİH SEÇİMİ)
# ============================================================================
if 'ss_start' not in st.session_state:
    st.session_state.ss_start = date.today() - relativedelta(years=1)
if 'ss_end' not in st.session_state:
    st.session_state.ss_end = date.today()

def set_quick_date(months):
    st.session_state.ss_start = st.session_state.ss_end - relativedelta(months=months)

def set_ytd_date():
    current_year = st.session_state.ss_end.year
    st.session_state.ss_start = date(current_year, 1, 1)

with st.container(border=True): 
    st.markdown("##### 📅 Tarih Aralığı Seçimi")
    c_date1, c_date2 = st.columns(2)
    
    with c_date1:
        start_date = st.date_input("Başlangıç Tarihi", key="ss_start", format="DD.MM.YYYY")
    with c_date2:
        end_date = st.date_input("Bitiş Tarihi (Güncel)", key="ss_end", format="DD.MM.YYYY")
        
    b1, b2, b3, b4, b5 = st.columns([1, 1, 1, 1.2, 2.5])
    with b1: st.button("3 Ay", on_click=set_quick_date, args=(3,), use_container_width=True)
    with b2: st.button("6 Ay", on_click=set_quick_date, args=(6,), use_container_width=True)
    with b3: st.button("1 Yıl", on_click=set_quick_date, args=(12,), use_container_width=True)
    with b4: st.button("Sene Başı", on_click=set_ytd_date, use_container_width=True, help="Başlangıç tarihini 1 Ocak'a çeker.")
    with b5: st.markdown(f"<div style='padding-top:10px; font-size:12px; color:gray'>*Seçili Bitiş Tarihine göre hesaplar.</div>", unsafe_allow_html=True)

if start_date >= end_date: st.error("Hata: Başlangıç < Bitiş olmalı!")
d_key = f"{start_date}_{end_date}"

# --- VERİ KÖPRÜSÜ ---
with st.spinner("PNX Veritabanlarına Bağlanıyor..."):
    tufe_sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS1f-Ix-2hu_Gcuc0_dxZ-BcZbvoHPPewNmQAkOrC6H1nKOR_TYaAtyhWO2KObVArIvus0l1AvrsLY9/pub?output=csv"
    
    tufe_res = get_sheets_tufe_data(tufe_sheet_url, start_date, end_date)
    ufe_val = get_evds_ufe_data(MY_API_KEY, start_date, end_date)
    
    tcmb = {
        "TUFE": tufe_res["TUFE"],
        "UFE": ufe_val,
        "HUFE": 0.0,
        "Status": tufe_res["Status"],
        "Msg": tufe_res["Msg"]
    }
    
    yakit_guncel = guncel_akaryakit_cek()
    doviz_com_data = doviz_com_canli_cek() 
    te_data_live = trading_economics_live_all() 
    evds_gold_ilk = get_evds_gold_history(MY_API_KEY, start_date)
    evds_fuel_ilk = get_evds_fuel_history(MY_API_KEY, start_date)
    df_hufe = get_google_sheet_data()

# ============================================================================
# PİYASA VERİSİ İŞLEME
# ============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def piyasa_verisi_al_tekli(d_start, d_end, doviz_data, evds_gold_start, evds_key, te_data, fred_key):
    data_dict = {}

    fx_map = {"USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "EURUSD": "EURUSD=X"}
    for k_fx, ticker_code in fx_map.items():
        ilk_val, son_val = 0.0, 0.0
        try:
            t = yf.Ticker(ticker_code)
            h = t.history(start=d_start - timedelta(days=5), end=d_start + timedelta(days=5))
            if not h.empty:
                ilk_val = float(h['Close'].iloc[0])
                son_val = float(h['Close'].iloc[-1])
        except: pass

        data_dict[k_fx] = {"ilk": ilk_val, "son": son_val, "degisim": 0.0}

    if data_dict["USDTRY"]["ilk"] == 0 and evds_key:
        try:
            evds_service = evdsAPI(evds_key)
            s_evds = (d_start - timedelta(days=10)).strftime("%d-%m-%Y")
            e_evds = d_start.strftime("%d-%m-%Y")
            evds_df = evds_service.get_data(["TP.DK.USD.A.YTL"], startdate=s_evds, enddate=e_evds)
            if evds_df is not None and not evds_df.empty:
                v_col = [c for c in evds_df.columns if "USD" in c or "TP" in c][0]
                data_dict["USDTRY"]["ilk"] = float(pd.to_numeric(evds_df[v_col].astype(str).str.replace(',', '.'), errors='coerce').dropna().iloc[-1])
        except: pass

    if data_dict["EURTRY"]["ilk"] == 0 and evds_key:
        try:
            evds_service = evdsAPI(evds_key)
            s_evds = (d_start - timedelta(days=10)).strftime("%d-%m-%Y")
            e_evds = d_start.strftime("%d-%m-%Y")
            evds_df = evds_service.get_data(["TP.DK.EUR.A.YTL"], startdate=s_evds, enddate=e_evds)
            if evds_df is not None and not evds_df.empty:
                v_col = [c for c in evds_df.columns if "EUR" in c or "TP" in c][0]
                data_dict["EURTRY"]["ilk"] = float(pd.to_numeric(evds_df[v_col].astype(str).str.replace(',', '.'), errors='coerce').dropna().iloc[-1])
        except: pass

    if doviz_data.get("USD", 0) > 0: data_dict["USDTRY"]["son"] = doviz_data["USD"]
    if doviz_data.get("EUR", 0) > 0: data_dict["EURTRY"]["son"] = doviz_data["EUR"]

    euro_ilk, euro_son, euro_deg = get_global_inflation_change(
        fred_key,
        "CP0000EZ19M086NEST",
        d_start,
        d_end)
    
    abd_ilk, abd_son, abd_deg = get_global_inflation_change(
        fred_key,
        "CPIAUCSL",
        d_start,
        d_end)

    data_dict["BRENT_PETROL"] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}
    try:
        b_ticker = yf.Ticker("BZ=F")
        b_hist = b_ticker.history(start=d_start - timedelta(days=5), end=d_start + timedelta(days=5))
        if not b_hist.empty:
            data_dict["BRENT_PETROL"]["ilk"] = float(b_hist['Close'].iloc[0])
    except: pass

    if data_dict["BRENT_PETROL"]["ilk"] == 0 and evds_key:
        try:
            evds_service = evdsAPI(evds_key)
            s_evds = (d_start - timedelta(days=10)).strftime("%d-%m-%Y")
            e_evds = d_start.strftime("%d-%m-%Y")
            evds_brent = evds_service.get_data(["TP.AK.BRENT"], startdate=s_evds, enddate=e_evds)
            if evds_brent is not None and not evds_brent.empty:
                v_col = [c for c in evds_brent.columns if "BRENT" in c or "TP" in c][0]
                data_dict["BRENT_PETROL"]["ilk"] = float(pd.to_numeric(evds_brent[v_col].astype(str).str.replace(',', '.'), errors='coerce').dropna().iloc[-1])
        except: pass

    if doviz_data.get("BRENT_PETROL", 0) > 0:
        data_dict["BRENT_PETROL"]["son"] = doviz_data["BRENT_PETROL"]
    elif te_data.get("BRENT_PETROL", 0) > 0:
        data_dict["BRENT_PETROL"]["son"] = te_data["BRENT_PETROL"]

    data_dict["JET_FUEL"] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}
    try:
        j_ticker = yf.Ticker("HO=F")
        j_hist_s = j_ticker.history(start=d_start - timedelta(days=7), end=d_start + timedelta(days=7))
        j_hist_e = j_ticker.history(start=d_end - timedelta(days=7), end=d_end + timedelta(days=1))
        
        if not j_hist_s.empty and not j_hist_e.empty:
            data_dict["JET_FUEL"]["ilk"] = round(float(j_hist_s['Close'].iloc[-1]) * 42, 2)
            data_dict["JET_FUEL"]["son"] = round(float(j_hist_e['Close'].iloc[-1]) * 42, 2)
            i_val = data_dict["JET_FUEL"]["ilk"]
            s_val = data_dict["JET_FUEL"]["son"]
            if i_val > 0:
                data_dict["JET_FUEL"]["degisim"] = round(((s_val - i_val) / i_val) * 100, 2)
    except Exception: pass

    if fred_key and data_dict["JET_FUEL"]["son"] == 0:
        try:
            url_j = f"https://api.stlouisfed.org/fred/series/observations?series_id=PJETUSDM&api_key={fred_key}&file_type=json&sort_order=desc&limit=1"
            res_j = requests.get(url_j, timeout=5)
            if res_j.status_code == 200:
                obs = res_j.json().get("observations", [])
                if obs and obs[0].get("value") not in [None, ".", ""]:
                    latest_val = float(obs[0]["value"])
                    pct_j = get_fred_index_change(fred_key, "PJETUSDM", d_start)
                    data_dict["JET_FUEL"]["son"] = round(latest_val, 2)
                    data_dict["JET_FUEL"]["degisim"] = pct_j
                    if (1 + pct_j/100) != 0:
                        data_dict["JET_FUEL"]["ilk"] = round(latest_val / (1 + pct_j/100), 2)
        except Exception: pass

    if data_dict["JET_FUEL"]["son"] == 0 and data_dict["BRENT_PETROL"]["son"] > 0:
        b_ilk = data_dict["BRENT_PETROL"]["ilk"]
        b_son = data_dict["BRENT_PETROL"]["son"]
        data_dict["JET_FUEL"]["ilk"] = round(b_ilk * 1.18, 2)
        data_dict["JET_FUEL"]["son"] = round(b_son * 1.18, 2)
        data_dict["JET_FUEL"]["degisim"] = data_dict["BRENT_PETROL"]["degisim"]

    for te_key, te_val in te_data.items():
        if te_key not in data_dict:
            data_dict[te_key] = {"ilk": 0.0, "son": te_val, "degisim": 0.0}

    if fred_key:
        fred_map = {
            "BAKIR": "PCOPPUSDM", "ALUMINYUM": "PALUMUSDM", "DOGALGAZ": "PNGASUSDM",
            "PLASTIK": "WPU066", "PROPAN": "PROPANEM", "SCRAP_STEEL": "WPU1012",
            "SCRAP_ALUM": "WPU102301", "HRC_STEEL": "WPUSI019011", "DEMIR": "PIRONUSDM",
            "NIKEL": "PNICKUSDM", "CINKO": "PZINCUSDM", "PAMUK": "PCOTTUSDM",
            "BUGDAY": "PWHEAMTUSDM", "KAKAO": "PCOCOUSDM", "COAL": "PCOALAUUSDM"
        }
        for k_fred, series_id in fred_map.items():
            if k_fred in data_dict and data_dict[k_fred]["son"] > 0:
                pct = get_fred_index_change(fred_key, series_id, d_start)
                if k_fred == "JET_FUEL" and data_dict["JET_FUEL"]["ilk"] > 0 and data_dict["JET_FUEL"]["ilk"] != data_dict["JET_FUEL"]["son"]: continue
                
                if pct == 0.0:
                    yf_backup_map = {"DOGALGAZ": "NG=F", "PLASTIK": "PLASTIK.L", "BAKIR": "HG=F"}
                    if k_fred in yf_backup_map:
                        try:
                            yt = yf.Ticker(yf_backup_map[k_fred])
                            yh = yt.history(start=d_start - timedelta(days=5), end=d_start + timedelta(days=5))
                            if not yh.empty:
                                y_ilk = float(yh['Close'].iloc[0])
                                y_son = float(yh['Close'].iloc[-1])
                                if y_ilk > 0: pct = ((y_son - y_ilk) / y_ilk) * 100
                        except: pass

                data_dict[k_fred]["degisim"] = pct
                if (1 + pct/100) != 0:
                    data_dict[k_fred]["ilk"] = round(data_dict[k_fred]["son"] / (1 + pct/100), 2)

    gold_son = doviz_data.get("ALTIN", 0.0)
    if gold_son <= 0:
        ons_s = te_data.get("ONS_ALTIN", 0.0)
        usd_s = data_dict.get("USDTRY", {}).get("son", 0)
        if ons_s > 0 and usd_s > 0: gold_son = (ons_s / 31.1035) * usd_s

    gold_ilk = evds_gold_start
    if gold_ilk <= 0:
        ons_i = data_dict.get("ONS_ALTIN", {}).get("ilk", 0)
        usd_i = data_dict.get("USDTRY", {}).get("ilk", 0)
        if ons_i > 0 and usd_i > 0: gold_ilk = (ons_i / 31.1035) * usd_i

    data_dict["GRAM_ALTIN_TL"] = {"ilk": gold_ilk, "son": gold_son, "degisim": ((gold_son - gold_ilk) / gold_ilk * 100) if gold_ilk > 0 else 0.0}

    if fred_key and data_dict.get("ABD_TAHVIL", {}).get("son", 0) == 0:
        try:
            pct_tnx = get_fred_index_change(fred_key, "DGS10", d_start)
            url_tnx = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={fred_key}&file_type=json&sort_order=desc&limit=1"
            res_tnx = requests.get(url_tnx, timeout=5)
            if res_tnx.status_code == 200:
                obs = res_tnx.json().get("observations", [])
                if obs and obs[0].get("value") not in [None, ".", ""]:
                    latest_val = float(obs[0]["value"])
                    start_val = round(latest_val / (1 + pct_tnx / 100), 2) if (1 + pct_tnx / 100) != 0 else 0.0
                    data_dict["ABD_TAHVIL"] = {"ilk": start_val, "son": latest_val, "degisim": pct_tnx}
        except: pass

    for k in ["USDTRY", "EURTRY", "BRENT_PETROL"]:
        v = data_dict[k]
        ilk_val, son_val = safe_float(v["ilk"]), safe_float(v["son"])
        v["degisim"] = ((son_val - ilk_val) / ilk_val * 100) if (ilk_val > 0 and son_val > 0) else 0.0

    if data_dict["EURUSD"]["ilk"] == 0 and data_dict["USDTRY"]["ilk"] > 0 and data_dict["EURTRY"]["ilk"] > 0:
        data_dict["EURUSD"]["ilk"] = data_dict["EURTRY"]["ilk"] / data_dict["USDTRY"]["ilk"]
            
    if data_dict["EURUSD"]["son"] == 0 or doviz_data.get("USD", 0) > 0:
        u_son = data_dict["USDTRY"]["son"] if data_dict["USDTRY"]["son"] > 0 else doviz_data.get("USD", 1)
        e_son = data_dict["EURTRY"]["son"] if data_dict["EURTRY"]["son"] > 0 else doviz_data.get("EUR", 1)
        data_dict["EURUSD"]["son"] = e_son / u_son
    
    p_ilk, p_son = data_dict["EURUSD"]["ilk"], data_dict["EURUSD"]["son"]
    data_dict["EURUSD"]["degisim"] = ((p_son - p_ilk) / p_ilk * 100) if p_ilk > 0 else 0.0

    data_dict["EURO_HICP"] = {"ilk": euro_ilk, "son": euro_son, "degisim": euro_deg}
    data_dict["ABD_CPI"] = {"ilk": abd_ilk, "son": abd_son, "degisim": abd_deg}
    
    return data_dict

piyasa = piyasa_verisi_al_tekli(start_date, end_date, doviz_com_data, evds_gold_ilk, MY_API_KEY, te_data_live, FRED_API_KEY)
euro_enf_val = piyasa.get("EURO_HICP", {}).get("degisim", 0.0)
abd_cpi_val = piyasa.get("ABD_CPI", {}).get("degisim", 0.0)

# ============================================================================
# GÖSTERGE PANELİ (DASHBOARD)
# ============================================================================
st.title("💠Procurement Node | Financial Datum")

with st.container(border=True):
    st.subheader("📊 Piyasa Göstergeleri")
    def kutu(col, baslik, key, ikon):
        val = piyasa.get(key, {"ilk":0, "son":0, "degisim":0})
        ilk, son, deg = safe_float(val["ilk"]), safe_float(val["son"]), safe_float(val["degisim"])
        w_key = f"{key}_{d_key}"
        with col:
            st.markdown(f"<div class='kutu'><div style='display:flex; align-items:center; margin-bottom:5px;'><span style='font-size:20px; margin-right:8px;'>{ikon}</span><b>{baslik}</b></div>", unsafe_allow_html=True)
            if son == 0: deg = st.number_input(f"{baslik} %", value=0.0, step=0.1, key=w_key)
            else:
                renk = "pozitif" if deg >= 0 else "negatif"
                st.markdown(f"<div style='font-size:12px; color:#666 !important;'>Eski: {tr_fmt(ilk)}</div>", unsafe_allow_html=True)
                ek_bilgi = " (Canlı)" if ("GRAM" in key or "USD" in key or "EUR" in key or "BRENT" in key) and (doviz_com_data.get("USD",0) > 0 or doviz_com_data.get("BRENT_PETROL",0) > 0 or doviz_com_data.get("ALTIN",0) > 0) else ""
                st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:baseline;'><span class='big-metric'>{tr_fmt(son)}</span><span class='{renk}'>%{deg:+.2f}</span></div>", unsafe_allow_html=True)
                if ek_bilgi: st.markdown(f"<div style='font-size:10px; color:#27AE60; text-align:right;'>{ek_bilgi}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        return deg

    k1, k2, k3, k4 = st.columns(4)
    d_usd = kutu(k1, "USD/TL", "USDTRY", "💵")
    d_eur = kutu(k2, "EUR/TL", "EURTRY", "💶")
    d_gram = kutu(k3, "Gram Altın", "GRAM_ALTIN_TL", "🥇")
    d_parite = kutu(k4, "EUR/USD", "EURUSD", "⚖️")

    st.markdown("### 🛢️ Enerji Emtiaları")
    e1, e2, e3, e4, e5 = st.columns(5)
    d_brent = kutu(e1, "Brent Petrol ($/Bbl)", "BRENT_PETROL", "🛢️")
    d_jet = emtia_karti(e5, "✈️ Jet A-1 ($/Bbl)", "JET_FUEL")

    benzin_yeni_val = yakit_guncel.get("benzin", 0.0) if yakit_guncel.get("benzin", 0) > 0 else 44.0
    motorin_yeni_val = yakit_guncel.get("motorin", 0.0) if yakit_guncel.get("motorin", 0) > 0 else 45.0
    is_proxy = False
    if evds_fuel_ilk["benzin"] > 0:
        benzin_eski_val = evds_fuel_ilk["benzin"]
        motorin_eski_val = evds_fuel_ilk["motorin"]
    else:
        is_proxy = True
        usd_ilk = piyasa["USDTRY"]["ilk"]
        usd_son = piyasa["USDTRY"]["son"]
        ratio = usd_ilk / usd_son if usd_son > 0 and usd_ilk > 0 else 1.0
        benzin_eski_val = round(benzin_yeni_val * ratio, 2)
        motorin_eski_val = round(motorin_yeni_val * ratio, 2)

    with e2:
        badge = f"<span class='badge-live'>CANLI: {benzin_yeni_val} TL</span>" if yakit_guncel.get("benzin", 0) > 0 else ""
        st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b> {badge}", unsafe_allow_html=True)
        etiket_b = "Eski (TL) <span class='badge-tcmb'>✅ TCMB</span>" if not is_proxy else "Eski (TL) <span class='badge-est'>⚠️ Tahmin</span>"
        st.markdown(f"<label style='font-size:13px;'>{etiket_b}</label>", unsafe_allow_html=True)
        b_eski = st.number_input("bo", value=benzin_eski_val, key=f"bo_{d_key}", label_visibility="collapsed")
        st.markdown("<label style='font-size:13px;'>Yeni (TL)</label>", unsafe_allow_html=True)
        b_yeni = st.number_input("bn", value=benzin_yeni_val, key=f"bn_{d_key}", label_visibility="collapsed")
        d_benzin = ((b_yeni-b_eski)/b_eski)*100 if b_eski > 0 else 0
        st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

    with e3:
        badge_m = f"<span class='badge-live'>CANLI: {motorin_yeni_val} TL</span>" if yakit_guncel.get("motorin", 0) > 0 else ""
        st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b> {badge_m}", unsafe_allow_html=True)
        etiket_m = "Eski (TL) <span class='badge-tcmb'>✅ TCMB</span>" if not is_proxy else "Eski (TL) <span class='badge-est'>⚠️ Tahmin</span>"
        st.markdown(f"<label style='font-size:13px;'>{etiket_m}</label>", unsafe_allow_html=True)
        m_eski = st.number_input("mo", value=motorin_eski_val, key=f"mo_{d_key}", label_visibility="collapsed")
        st.markdown("<label style='font-size:13px;'>Yeni (TL)</label>", unsafe_allow_html=True)
        m_yeni = st.number_input("mn", value=motorin_yeni_val, key=f"mn_{d_key}", label_visibility="collapsed")
        d_dizel = ((m_yeni-m_eski)/m_eski)*100 if m_eski > 0 else 0
        st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

    kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

    st.markdown("### 🌍 Küresel Enflasyon Endeksleri")
    i1, i2, _, _ = st.columns(4)
    d_euro_enf = kutu(i1, "Avrupa Enf. (HICP)", "EURO_HICP", "🇪🇺")
    d_abd_cpi   = kutu(i2, "ABD CPI", "ABD_CPI", "🇺🇸")

    st.markdown("### 🏗️ Sanayi, Metal, Tarım & Hammadde Emtiaları")
    
    em1, em2, em3, em4 = st.columns(4)
    d_bakir   = emtia_karti(em1, "🔌 Bakır ($/Lbs)", "BAKIR")
    d_alum    = emtia_karti(em2, "🏗️ Alüminyum ($/Ton)", "ALUMINYUM")
    d_gaz     = emtia_karti(em3, "🔥 Doğal Gaz ($/MMBtu)", "DOGALGAZ")
    d_propan = emtia_karti(em4, "🔥 Propan ($/Gal)", "PROPAN")

    em5, em6, em7, em8 = st.columns(4)
    d_celik        = emtia_karti(em5, "🔩 Çelik / HRC ($/Ton)", "HRC_STEEL")
    d_scrap_steel = emtia_karti(em6, "♻️ Hurda Çelik ($/Ton)", "SCRAP_STEEL")
    d_scrap_alum  = emtia_karti(em7, "♻️ Hurda Alüminyum ($/Ton)", "SCRAP_ALUM")
    d_demir        = emtia_karti(em8, "⛏️ Demir Cevheri ($/Ton)", "DEMIR")

    em9, em10, em11, em12 = st.columns(4)
    d_lityum  = emtia_karti(em9, "🔋 Lityum (CNY/T)", "LITYUM")
    d_nikel   = emtia_karti(em10, "🔋 Nikel ($/Ton)", "NIKEL")
    d_cinko   = emtia_karti(em11, "🛡️ Çinko ($/Ton)", "CINKO")
    d_coal    = emtia_karti(em12, "🪨 Kömür ($/T)", "COAL")

    em13, em14, em15, em16 = st.columns(4)
    d_pamuk   = emtia_karti(em13, "🧶 Pamuk ($/Lbs)", "PAMUK")
    d_bugday  = emtia_karti(em14, "🌾 Buğday ($/Bu)", "BUGDAY")
    d_kakao   = emtia_karti(em15, "🍫 Kakao ($/MT)", "KAKAO")
    d_plastik = emtia_karti(em16, "🧪 Plastik/Polimer ($/MT)", "PLASTIK")

# ============================================================================
# İNTERAKTİF PLOTLY BORSA GRAFİK MODÜLÜ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.subheader("📈 Emtia & Kur İnteraktif Trend Analizi (Plotly Borsa Terminali)")
    
    chart_symbols = {
        "Dolar (USD/TL)": "TRY=X",
        "Euro (EUR/TL)": "EURTRY=X",
        "Parite (EUR/USD)": "EURUSD=X",
        "Gram Altın (TL)": "GC=F",
        "Brent Petrol ($/Bbl)": "BZ=F",
        "Jet A-1 Yakıt ($/Bbl)": "HO=F",
        "Doğal Gaz ($/MMBtu)": "NG=F",
        "Propan ($/Gal)": "PN=F",
        "Kömür ($/Ton)": "MTF=F",
        "Bakır ($/Lbs)": "HG=F",
        "Alüminyum ($/Ton)": "ALI=F",
        "Hurda Alüminyum ($/Ton)": "ALI=F",
        "Çelik / HRC ($/Ton)": "HRC=F",
        "Hurda Çelik ($/Ton)": "HRC=F",
        "Demir Cevheri ($/Ton)": "TI=F",
        "Nikel ($/Ton)": "NKL=F",
        "Çinko ($/Ton)": "ZNC=F",
        "Pamuk ($/Lbs)": "CT=F",
        "Buğday ($/Bu)": "ZW=F",
        "Kakao ($/MT)": "CC=F",
        "Plastik / Polimer ($/MT)": "PLASTIK.L"
    }
    
    c_sel1, _ = st.columns([2, 2])
    with c_sel1:
        selected_chart_item = st.selectbox("🎯 Grafik İçin Emtia / Kur Seçiniz", list(chart_symbols.keys()))
    
    symbol_code = chart_symbols[selected_chart_item]
    
    try:
        df_hist = yf.download(symbol_code, start=start_date, end=end_date, progress=False)
        if not df_hist.empty and "Close" in df_hist.columns:
            close_series = df_hist["Close"]
            if isinstance(close_series, pd.DataFrame):
                close_series = close_series.iloc[:, 0]
                
            close_series = close_series.dropna().copy()
            
            if "HO=F" in symbol_code or selected_chart_item.startswith("Jet"):
                close_series = close_series * 42.0
            
            fig_plotly = go.Figure()
            fig_plotly.add_trace(go.Scatter(
                x=close_series.index,
                y=close_series.values,
                mode='lines',
                name='Fiyat ($/Bbl)' if "HO=F" in symbol_code else 'Fiyat',
                line=dict(color='#27AE60' if "HO=F" in symbol_code else '#1E3D59', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(39, 174, 96, 0.1)' if "HO=F" in symbol_code else 'rgba(30, 61, 89, 0.1)',
                hovertemplate="<b>Tarih:</b> %{x|%d %b %Y}<br><b>Fiyat:</b> $%{y:,.2f}<extra></extra>"
            ))

            fig_plotly.update_layout(
                title=f"<b>{selected_chart_item}</b> — Tarihsel Değişim Grafiği",
                xaxis_title="Tarih",
                yaxis_title="Fiyat ($/Varil)" if "HO=F" in symbol_code else "Fiyat / Değer",
                template="plotly_white",
                hovermode="x unified",
                height=420,
                margin=dict(l=40, r=40, t=50, b=40),
                xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.05)', rangeslider=dict(visible=True), type="date"),
                yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
            )

            st.plotly_chart(fig_plotly, use_container_width=True)
        else:
            st.info("Seçilen tarih aralığı için grafik verisi indiriliyor...")
    except Exception as e:
        st.caption("Grafik yüklenirken bir teknik kısıt oluştu, sayısal veriler yukarıda mevcuttur.")

# ============================================================================
# PNX DÖVİZ ÇEVRİM MATRİSİ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.subheader("💱 PNX Value Matrix: Alım Gücü Analizi")
    
    u_son = piyasa["USDTRY"]["son"] if piyasa["USDTRY"]["son"] > 0 else 1.0
    e_son = piyasa["EURTRY"]["son"] if piyasa["EURTRY"]["son"] > 0 else 1.0
    
    u_ilk = piyasa["USDTRY"]["ilk"] if piyasa["USDTRY"]["ilk"] > 0 else u_son
    e_ilk = piyasa["EURTRY"]["ilk"] if piyasa["EURTRY"]["ilk"] > 0 else e_son
    
    tutar_usd_baslangic = sozlesme_tutari / u_ilk
    tutar_usd_guncel = sozlesme_tutari / u_son
    fark_usd = tutar_usd_guncel - tutar_usd_baslangic
    
    tutar_eur_baslangic = sozlesme_tutari / e_ilk
    tutar_eur_guncel = sozlesme_tutari / e_son
    fark_eur = tutar_eur_guncel - tutar_eur_baslangic

    c_usd, c_eur = st.columns(2)
    with c_usd:
        st.markdown(f"**💵 USD Bazlı Değerleme**")
        col_u1, col_u2, col_u3 = st.columns(3)
        col_u1.metric("Başlangıç ($)", tr_fmt(tutar_usd_baslangic))
        col_u2.metric("Güncel ($)", tr_fmt(tutar_usd_guncel))
        col_u3.metric("Erime ($)", tr_fmt(fark_usd), delta_color="normal")
    
    with c_eur:
        st.markdown(f"**💶 EUR Bazlı Değerleme**")
        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("Başlangıç (€)", tr_fmt(tutar_eur_baslangic))
        col_e2.metric("Güncel (€)", tr_fmt(tutar_eur_guncel))
        col_e3.metric("Erime (€)", tr_fmt(fark_eur), delta_color="normal")
        
    st.markdown(f"<div style='font-size:11px; color:gray; text-align:right'>*Hesaplama: Girilen {tr_fmt(sozlesme_tutari)} TL'nin, başlangıç tarihi ve bugünkü kurlar üzerinden karşılığıdır.</div>", unsafe_allow_html=True)

# ============================================================================
# HESAPLAMA MOTORU & SEPET AĞIRLIKLARI
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_header, c_link = st.columns([3, 1])
    with c_header: st.subheader("⚡ Enflasyon & Sepet Hesabı")
    with c_link: st.link_button("🔗 Manuel Hesaplama Sitesi", "https://tufehesaplama-serzan.streamlit.app/")

    if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
    else: st.warning(f"⚠️ {tcmb['Msg']}")

    tum_sektorler = []
    if not df_hufe.empty:
        tum_sektorler = [col for col in df_hufe.columns if col not in ['Tarih', 'Donem']]
    else:
        tum_sektorler = ["Veri Yüklenemedi"]

    preselect_idx = 0
    search_keyword = ""
    
    if sozlesme_tipi == "Güvenlik Hizmetleri": search_keyword = "Güvenlik"
    elif sozlesme_tipi == "Personel Taşımacılık": search_keyword = "Kara"
    elif sozlesme_tipi == "Yiyecek-İçecek Hizmetleri": search_keyword = "Yiyecek"
    elif sozlesme_tipi == "Yazılım / Lisans": search_keyword = "Bilgi"
    
    if search_keyword:
        for i, s in enumerate(tum_sektorler):
            if search_keyword in s:
                preselect_idx = i
                break

    st.markdown("##### 📊 H-ÜFE Sektör Seçimi")
    c_search, c_select, c_manuel = st.columns([2, 3, 1])
    
    with c_search:
        filter_text = st.text_input("🔍 Sektör Ara (Filtre)", value=search_keyword)
    
    filtered_list = tum_sektorler
    if filter_text:
        filtered_list = [s for s in tum_sektorler if filter_text.lower() in s.lower()]
        if not filtered_list: filtered_list = tum_sektorler
    
    with c_select:
        final_idx = 0
        if tum_sektorler[preselect_idx] in filtered_list:
            final_idx = filtered_list.index(tum_sektorler[preselect_idx])
            
        selected_sector = st.selectbox("📋 Listeden Seçiniz", filtered_list, index=final_idx, label_visibility="collapsed")
    
    with c_manuel:
        st.link_button("🔗 TÜİK Kontrol", "https://data.tuik.gov.tr/Kategori/GetKategori?p=Enflasyon-ve-Fiyat-106")

    val_hufe_final = 0.0
    debug_sheet = st.expander(f"🕵️ H-ÜFE Hesaplama Detayı: {selected_sector}", expanded=False)

    if not df_hufe.empty and selected_sector:
        try:
            target_start = pd.to_datetime(start_date)
            target_end = pd.to_datetime(end_date)
            
            past_hufe = df_hufe[df_hufe['Tarih'] <= target_start]
            row_s = past_hufe.iloc[-1] if not past_hufe.empty else df_hufe.iloc[0]
            row_e = df_hufe.iloc[-1] 
            
            v1 = safe_float(row_s[selected_sector])
            v2 = safe_float(row_e[selected_sector])
            
            d1_str = row_s['Tarih'].strftime('%d.%m.%Y')
            d2_str = row_e['Tarih'].strftime('%d.%m.%Y')

            debug_sheet.write(f"**Hedef Başlangıç:** {start_date} ➡️ **Bulunan:** {d1_str} (Değer: {v1})")
            debug_sheet.write(f"**Hedef Bitiş:** {end_date} ➡️ **Bulunan:** {d2_str} (Değer: {v2})")

            if v1 > 0:
                val_hufe_final = round(((v2 - v1) / v1) * 100, 2)
                debug_sheet.success(f"✅ Hesaplanan H-ÜFE Değişimi: %{val_hufe_final:.2f}")
            else:
                debug_sheet.error("Başlangıç değeri 0 olduğu için hesaplanamadı.")
                
        except Exception as e:
            debug_sheet.error(f"Hesaplama Hatası: {str(e)}")
            val_hufe_final = 0.0

    val_tufe = safe_float(tcmb["TUFE"])
    val_ufe = safe_float(tcmb["UFE"])
    val_mix = round((val_tufe + val_ufe) / 2, 2)
    
    val_iscilik, asgari_eski, asgari_yeni = get_asgari_ucret_degisim(start_date, end_date)
    iscilik_notu = f"{tr_fmt(asgari_eski)} ➡️ {tr_fmt(asgari_yeni)} TL"

    if f"t_{d_key}" not in st.session_state:
        st.session_state[f"t_{d_key}"] = val_tufe

    ec1, ec2, ec_mix, ec3, ec4, ec5 = st.columns(6)
    tufe = ec1.number_input("TÜFE %", value=val_tufe, key=f"t_{d_key}")
    ufe = ec2.number_input("ÜFE %", value=val_ufe, key=f"u_{d_key}")
    ort_mix_giris = ec_mix.number_input("Ort(TÜFE+ÜFE)", value=val_mix, key=f"mix_{d_key}")
    
    h_ufe = ec3.number_input("H-ÜFE %", value=val_hufe_final, key=f"h_{d_key}_{selected_sector}", help=f"Seçilen Sektör: {selected_sector}")
    iscilik = ec4.number_input("İşçilik %", value=val_iscilik, key=f"i_{d_key}", help=f"Otomatik Hesaplanan Asgari Ücret:\n{iscilik_notu}")
    abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")
    
    if val_iscilik > 0:
        ec4.markdown(f"<div style='font-size:10px; color:#27AE60'>ASG: {iscilik_notu}</div>", unsafe_allow_html=True)
    
    ec3.markdown(f"<div style='font-size:10px; color:#F39C12'>{selected_sector[:15]}...</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### ⚖️ Sepet Ağırlıkları")

    with st.expander("✨ Yapay Zeka ile Şartname / PDF Okuyucu (Drag & Drop)", expanded=False):
        c_up1, c_up2 = st.columns([1, 1])
        
        with c_up1:
            uploaded_pdf = st.file_uploader("📄 Şartname veya Sözleşme PDF'i Sürükleyin", type=["pdf"], help="Tedarikçiden gelen teklif, şartname veya sözleşme PDF'ini yükleyin.")
            
        with c_up2:
            kapsam_input = st.text_area(
                "Veya İş Kapsamını / Metraj Açıklamasını Metin Olarak Yapıştırın:", 
                placeholder="Örn: Lounge ince işler kapsamında ahşap kaplamalar, özel imalat mobilya, lokal işçilik, ithal aydınlatma ve lojistik giderleri dahildir...",
                height=100
            )
        
        if st.button("🚀 Şartnameyi Analiz Et ve Sepeti Doldur", use_container_width=True):
            extracted_text = ""
            if uploaded_pdf is not None:
                with st.spinner("PDF dokümanı okunuyor ve OCR işlemi yapılıyor..."):
                    extracted_text = extract_text_from_pdf(uploaded_pdf)
            
            final_text_to_analyze = extracted_text if extracted_text.strip() else kapsam_input
            
            if not final_text_to_analyze.strip():
                st.warning("Lütfen bir PDF dosyası yükleyin veya metin alanına iş kapsamını girin.")
            else:
                with st.spinner("Jarvis (Gemini 2.5) şartname maddelerini tarıyor ve maliyet kırılımı çıkarıyor..."):
                    ai_weights = ai_kapsam_analizi(final_text_to_analyze, GEMINI_API_KEY)
                    if ai_weights:
                        for k in WEIGHT_KEYS:
                            st.session_state[f"w_{k}"] = 0.0
                        for key, val in ai_weights.items():
                            clean_k = key.lower().replace("ğ", "g")
                            if clean_k in WEIGHT_KEYS:
                                st.session_state[f"w_{clean_k}"] = float(val)
                        
                        st.success("✅ Şartname / PDF başarıyla analiz edildi ve sepet ağırlıkları güncellendi!")
                        if extracted_text:
                            st.info(f"ℹ️ Okunan PDF Boyutu: {len(extracted_text)} karakter. Şartname içindeki maliyet girdileri tespit edildi.")
                        st.rerun()

    w1, w2, w3, w4 = st.columns(4)
    w_mix_oran = w1.number_input("TÜFE+ÜFE Ort. %", key="w_mix")
    w_tufe = w2.number_input("Saf TÜFE %", key="w_tufe")
    w_ufe = w3.number_input("Saf ÜFE %", key="w_ufe")
    w_hufe = w4.number_input("H-ÜFE %", key="w_hufe")
    
    w5, w6, w7, w8 = st.columns(4)
    w_iscilik = w5.number_input("İşçilik %", key="w_iscilik")
    w_usd = w6.number_input("USD %", key="w_usd")
    w_eur = w7.number_input("EUR %", key="w_eur")
    w_altin = w8.number_input("Altın %", key="w_altin")
    
    w9, w10, w11, w12 = st.columns(4)
    w_benzin = w9.number_input("Benzin %", key="w_benzin")
    w_dizel = w10.number_input("Motorin %", key="w_dizel")
    w_brent = w11.number_input("Brent %", key="w_brent")
    w_abd = w12.number_input("ABD Enf. %", key="w_abd")

    w13, w14, w15, w16 = st.columns(4)
    w_bakir = w13.number_input("Bakır %", key="w_bakir")
    w_alum  = w14.number_input("Alüminyum %", key="w_alum")
    w_gaz   = w15.number_input("Doğal Gaz %", key="w_gaz")
    w_celik = w16.number_input("Çelik %", key="w_celik")

    w17, w18, w19, w20 = st.columns(4)
    w_scrap_steel = w17.number_input("Hurda Çelik %", key="w_scrap_steel")
    w_scrap_alum  = w18.number_input("Hurda Alüminyum %", key="w_scrap_alum")
    w_propan      = w19.number_input("Propan %", key="w_propan")
    w_lityum      = w20.number_input("Lityum %", key="w_lityum")

    w21, w22, w23, w24 = st.columns(4)
    w_demir   = w21.number_input("Demir Cevheri %", key="w_demir")
    w_nikel   = w22.number_input("Nikel %", key="w_nikel")
    w_cinko   = w23.number_input("Çinko %", key="w_cinko")
    w_pamuk   = w24.number_input("Pamuk %", key="w_pamuk")

    w25, w26, w27, w28 = st.columns(4)
    w_bugday  = w25.number_input("Buğday %", key="w_bugday")
    w_kakao   = w26.number_input("Kakao %", key="w_kakao")
    w_plastik = w27.number_input("Plastik %", key="w_plastik")
    w_jet_fuel = w28.number_input("Jet A-1 %", key="w_jet_fuel")

    w29, w30, _, _ = st.columns(4)
    w_euro_enf = w29.number_input("Avrupa Enf. (HICP) %", key="w_euro_enf")
    w_abd_enf_new = w30.number_input("ABD CPI Enf. %", key="w_abd_enf")

    toplam = w_mix_oran+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd+w_bakir+w_alum+w_gaz+w_celik+w_scrap_steel+w_scrap_alum+w_propan+w_lityum+w_demir+w_nikel+w_cinko+w_pamuk+w_bugday+w_kakao+w_plastik+w_jet_fuel+w_euro_enf+w_abd_enf_new
    kalan = 100.0 - toplam
    
    if kalan == 0:
        st.success(f"✅ Sepet Tamamlandı: Toplam %100")
    elif kalan > 0:
        st.info(f"ℹ️ Henüz %100 olmadı. Kalan Dağıtılacak Ağırlık: %{kalan:.2f}")
    else:
        st.error(f"⚠️ HATA: Toplam %100'ü geçti! (Mevcut: %{toplam:.2f} -> Fazlalık: %{abs(kalan):.2f})")
    
    etkiler = [
        ("TÜFE+ÜFE Ort.", safe_float(ort_mix_giris), safe_float(w_mix_oran)), 
        ("TÜFE", safe_float(tufe), safe_float(w_tufe)), 
        ("ÜFE", safe_float(ufe), safe_float(w_ufe)), 
        ("H-ÜFE", safe_float(h_ufe), safe_float(w_hufe)),
        ("İşçilik", safe_float(iscilik), safe_float(w_iscilik)), 
        ("USD", safe_float(d_usd), safe_float(w_usd)), 
        ("EUR", safe_float(d_eur), safe_float(w_eur)), 
        ("Altın", safe_float(d_gram), safe_float(w_altin)),
        ("Benzin", safe_float(d_benzin), safe_float(w_benzin)), 
        ("Motorin", safe_float(d_dizel), safe_float(w_dizel)), 
        ("Brent", safe_float(d_brent), safe_float(w_brent)), 
        ("Jet A-1 Yakıt", safe_float(d_jet), safe_float(w_jet_fuel)),
        ("Avrupa Enf. (HICP)", safe_float(euro_enf_val), safe_float(w_euro_enf)),
        ("ABD CPI Enf.", safe_float(abd_cpi_val), safe_float(w_abd_enf_new)),
        ("ABD Enf", safe_float(abd_enf), safe_float(w_abd)),
        ("Bakır", safe_float(d_bakir), safe_float(w_bakir)),
        ("Alüminyum", safe_float(d_alum), safe_float(w_alum)),
        ("Doğal Gaz", safe_float(d_gaz), safe_float(w_gaz)),
        ("Çelik", safe_float(d_celik), safe_float(w_celik)),
        ("Hurda Çelik", safe_float(d_scrap_steel), safe_float(w_scrap_steel)),
        ("Hurda Alüminyum", safe_float(d_scrap_alum), safe_float(w_scrap_alum)),
        ("Propan", safe_float(d_propan), safe_float(w_propan)),
        ("Lityum", safe_float(d_lityum), safe_float(w_lityum)),
        ("Demir", safe_float(d_demir), safe_float(w_demir)),
        ("Nikel", safe_float(d_nikel), safe_float(w_nikel)),
        ("Çinko", safe_float(d_cinko), safe_float(w_cinko)),
        ("Pamuk", safe_float(d_pamuk), safe_float(w_pamuk)),
        ("Buğday", safe_float(d_bugday), safe_float(w_bugday)),
        ("Kakao", safe_float(d_kakao), safe_float(w_kakao)),
        ("Plastik", safe_float(d_plastik), safe_float(w_plastik))
    ]

    # --- SEPETİ IŞILDATAN AKTİF AĞIRLIK BANDEROLÜ ---
    aktif_kalemler = [f"<b>{ad.upper()}:</b> %{agr:.0f}" for ad, deg, agr in etkiler if agr > 0]
    if aktif_kalemler:
        st.markdown(
            f"""
            <div style='background: linear-gradient(90deg, #1E3D59 0%, #27AE60 100%); 
                        color: white; padding: 12px 18px; border-radius: 8px; 
                        box-shadow: 0 4px 12px rgba(39, 174, 96, 0.3); margin: 10px 0px 15px 0px; font-size: 14px;'>
                ✨ <b>AKTİF SEPET KIRILIMI:</b> &nbsp;|&nbsp; {' &nbsp;&bull;&nbsp; '.join(aktif_kalemler)}
            </div>
            """,
            unsafe_allow_html=True
        )

# ============================================================================
    # ⚡ SEPET HESAPLAMALARI VE DATAFRAME OLUŞTURMA
    # ============================================================================
    zam = sum([(e[1] * e[2])/100 for e in etkiler])
    fark = sozlesme_tutari * (zam / 100)
    yeni = sozlesme_tutari + fark

    # DETAY DATAFRAME (Tablodan ve Grafiklerden Önce Tanımlanmalıdır)
    data = {"Kalem": [], "Değişim": [], "Ağırlık": [], "Etki": []}
    for ad, deg, agr in etkiler:
        if agr > 0:
            data["Kalem"].append(f"📌 {ad}")
            data["Değişim"].append(deg)
            data["Ağırlık"].append(agr)
            data["Etki"].append((deg * agr) / 100)

    df = pd.DataFrame(data)

    # ============================================================================
    # ⚖️ TEDARİKCİ KIYASLAMA & ŞIK MALİYET HASSASİYETİ (DARK THEME)
    # ============================================================================
    st.markdown("---")
    st.markdown("##### ⚖️ Tedarikçi Zam Talebi vs. Piyasa Gerçeği Analizi")
    
    c_k1, c_k2, c_k3 = st.columns([2, 2, 3])
    with c_k1:
        tedarikci_zam = st.number_input(
            "Tedarikçi Talep Ettiği Zam (%)", 
            value=float(round(zam * 1.2, 2)) if zam > 0 else 15.0, 
            step=0.5, 
            key=f"ted_zam_{d_key}"
        )
    
    pazarlik_marji = tedarikci_zam - zam
    pazarlik_tl = sozlesme_tutari * (pazarlik_marji / 100)

    with c_k2:
        st.metric("Piyasa Sepet Eskalasyonu", f"%{zam:.2f}")
    with c_k3:
        if pazarlik_marji > 0:
            st.metric("Pazarlık Edilecek Fahiş Marj", f"%{pazarlik_marji:+.2f}", delta=f"-{tr_fmt(pazarlik_tl)} TL Masada İstenmeli", delta_color="inverse")
        else:
            st.metric("Fiyat Avantajı", f"%{abs(pazarlik_marji):.2f}", delta=f"+{tr_fmt(abs(pazarlik_tl))} TL Avantajlı", delta_color="normal")

    # İNCE ZAM KIYASLAMA BARU
    fig_gouging = go.Figure()
    fig_gouging.add_trace(go.Bar(
        y=['Zam'],
        x=[zam],
        name='Piyasa Gerçeği',
        orientation='h',
        marker=dict(color='#27AE60', cornerradius=4),
        text=[f"Piyasa: %{zam:.2f}"],
        textposition='inside',
        insidetextanchor='middle'
    ))
    if pazarlik_marji > 0:
        fig_gouging.add_trace(go.Bar(
            y=['Zam'],
            x=[pazarlik_marji],
            name='Tedarikçi Fazlası',
            orientation='h',
            marker=dict(color='#E74C3C', cornerradius=4),
            text=[f"Fazlalık: %{pazarlik_marji:+.2f}"],
            textposition='inside',
            insidetextanchor='middle'
        ))

    fig_gouging.update_layout(
        barmode='stack',
        height=70,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False)
    )
    st.plotly_chart(fig_gouging, use_container_width=True, config={'displayModeBar': False})

    # MALİYET HASSASİYET MATRİSİ (HEATMAP)
    st.markdown("##### 🌡️ Bütçe Hassasiyet Haritası (Ek Şok Senaryoları)")
    
    top_items = sorted([e for e in etkiler if e[2] > 0], key=lambda x: x[2], reverse=True)[:4]
    
    if top_items:
        shock_rates = [5, 10, 15, 20]
        heatmap_data = []
        y_labels = []
        
        for ad, deg, agr in top_items:
            y_labels.append(f"{ad} (%{agr:.0f})")
            row = []
            for shock in shock_rates:
                ek_yuk = sozlesme_tutari * ((agr / 100) * (shock / 100))
                row.append(ek_yuk)
            heatmap_data.append(row)
            
        fig_heat = go.Figure(data=go.Heatmap(
            z=heatmap_data,
            x=[f"+%{s} Şok" for s in shock_rates],
            y=y_labels,
            colorscale=[[0, '#1E2A38'], [0.5, '#2C3E50'], [1.0, '#C0392B']],
            text=[[f"+{tr_fmt(val)} TL" for val in row] for row in heatmap_data],
            texttemplate="%{text}",
            textfont={"size": 11, "color": "white"},
            showscale=False
        ))
        
        fig_heat.update_layout(
            height=200,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False)
        )
        st.plotly_chart(fig_heat, use_container_width=True, config={'displayModeBar': False})

    # ============================================================================
    # 📊 FİNANSAL ÖZET & DETAY TABLOSU
    # ============================================================================
    st.markdown("---")
    r1, r2, r3 = st.columns(3)
    r1.metric("Toplam Artış", f"%{zam:.2f}")
    r2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
    r3.metric("YENİ TUTAR", f"{tr_fmt(yeni)} TL", delta_color="normal")
    
    st.dataframe(
        df.style.format({
            "Değişim": "%{:+.2f}",
            "Ağırlık": "%{:.0f}",
            "Etki": "%{:+.2f}"
        })
        .background_gradient(subset=["Ağırlık"], cmap="YlGn")
        .highlight_max(subset=["Etki"], color="#D4EFDF"),
        use_container_width=True
    )
    
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if HAS_XLSX:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Detay', index=False)
            st.download_button("📥 Excel Raporu İndir", data=buffer.getvalue(), file_name=f"Hakedis.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            
    with col_dl2:
        if HAS_FPDF:
            jarvis_text = st.session_state.get("last_jarvis_comment", "")
            pdf_bytes = create_executive_pdf_report(sozlesme_tipi, sozlesme_tutari, zam, fark, yeni, etkiler, jarvis_text, start_date, end_date)
            st.download_button("📄 Executive A4 PDF Raporu İndir", data=pdf_bytes, file_name=f"Executive_Eskalasyon_Raporu_{date.today().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)

# ============================================================================
# 🌍 ÇAPRAZ KUR & HEDGING ANALİZ MATRİSİ (DOĞRU YERİ: SEPET HESABI SONRASI)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.header("🌍 Çapraz Kur & Hedging Analiz Matrisi (Cross-Currency Risk)")
    
    # Çapraz Kur Değişimini Hesapla
    fx_change_pct, p_start_fx, p_end_fx = get_cross_currency_rate(contract_curr, cost_curr, start_date, end_date)
    
    # Reel Sözleşme Etkisi (Yukarıda hesaplanan 'zam' değerini kusursuz şekilde kullanır)
    reel_net_impact = (((1 + (zam / 100)) / (1 + (fx_change_pct / 100))) - 1) * 100

    col_fx1, col_fx2, col_fx3 = st.columns(3)
    
    col_fx1.metric(
        label=f"Çapraz Kur Değişimi ({contract_curr}/{cost_curr})",
        value=f"%{fx_change_pct:+.2f}",
        delta=f"Başlangıç: {p_start_fx:.2f} ➔ Güncel: {p_end_fx:.2f}",
        delta_color="off"
    )
    
    col_fx2.metric(
        label=f"Lokal Masraf Eskalasyonu ({cost_curr})",
        value=f"%{zam:.2f}",
        delta="Lokal Sepet Yükü",
        delta_color="off"
    )
    
    delta_color_type = "inverse" if reel_net_impact > 0 else "normal"
    col_fx3.metric(
        label=f"Sözleşme Bazlı Reel Maliyet Yükü ({contract_curr})",
        value=f"%{reel_net_impact:+.2f}",
        delta="Haksız Avantaj / Tedarikçi Erimesi",
        delta_color=delta_color_type
    )

    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)

    # --- PAZARLIK VE MÜZAKERE KOZU BANDEROLÜ ---
    if contract_curr != cost_curr:
        if reel_net_impact < -2.0:
            st.success(
                f"💡 **MÜZAKERE KOZU (Şirket Lehine / İndirim Talebi):**\n\n"
                f"Sözleşme para biriminiz (**{contract_curr}**), sahadaki masraf birimine (**{cost_curr}**) karşı "
                f"lokal enflasyondan **%{abs(reel_net_impact):.2f} daha hızlı değer kazanmıştır.** "
                f"Tedarikçinin {contract_curr} bazında **haksız kur marjı kazandığı** tespit edilmiştir. "
                f"Pazarlık masasında **%{abs(reel_net_impact):.2f} oranında indirim veya sabit kur kilitlemesi (Lock-In)** talep ediniz Sir!"
            )
        elif reel_net_impact > 2.0:
            st.warning(
                f"⚠️ **TEDARİKCİ ERİME RİSKİ (İtiraz / İş Durdurma Uyarısı):**\n\n"
                f"Sahanın lokal maliyet artışı (%{zam:.2f}), sözleşme döviz artışını (%{fx_change_pct:.2f}) aşmıştır. "
                f"Tedarikçi **{contract_curr}** bazında reelde **%{reel_net_impact:.2f} net maliyet erimesi** yaşamaktadır. "
                f"Tedarikçiden ek fiyat revizyonu veya hakediş itirazı gelme olasılığı yüksektir."
            )
        else:
            st.info(
                f"⚖️ **DENGELİ PARİTE DENGESİ:**\n\n"
                f"Sözleşme para birimi (**{contract_curr}**) artışı ile saha maliyet enflasyonu (**{cost_curr}**) tam dengededir. "
                f"Çapraz kur tarafında kayda değer bir arbitraj veya erime riski bulunmamaktadır."
            )
    else:
        st.info("ℹ️ Sözleşme para birimi ile Saha masraf birimi aynı seçildiği için Çapraz Kur arbitrajı hesaplanmamıştır.")

# ============================================================================
# MONTE CARLO RISK & BÜTÇE SIMÜLASYONU (PERİYOT UYUMLU)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_m1, c_m2 = st.columns([3, 1])
    with c_m1: 
        st.header("🎲 Monte Carlo Olasılıklı Bütçe Risk Simülasyonu")
    with c_m2: 
        st.markdown("<div style='text-align:right; font-size:12px; color:gray'>*1.000 Piyasa Şoku Simüle Edilmiştir.</div>", unsafe_allow_html=True)
    
    is_yillik = (sozlesme_periyodu == "Yıllık")
    base_start_val = (yeni / 12) if is_yillik else yeni

    def run_monte_carlo(start_val, base_monthly_rate, vol_rate, months=12, sims=1000):
        np.random.seed(42)
        simulation_matrix = np.zeros((sims, months + 1))
        simulation_matrix[:, 0] = start_val
        
        for t in range(1, months + 1):
            shocks = np.random.normal(loc=base_monthly_rate, scale=vol_rate, size=sims)
            simulation_matrix[:, t] = simulation_matrix[:, t-1] * (1 + shocks / 100)
            
        return simulation_matrix

    # ============================================================================
# MONTE CARLO RISK & BÜTÇE SIMÜLASYONU (PERİYOT UYUMLU)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_m1, c_m2 = st.columns([3, 1])
    with c_m1: 
        st.header("🎲 Monte Carlo Olasılıklı Bütçe Risk Simülasyonu")
    with c_m2: 
        st.markdown("<div style='text-align:right; font-size:12px; color:gray'>*1.000 Piyasa Şoku Simüle Edilmiştir.</div>", unsafe_allow_html=True)
    
    is_yillik = (sozlesme_periyodu == "Yıllık") if 'sozlesme_periyodu' in locals() or 'sozlesme_periyodu' in globals() else False
    base_start_val = (yeni / 12) if is_yillik else yeni

    def run_monte_carlo(start_val, base_monthly_rate, vol_rate, months=12, sims=1000):
        np.random.seed(42)
        simulation_matrix = np.zeros((sims, months + 1))
        simulation_matrix[:, 0] = start_val
        
        for t in range(1, months + 1):
            shocks = np.random.normal(loc=base_monthly_rate, scale=vol_rate, size=sims)
            simulation_matrix[:, t] = simulation_matrix[:, t-1] * (1 + shocks / 100)
            
        return simulation_matrix

    # 🟢 1. Sepet Değiştikçe Kutuyu Zorunlu Yenileyen Dinamik Key
    mc_key = f"mc_base_{d_key}_{round(zam, 2)}"

    # 🟢 2. Sepetteki Riskli Emtialara Göre Dinamik Oynaklık (Volatilite) Hesabı
    emtia_agirligi = safe_float(w_bakir) + safe_float(w_alum) + safe_float(w_celik) + safe_float(w_brent) + safe_float(w_dizel) + safe_float(w_jet_fuel)
    dinamik_volatilite = float(round(1.5 + (emtia_agirligi / 100) * 2.5, 2))

    c_sim1, c_sim2 = st.columns(2)
    with c_sim1:
        base_monthly = st.number_input(
            "Beklenen Aylık Ortalama Artış Trendi (%)", 
            value=float(round((zam/12) if zam > 0 else 2.5, 2)), 
            step=0.1, 
            key=mc_key
        )
    with c_sim2:
        volatility = st.number_input(
            "Piyasa Volatilitesi / Oynaklık Sapması (%)", 
            value=dinamik_volatilite, 
            step=0.1, 
            key=f"mc_vol_{mc_key}", 
            help="Sepetinizdeki emtia ağırlığı arttıkça otomatik olarak riski yükseltir."
        )

    proj_months = 12
    dates_str = [(date.today() + relativedelta(months=i)).strftime("%Y-%m") for i in range(1, proj_months + 1)]
    chart_dates = [datetime.today().strftime("%Y-%m")] + dates_str

    sim_matrix = run_monte_carlo(base_start_val, base_monthly, volatility, proj_months, 1000)
    cum_matrix = np.cumsum(sim_matrix[:, 1:], axis=1)
    
    if is_yillik:
        final_p10 = np.percentile(cum_matrix[:, -1], 10)
        final_p50 = np.percentile(cum_matrix[:, -1], 50)
        final_p95 = np.percentile(cum_matrix[:, -1], 95)
        
        lbl_p10 = "İyimser Yıllık Bütçe (P10)"
        lbl_p50 = "En Olası Yıllık Bütçe (P50 Medyan)"
        lbl_p95 = "Maksimum Riskli Yıllık Bütçe (P95 VaR)"
        
        sub_p10 = f"Aylık Ort: {tr_fmt(final_p10/12)} TL"
        sub_p50 = f"Aylık Ort: {tr_fmt(final_p50/12)} TL"
        sub_p95 = f"Risk Farkı: +{tr_fmt(final_p95 - final_p50)} TL"
    else:
        final_p10 = np.percentile(sim_matrix[:, -1], 10)
        final_p50 = np.percentile(sim_matrix[:, -1], 50)
        final_p95 = np.percentile(sim_matrix[:, -1], 95)
        
        cum_p50 = np.percentile(cum_matrix[:, -1], 50)
        
        lbl_p10 = "İyimser 12. Ay Faturası (P10)"
        lbl_p50 = "En Olası 12. Ay Faturası (P50 Medyan)"
        lbl_p95 = "Maksimum Risk (P95 VaR)"
        
        sub_p10 = "Şanslı Piyasa"
        sub_p50 = f"Kümülatif Yıl Sonu: {tr_fmt(cum_p50)} TL"
        sub_p95 = f"Risk Farkı: +{tr_fmt(final_p95 - final_p50)} TL"

    st.markdown("##### 📊 Olasılıklı Bütçe Risk Karnesi (Percentile Matrix)")
    mc_kpi1, mc_kpi2, mc_kpi3 = st.columns(3)
    mc_kpi1.metric(lbl_p10, f"{tr_fmt(final_p10)} TL", delta=sub_p10, delta_color="normal")
    mc_kpi2.metric(lbl_p50, f"{tr_fmt(final_p50)} TL", delta=sub_p50, delta_color="off")
    mc_kpi3.metric(lbl_p95, f"{tr_fmt(final_p95)} TL", delta=sub_p95, delta_color="inverse")

    tab_fan, tab_dist = st.tabs(["📈 Monte Carlo Yelpaze Grafiği (Fan Chart)", "🔔 Bütçe Risk Dağılımı (Çan Eğrisi)"])

    with tab_fan:
        p10_series = np.percentile(sim_matrix, 10, axis=0)
        p25_series = np.percentile(sim_matrix, 25, axis=0)
        p50_series = np.percentile(sim_matrix, 50, axis=0)
        p75_series = np.percentile(sim_matrix, 75, axis=0)
        p95_series = np.percentile(sim_matrix, 95, axis=0)

        fig_fan = go.Figure()

        fig_fan.add_trace(go.Scatter(
            x=chart_dates + chart_dates[::-1],
            y=np.concatenate([p95_series, p10_series[::-1]]),
            fill='toself',
            fillcolor='rgba(41, 128, 185, 0.15)',
            line=dict(color='rgba(255,255,255,0)'),
            hoverinfo="skip",
            name="%90 Güven Aralığı (P10-P95)"
        ))

        fig_fan.add_trace(go.Scatter(
            x=chart_dates + chart_dates[::-1],
            y=np.concatenate([p75_series, p25_series[::-1]]),
            fill='toself',
            fillcolor='rgba(41, 128, 185, 0.3)',
            line=dict(color='rgba(255,255,255,0)'),
            hoverinfo="skip",
            name="%50 Güven Aralığı (P25-P75)"
        ))

        fig_fan.add_trace(go.Scatter(
            x=chart_dates,
            y=p50_series,
            mode='lines+markers',
            line=dict(color='#1E3D59', width=3),
            name="En Olası Trend (P50 Medyan)",
            hovertemplate="<b>Tarih:</b> %{x}<br><b>Aylık Tutar:</b> %{y:,.2f} TL<extra></extra>"
        ))

        fig_fan.update_layout(
            title="<b>1.000 Simülasyonlu Bütçe Yelpaze Grafiği (Monte Carlo Fan Chart)</b>",
            xaxis_title="Dönem",
            yaxis_title="Aylık Bütçe Yükü (TL)",
            template="plotly_white",
            height=430,
            hovermode="x unified",
            margin=dict(l=40, r=40, t=50, b=40)
        )

        st.plotly_chart(fig_fan, use_container_width=True)

    with tab_dist:
        dist_data = cum_matrix[:, -1] if is_yillik else sim_matrix[:, -1]
        
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Histogram(
            x=dist_data,
            nbinsx=40,
            marker_color='#2980B9',
            opacity=0.75,
            name="Simülasyon Sıklığı"
        ))

        fig_dist.add_vline(x=final_p50, line_width=3, line_dash="dash", line_color="#27AE60", annotation_text=f"Medyan (P50): {tr_fmt(final_p50)} TL")
        fig_dist.add_vline(x=final_p95, line_width=3, line_dash="dot", line_color="#C0392B", annotation_text=f"Maksimum Risk (P95): {tr_fmt(final_p95)} TL")

        dist_title = "<b>Yıllık Toplam Bütçe Dağılım Çan Eğrisi</b>" if is_yillik else "<b>12. Ay Sonu Aylık Fatura Dağılım Çan Eğrisi</b>"

        fig_dist.update_layout(
            title=dist_title,
            xaxis_title="Tahmini Tutarlar (TL)",
            yaxis_title="Senaryo Frekansı (1.000 Üzerinden)",
            template="plotly_white",
            height=430,
            margin=dict(l=40, r=40, t=50, b=40)
        )

        st.plotly_chart(fig_dist, use_container_width=True)

# ============================================================================
# JARVIS AI & YORUM MODÜLÜ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.markdown("### 🤖 Jarvis Finansal Yorumu")
    
    col_j1, col_j2 = st.columns([1, 4])
    risk_durumu = "Yüksek" if zam > 20 else "Düşük"
    with col_j1:
        st.metric("Risk Skoru", risk_durumu, delta="Dikkat" if zam > 20 else "Stabil", delta_color="inverse")

    with col_j2:
        if st.button("🧠 Yapay Zeka ile Analiz Et"):
            if not GEMINI_API_KEY:
                st.error("⚠️ API Anahtarı Bulunamadı! Lütfen Streamlit Secrets ayarlarını kontrol edin.")
            else:
                with st.spinner("Jarvis (Gemini 2.5 Flash) verileri işliyor..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        model_name = "gemini-2.5-flash" 
                        
                        prompt = f"""
                        Sen TAV Havalimanları Holding standartlarında çalışan kıdemli bir Satın Alma Yöneticisi ve Finansal Danışmansın (Jarvis).
                        Aşağıdaki verileri analiz ederek, sözleşmedeki fiyat artışının temel sebeplerini ve riskleri 3-4 cümle ile özetle.
                        
                        Kullanıcıya "Sir" diye hitap et. Profesyonel, net ve kurumsal bir dil kullan.

                        VERİLER:
                        - Sözleşme Tipi: {sozlesme_tipi}
                        - Toplam Fiyat Artışı: %{zam:.2f}
                        - Eski Tutar: {tr_fmt(sozlesme_tutari)} TL
                        - Yeni Tutar: {tr_fmt(yeni)} TL
                        - SEPET TOPLAM KONTROL: %{toplam}
                        
                        PİYASA DEĞİŞİMLERİ:
                        - Dolar (USD): %{piyasa['USDTRY']['degisim']:.2f}
                        - Euro (EUR): %{piyasa['EURTRY']['degisim']:.2f}
                        - Enflasyon (TÜFE): %{val_tufe:.2f}
                        - Avrupa Enf. (HICP): %{euro_enf_val:.2f}
                        - ABD CPI Enf.: %{abd_cpi_val:.2f}
                        - İşçilik: %{iscilik:.2f}
                        - Akaryakıt: %{d_dizel:.2f}
                        - Jet A-1 Yakıt: %{piyasa['JET_FUEL']['degisim']:.2f}
                        - Bakır: %{d_bakir:.2f}
                        - Alüminyum: %{d_alum:.2f}
                        - Çelik: %{d_celik:.2f}

                        YÖNERGE:
                        Hangi kalemin artışa en çok sebep olduğunu tespit et. 
                        Eğer artış piyasa ortalamasının üzerindeyse uyar, altındaysa "başarılı bir hedging" olduğunu belirt.
                        Sonuçları akıcı bir paragraf olarak sun.
                        """
                        
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(prompt)
                        
                        st.session_state["last_jarvis_comment"] = response.text
                        st.success(f"Analiz Tamamlandı (Motor: {model_name})")
                        st.markdown(response.text)
                        
                    except Exception as e:
                        st.error(f"Bir hata oluştu: {str(e)}")
        else:
            st.info("Jarvis şu an beklemede. Güncel verileri yapay zeka ile yorumlamak için butona basınız.")
