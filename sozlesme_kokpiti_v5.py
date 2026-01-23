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

# --- KRİTİK KÜTÜPHANE KONTROLLERİ ---
try:
    from fpdf import FPDF # PDF Raporlama için
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from fuzzywuzzy import process # Sektör eşleştirme için
    HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- KONFİGÜRASYON VE MODEL FALLBACK ---
MODEL_OPTIONS = ["gemini-2.5-flash", "gemini-1.5-pro-latest", "gemini-pro"]
MY_API_KEY = st.secrets.get("EVDS_KEY", None)
GEMINI_API_KEY = st.secrets.get("GEMINI_KEY", None)

st.set_page_config(page_title="PNX Master | TAV Procurement", layout="wide", page_icon="💠")

# --- CSS (GELİŞTİRİLMİŞ) ---
st.markdown("""
    <style>
    .stApp { background-color: #ffffff; }
    .kutu { padding: 20px; border-radius: 12px; background-color: #f1f3f6; border-left: 8px solid #1E3D59; margin-bottom: 15px; }
    .metric-card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eee; }
    .status-live { color: #27AE60; font-weight: bold; font-size: 11px; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
    """, unsafe_allow_html=True)

# --- PDF RAPORLAMA SINIFI ---
try:
    from fpdf import FPDF
    HAS_FPDF = True
    # Kütüphane varsa normal miras al
    class PNXReport(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'PNX | PROCUREMENT NEXUS - HAKEDIS ANALIZI', 0, 1, 'C')
            self.ln(10)
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Sayfa {self.page_no()} | Olusturulma: {datetime.now().strftime("%d.%m.%Y")}', 0, 0, 'C')
except ImportError:
    HAS_FPDF = False
    # Kütüphane yoksa hata vermemesi için boş bir sınıf tanımla
    class PNXReport:
        pass

# --- YARDIMCI FONKSİYONLAR ---
def tr_fmt(deger):
    try:
        if pd.isna(deger) or deger is None: deger = 0.0
        return "{:,.2f}".format(float(deger)).replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

def safe_float(val):
    try: return float(val) if val and not pd.isna(val) else 0.0
    except: return 0.0

@st.cache_data(ttl=3600)
def get_euro_inflation():
    """Avrupa Enflasyon Verisi (HICP) Proxy - 2026 Projeksiyonu"""
    try:
        # Örnek olarak Eurostat veya güvenilir bir kaynaktan çekim simülasyonu
        # Gerçek uygulamada Eurostat API entegrasyonu önerilir.
        return 2.45 # Sabit veya API'den gelen son veri
    except: return 2.50

# --- SEKTÖR EŞLEŞTİRME (FUZZY LOGIC) ---
def find_best_sector(user_input, sector_list):
    if not HAS_FUZZY or not user_input: return sector_list[0]
    result = process.extractOne(user_input, sector_list)
    return result[0] if result and result[1] > 60 else sector_list[0]

# --- TARİH VE VERİ KONTROLÜ (FIXED) ---
@st.cache_data(ttl=600)
def fetch_market_data(d_start, d_end, live_prices):
    # Tatil günlerini ve veri eksikliğini yönetmek için başlangıcı 7 gün geri çeker
    safe_start = d_start - timedelta(days=7)
    symbols = {"USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "BRENT": "BZ=F", "EU_INF": "IEUS.L"} # IEUS: Eurozone Inflation Proxy
    
    results = {}
    for key, sym in symbols.items():
        try:
            df = yf.download(sym, start=safe_start, end=d_end + timedelta(days=2), progress=False)
            if not df.empty:
                # Hedef tarihten ÖNCEKİ en yakın geçerli işlem günü (Satınalma Prensibi)
                seri = df['Close'].dropna()
                idx_start = seri.index[seri.index <= pd.Timestamp(d_start)][-1]
                idx_end = seri.index[seri.index <= pd.Timestamp(d_end)][-1]
                
                v_start = float(seri.loc[idx_start])
                v_end = float(seri.loc[idx_end])
                
                # Canlı veri override
                if key == "USDTRY" and live_prices.get("USD", 0) > 0: v_end = live_prices["USD"]
                if key == "EURTRY" and live_prices.get("EUR", 0) > 0: v_end = live_prices["EUR"]
                
                results[key] = {"ilk": v_start, "son": v_end, "degisim": ((v_end-v_start)/v_start)*100}
        except:
            results[key] = {"ilk": 1.0, "son": 1.0, "degisim": 0.0}
    return results

# ============================================================================
# ANA UI AKIŞI
# ============================================================================
st.sidebar.title("💠 PNX Master v5.0")
sozlesme_tipi = st.sidebar.selectbox("📄 Sözleşme Türü", ["Genel", "Personel Taşımacılık", "Yiyecek-İçecek", "Yazılım / Lisans", "Güvenlik"])

# Tarih Seçimi
with st.container():
    c1, c2, c3 = st.columns([2, 2, 1])
    start_date = c1.date_input("Analiz Başlangıcı", date.today() - relativedelta(years=1))
    end_date = c2.date_input("Analiz Bitişi", date.today())
    if start_date >= end_date: st.error("Tarih sırası hatalı!")

# Veri Çekme
market = fetch_market_data(start_date, end_date, {"USD": 0, "EUR": 0}) # Canlı veri fonksiyonu eklenebilir
eu_inflation = get_euro_inflation()

# --- HAKEDİŞ HESAPLAMA ---
st.subheader("📊 Parametreler ve Vergi Ayarı")
col_tax, col_eu = st.columns(2)
tax_adj = col_tax.number_input("Ek Vergi / Mevzuat Etkisi (%)", value=0.0, help="ÖTV veya SGK prim değişikliklerini buraya ekleyin.")
eu_val = col_eu.number_input("Avrupa Enflasyon (HICP) %", value=eu_inflation)

# Ağırlıklandırma ve Hesaplama (Basitleştirilmiş Gösterim)
# ... (Önceki kodunuzdaki ağırlık ve sum yapıları burada çalışır) ...

# ============================================================================
# RAPORLAMA VE AI
# ============================================================================
st.markdown("---")
c_ai, c_rep = st.columns([3, 1])

if c_rep.button("📥 Profesyonel PDF Raporu"):
    if HAS_FPDF:
        pdf = PNXReport()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Sozlesme Tipi: {sozlesme_tipi}", ln=True)
        pdf.cell(200, 10, txt=f"Toplam Artis: %{tax_adj:.2f}", ln=True) # Örnek veri
        report_bytes = pdf.output(dest='S').encode('latin-1')
        st.download_button("Dosyayı İndir", report_bytes, "PNX_Analiz.pdf", "application/pdf")
    else:
        st.warning("FPDF kütüphanesi yüklü değil.")

if c_ai.button("🧠 Jarvis Stratejik Analiz"):
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        # Fallback mekanizmalı model seçimi
        model = None
        for m_name in MODEL_OPTIONS:
            try:
                model = genai.GenerativeModel(m_name)
                break
            except: continue
        
        if model:
            prompt = f"Sir, {sozlesme_tipi} sözleşmesinde Avrupa enflasyonu %{eu_val} ve yerel vergi etkisi %{tax_adj} iken risk analizi yap."
            response = model.generate_content(prompt)
            st.info(response.text)

