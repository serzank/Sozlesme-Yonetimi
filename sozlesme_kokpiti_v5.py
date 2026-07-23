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

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ve GÜVENLİK (SECRETS) ---
try: MY_API_KEY = st.secrets["EVDS_KEY"]
except: MY_API_KEY = None 

try: GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
except: GEMINI_API_KEY = None

try: FMP_KEY = st.secrets["FMP_KEY"]
except: FMP_KEY = None

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

# --- SÖZLEŞME AĞIRLIK MANTIĞI (GENİŞLETİLMİŞ) ---
def get_auto_weights(contract_type):
    w = {
        "mix": 0, "tufe": 0, "ufe": 0, "hufe": 0, "iscilik": 0, "usd": 0, "eur": 0, "altin": 0,
        "benzin": 0, "dizel": 0, "brent": 0, "wti": 0, "abd": 0,
        "bakir": 0, "alum": 0, "gaz": 0, "gumus": 0, "platin": 0, "paladyum": 0,
        "kereste": 0, "bugday": 0, "misir": 0, "kahve": 0, "pamuk": 0
    }
    if contract_type == "Personel Taşımacılık":
        w["dizel"] = 35; w["iscilik"] = 40; w["tufe"] = 25
    elif contract_type == "Yiyecek-İçecek Hizmetleri":
        w["tufe"] = 30; w["iscilik"] = 40; w["hufe"] = 10; w["usd"] = 10; w["bugday"] = 5; w["kahve"] = 5
    elif contract_type == "Yazılım / Lisans":
        w["usd"] = 60; w["eur"] = 20; w["tufe"] = 20
    elif contract_type == "Bilişim Sarf (Donanım)":
        w["usd"] = 80; w["gumus"] = 10; w["bakir"] = 10
    elif contract_type == "Güvenlik Hizmetleri":
        w["iscilik"] = 85; w["tufe"] = 10; w["hufe"] = 5
    elif contract_type == "Serzan'ın Klasiği (TÜFE+ÜFE)":
        w["mix"] = 100
    else: 
        w["tufe"] = 30; w["iscilik"] = 30; w["usd"] = 20; w["eur"] = 10; w["hufe"] = 10
    return w

# --- ASGARİ ÜCRET HESAPLAYICI ---
def get_asgari_ucret_degisim(d_start, d_end):
    maas_tablosu = [
        (date(2026, 1, 1), 28732.0), (date(2025, 7, 1), 22102.0), (date(2025, 1, 1), 22102.0),
        (date(2024, 1, 1), 17002.12), (date(2023, 7, 1), 11402.32), (date(2023, 1, 1), 8506.80),
        (date(2022, 7, 1), 5500.35), (date(2022, 1, 1), 4253.40), (date(2021, 1, 1), 2825.90)
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
@st.cache_data(ttl=600)
def get_google_sheet_data():
    try:
        sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKKPo73sRdzL227kxw9PRvtd6teIyu74v0bw4NCZUCDmJBXgKxZ3AHYmD4zrkalxVgkOSc1lK6p7PF/pub?output=csv"
        df = pd.read_csv(sheet_url)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')
        df['Tarih'] = pd.to_datetime(df['Tarih'], format='%Y-%m-%d', errors='coerce')
        df = df.dropna(subset=['Tarih'])
        df['Donem'] = df['Tarih'].dt.strftime('%Y-%m')
        for col in df.columns:
            if col not in ['Tarih', 'Donem']:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
        return df
    except: return pd.DataFrame()

# -------------------------------------------------------------------------
# FINANCIAL MODELING PREP (FMP) API ENTEGRASYON FONKSİYONU
# -------------------------------------------------------------------------
@st.cache_data(ttl=1800)
def fmp_emtia_al(api_key, symbol, target_start_date):
    ilk_fiyat, son_fiyat = 0.0, 0.0
    if not api_key: return ilk_fiyat, son_fiyat

    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?apikey={api_key}"
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            historical = data.get("historical", [])
            if historical:
                son_fiyat = float(historical[0].get("close", 0.0))
                target_dt = pd.to_datetime(target_start_date)
                valid_items = [{"date": pd.to_datetime(x["date"]), "val": float(x["close"])} 
                               for x in historical if x.get("close") is not None]
                if valid_items:
                    df = pd.DataFrame(valid_items).set_index("date")
                    idx = (df.index - target_dt).abs().argmin()
                    ilk_fiyat = float(df.iloc[idx]["val"])
    except: pass
    return ilk_fiyat, son_fiyat

# --- DİĞER VERİ ÇEKME FONKSİYONLARI ---
@st.cache_data(ttl=3600)
def guncel_akaryakit_cek():
    url = "https://www.doviz.com/akaryakit-fiyatlari/istanbul-avrupa"
    headers = {'User-Agent': 'Mozilla/5.0'}
    fiyatlar = {"benzin": 0.0, "motorin": 0.0}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find('table')
            if table:
                rows = table.find('tbody').find_all('tr')
                if rows:
                    cols = rows[0].find_all('td')
                    if len(cols) >= 3:
                        fiyatlar["benzin"] = float(cols[1].get_text().replace('₺', '').strip().replace(',', '.'))
                        fiyatlar["motorin"] = float(cols[2].get_text().replace('₺', '').strip().replace(',', '.'))
    except: pass
    return fiyatlar

@st.cache_data(ttl=300)
def canli_piyasa_cek():
    base_url = "https://bigpara.hurriyet.com.tr"
    targets = { "USD": "/doviz/dolar/", "EUR": "/doviz/euro/", "ALTIN": "/altin/gram-altin-fiyati/" }
    headers = {'User-Agent': 'Mozilla/5.0'}
    sonuclar = {"USD": 0.0, "EUR": 0.0, "ALTIN": 0.0}
    for key, slug in targets.items():
        try:
            url = base_url + slug
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                box = soup.find("span", {"class": "value up"}) 
                if not box: box = soup.find("span", {"class": "value down"})
                if not box: box = soup.find("span", {"class": "value"})
                if box: sonuclar[key] = float(box.get_text().strip().replace(".", "").replace(",", "."))
        except: pass
    return sonuclar

@st.cache_data(ttl=3600)
def get_tcmb_data(api_key, start_date, end_date):
    res = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Yok"}
    if not api_key: return res
    try:
        evds_service = evdsAPI(api_key)
        s_date = start_date - relativedelta(months=2)
        e_date = end_date + relativedelta(months=1)
        start_q = s_date.replace(day=1).strftime("%d-%m-%Y")
        next_month = e_date + relativedelta(months=1)
        last_day_date = next_month.replace(day=1) - timedelta(days=1)
        end_q = last_day_date.strftime("%d-%m-%Y")

        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1"]
        raw_df = evds_service.get_data(series, startdate=start_q, enddate=end_q)
        if raw_df is None or raw_df.empty: return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m', errors='coerce')
        if raw_df['Tarih_Dt'].isna().all(): raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], errors='coerce')
        raw_df = raw_df.dropna(subset=['Tarih_Dt']).copy()
        
        data_cols = [c for c in raw_df.columns if c.startswith('TP')]
        for c in data_cols: raw_df[c] = pd.to_numeric(raw_df[c], errors='coerce')
        if data_cols:
            raw_df[data_cols] = raw_df[data_cols].ffill()
            raw_df = raw_df.dropna(subset=data_cols, how='all')
            
        p_start, p_end = pd.Period(start_date, freq='M'), pd.Period(end_date, freq='M')
        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        if row_start.empty: row_start = raw_df[raw_df['Tarih_Dt'] >= pd.to_datetime(start_date.replace(day=1))].head(1)
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        if row_end.empty: row_end = raw_df.tail(1)

        def get_val(row, codes):
            if row.empty: return 0.0
            for c in codes:
                c_clean = c.replace(".", "_") 
                if c in row.columns and pd.notna(row[c].values[0]): return float(row[c].values[0])
                if c_clean in row.columns and pd.notna(row[c_clean].values[0]): return float(row[c_clean].values[0])
            return 0.0
            
        t_start, t_end = get_val(row_start, ["TP.FG.J0"]), get_val(row_end, ["TP.FG.J0"])
        u_start, u_end = get_val(row_start, ["TP.TUFE1YI.T1"]), get_val(row_end, ["TP.TUFE1YI.T1"])
        h_start, h_end = get_val(row_start, ["TP.HKFE01.I1"]), get_val(row_end, ["TP.HKFE01.I1"])
        
        calc = lambda n, o: ((n - o) / o * 100) if o > 0 else 0.0
        res.update({ "TUFE": round(calc(t_end, t_start), 2), "UFE": round(calc(u_end, u_start), 2), "HUFE": round(calc(h_end, h_start), 2), "Status": True, "Msg": "EVDS Bağlantısı Başarılı" })
    except: pass
    return res

@st.cache_data(ttl=3600)
def get_evds_gold_history(api_key, d_start):
    try:
        evds = evdsAPI(api_key)
        df = evds.get_data(["TP.MK.KUL.YTL"], startdate=(d_start - timedelta(days=7)).strftime("%d-%m-%Y"), enddate=d_start.strftime("%d-%m-%Y"))
        if df is not None and not df.empty:
             col = [c for c in df.columns if "TP" in c][0]
             s = pd.to_numeric(df[col], errors='coerce').dropna()
             if not s.empty: return float(s.iloc[-1])
    except: pass
    return 0.0

@st.cache_data(ttl=3600)
def get_evds_fuel_history(api_key, d_start):
    res = {"benzin": 0.0, "motorin": 0.0}
    if not api_key: return res
    try:
        evds = evdsAPI(api_key)
        df = evds.get_data(["TP.AK.U95", "TP.AK.MTR"], startdate=(d_start - timedelta(days=30)).strftime("%d-%m-%Y"), enddate=d_start.strftime("%d-%m-%Y"))
        if df is not None and not df.empty:
            for k, code in [("benzin", "U95"), ("motorin", "MTR")]:
                cols = [c for c in df.columns if code in c]
                if cols:
                    s = pd.to_numeric(df[cols[0]], errors='coerce').dropna()
                    if not s.empty: res[k] = float(s.iloc[-1])
    except: pass
    return res

# ============================================================================
# SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown(render_svg_logo(), unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)
    
    st.info("ℹ️ Merhaba, finansal düğümlerin çözüldüğü yerdesiniz.")
    if FMP_KEY:
        st.success("✅ FMP API (Genişletilmiş Emtia Modülü Aktif)")
    else:
        st.caption("ℹ️ Secrets'a 'FMP_KEY' ekleyerek emtiaları borsa verileriyle bağlayabilirsiniz.")
    st.markdown("---")
    
    sozlesme_tipi = st.selectbox(
        "📄 Sözleşme Türü",
        ["Serzan'ın Klasiği (TÜFE+ÜFE)", "Manuel Giriş", "Personel Taşımacılık", "Yiyecek-İçecek Hizmetleri", "Yazılım / Lisans", "Bilişim Sarf (Donanım)", "Güvenlik Hizmetleri"]
    )
    
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    sozlesme_tutari = safe_float(tutar_giris.replace(".", "").replace(",", "."))
    auto_weights = get_auto_weights(sozlesme_tipi)

# ============================================================================
# ANA EKRAN - ÜST KISIM
# ============================================================================
if 'ss_start' not in st.session_state: st.session_state.ss_start = date.today() - relativedelta(years=1)
if 'ss_end' not in st.session_state: st.session_state.ss_end = date.today()

def set_quick_date(months): st.session_state.ss_start = st.session_state.ss_end - relativedelta(months=months)
def set_ytd_date(): st.session_state.ss_start = date(st.session_state.ss_end.year, 1, 1)

with st.container(border=True): 
    st.markdown("##### 📅 Tarih Aralığı Seçimi")
    c_date1, c_date2 = st.columns(2)
    start_date = c_date1.date_input("Başlangıç Tarihi", key="ss_start", format="DD.MM.YYYY")
    end_date = c_date2.date_input("Bitiş Tarihi (Güncel)", key="ss_end", format="DD.MM.YYYY")
        
    b1, b2, b3, b4, b5 = st.columns([1, 1, 1, 1.2, 2.5])
    b1.button("3 Ay", on_click=set_quick_date, args=(3,), use_container_width=True)
    b2.button("6 Ay", on_click=set_quick_date, args=(6,), use_container_width=True)
    b3.button("1 Yıl", on_click=set_quick_date, args=(12,), use_container_width=True)
    b4.button("Sene Başı", on_click=set_ytd_date, use_container_width=True)
    b5.markdown(f"<div style='padding-top:10px; font-size:12px; color:gray'>*Seçili Bitiş Tarihine göre hesaplar.</div>", unsafe_allow_html=True)

if start_date >= end_date: st.error("Hata: Başlangıç < Bitiş olmalı!")
d_key = f"{start_date}_{end_date}"

with st.spinner("PNX Veritabanlarına Bağlanıyor..."):
    tcmb = get_tcmb_data(MY_API_KEY, start_date, end_date)
    yakit_guncel = guncel_akaryakit_cek()
    canli_veri = canli_piyasa_cek()
    evds_gold_ilk = get_evds_gold_history(MY_API_KEY, start_date)
    evds_fuel_ilk = get_evds_fuel_history(MY_API_KEY, start_date)
    df_hufe = get_google_sheet_data()

# ============================================================================
# PİYASA VERİSİ İŞLEME (FMP API + DİNAMİK HYBRID MOTOR)
# ============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def piyasa_verisi_al_tekli(d_start, d_end, live_data, evds_gold_start, evds_key, fmp_key):
    symbol_map = [
        ("USDTRY", "TRY=X"), ("EURTRY", "EURTRY=X"), ("EURUSD", "EURUSD=X"), 
        ("ONS_ALTIN", "GC=F"), ("ABD_TAHVIL", "^TNX")
    ]
    data_dict = {}
    target_start = pd.Timestamp(d_start).replace(hour=0, minute=0, second=0)

    # 1. DÖVİZ VE PARİTELER
    for key, symbol in symbol_map:
        ilk, son = 0.0, 0.0
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2y"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
            if res.status_code == 200:
                data = res.json()
                result = data.get('chart', {}).get('result', [])
                if result:
                    ts = result[0].get('timestamp', [])
                    qs = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                    vd = [(pd.to_datetime(t, unit='s'), c) for t, c in zip(ts, qs) if c is not None]
                    if vd:
                        df = pd.DataFrame(vd, columns=['Date', 'Close']).set_index('Date')
                        if not df.empty:
                            idx = (df.index - target_start).abs().argmin()
                            ilk, son = float(df.iloc[idx]['Close']), float(df.iloc[-1]['Close'])
        except: pass

        if ilk == 0 and evds_key and (key in ["USDTRY", "EURTRY"]):
            try:
                evds_service = evdsAPI(evds_key)
                tcmb_code = "TP.DK.USD.A.YTL" if key == "USDTRY" else "TP.DK.EUR.A.YTL"
                evds_df = evds_service.get_data([tcmb_code], startdate=(d_start - timedelta(days=10)).strftime("%d-%m-%Y"), enddate=d_start.strftime("%d-%m-%Y"))
                if evds_df is not None and not evds_df.empty:
                    ilk = float(pd.to_numeric(evds_df[tcmb_code.replace(".", "_")], errors='coerce').dropna().iloc[-1])
            except: pass

        if key == "USDTRY" and live_data.get("USD", 0) > 0: son = live_data["USD"]
        elif key == "EURTRY" and live_data.get("EUR", 0) > 0: son = live_data["EUR"]

        data_dict[key] = {"ilk": ilk, "son": son, "degisim": ((son - ilk) / ilk * 100) if ilk > 0 else 0.0}

    # 2. FINANCIAL MODELING PREP (FMP) GENİŞLETİLMİŞ EMTİA DÜZENİ
    emtialar = [
        "BRENT_PETROL", "WTI_PETROL", "DOGALGAZ", 
        "BAKIR", "ALUMINYUM", "GUMUS", "PLATIN", "PALADYUM",
        "KERESTE", "BUGDAY", "MISIR", "KAHVE", "PAMUK"
    ]
    for e in emtialar:
        data_dict[e] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}

    if fmp_key:
        fmp_map = [
            ("BRENT_PETROL", "BZUSD"), ("WTI_PETROL", "CLUSD"), ("DOGALGAZ", "NGUSD"),
            ("BAKIR", "HGUSD"), ("ALUMINYUM", "ALIUSD"), ("GUMUS", "SIUSD"), 
            ("PLATIN", "PLUSD"), ("PALADYUM", "PAUSD"),
            ("KERESTE", "LBSUSD"), ("BUGDAY", "ZWUSD"), ("MISIR", "ZCUSD"), 
            ("KAHVE", "KCUSD"), ("PAMUK", "CTUSD")
        ]
        for key, fmp_sym in fmp_map:
            f_ilk, f_son = fmp_emtia_al(fmp_key, fmp_sym, d_start)
            if f_son > 0:
                data_dict[key]["son"] = f_son
                if f_ilk > 0:
                    data_dict[key]["ilk"] = f_ilk
                    data_dict[key]["degisim"] = ((f_son - f_ilk) / f_ilk * 100)

    # --- PARİTE VE GRAM ALTIN KORUMALARI ---
    if data_dict["EURUSD"]["ilk"] == 0 and data_dict["USDTRY"]["ilk"] > 0 and data_dict["EURTRY"]["ilk"] > 0:
        data_dict["EURUSD"]["ilk"] = data_dict["EURTRY"]["ilk"] / data_dict["USDTRY"]["ilk"]
            
    if data_dict["EURUSD"]["son"] == 0 or live_data.get("USD", 0) > 0:
        u_son = data_dict["USDTRY"]["son"] if data_dict["USDTRY"]["son"] > 0 else live_data.get("USD", 1)
        e_son = data_dict["EURTRY"]["son"] if data_dict["EURTRY"]["son"] > 0 else live_data.get("EUR", 1)
        data_dict["EURUSD"]["son"] = e_son / u_son
    
    p_ilk, p_son = data_dict["EURUSD"]["ilk"], data_dict["EURUSD"]["son"]
    data_dict["EURUSD"]["degisim"] = ((p_son - p_ilk) / p_ilk * 100) if p_ilk > 0 else 0.0

    gold_ilk = evds_gold_start
    if gold_ilk <= 0 and data_dict.get("ONS_ALTIN", {}).get("ilk", 0) > 0 and data_dict.get("USDTRY", {}).get("ilk", 0) > 0:
        gold_ilk = (data_dict["ONS_ALTIN"]["ilk"] / 31.1035) * data_dict["USDTRY"]["ilk"]

    gold_son = live_data.get("ALTIN", 0)
    if gold_son <= 0 and data_dict.get("ONS_ALTIN", {}).get("son", 0) > 0 and data_dict.get("USDTRY", {}).get("son", 0) > 0:
        gold_son = (data_dict["ONS_ALTIN"]["son"] / 31.1035) * data_dict["USDTRY"]["son"]

    data_dict["GRAM_ALTIN_TL"] = {"ilk": gold_ilk, "son": gold_son, "degisim": ((gold_son - gold_ilk) / gold_ilk * 100) if gold_ilk > 0 else 0.0}

    return data_dict

piyasa = piyasa_verisi_al_tekli(start_date, end_date, canli_veri, evds_gold_ilk, MY_API_KEY, FMP_KEY)

# ============================================================================
# GÖSTERGE PANELİ (DASHBOARD)
# ============================================================================
st.title("💠Procurement Node | Financial Datum")

with st.container(border=True):
    st.subheader("📊 Temel Göstergeler")
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
                st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:baseline;'><span class='big-metric'>{tr_fmt(son)}</span><span class='{renk}'>%{deg:+.2f}</span></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        return deg

    k1, k2, k3, k4 = st.columns(4)
    d_usd = kutu(k1, "USD/TL", "USDTRY", "💵")
    d_eur = kutu(k2, "EUR/TL", "EURTRY", "💶")
    d_gram = kutu(k3, "Gram Altın", "GRAM_ALTIN_TL", "🥇")
    d_parite = kutu(k4, "EUR/USD", "EURUSD", "⚖️")

    def emtia_karti(col, baslik, key, def_ilk, def_son):
        val = piyasa.get(key, {"ilk": 0.0, "son": 0.0, "degisim": 0.0})
        ilk = safe_float(val["ilk"]) if safe_float(val["ilk"]) > 0 else def_ilk
        son = safe_float(val["son"]) if safe_float(val["son"]) > 0 else def_son
        with col:
            st.markdown(f"<div class='kutu-enerji'><b>{baslik}</b>", unsafe_allow_html=True)
            st.markdown("<label style='font-size:13px;'>Geçmiş Fiyat <span class='badge-est'>Düzenle</span></label>", unsafe_allow_html=True)
            e_input = st.number_input("eski", value=ilk, format="%.2f", key=f"e_{key}_{d_key}", label_visibility="collapsed")
            badge_txt = "FMP LİVE" if (FMP_KEY and val["son"] > 0) else "DÜZENLE"
            st.markdown(f"<label style='font-size:13px;'>Güncel Fiyat <span class='badge-live'>{badge_txt}</span></label>", unsafe_allow_html=True)
            y_input = st.number_input("yeni", value=son, format="%.2f", key=f"y_{key}_{d_key}", label_visibility="collapsed")
            deg = ((y_input - e_input) / e_input * 100) if e_input > 0 else 0.0
            st.markdown(f"<div style='text-align:right;'><span class='{'pozitif' if deg >= 0 else 'negatif'}'>%{deg:+.2f}</span></div></div>", unsafe_allow_html=True)
        return deg

    # --- KAPSAMLI EMTİA GÖSTERİMİ ---
    st.markdown("### 🛢️ Enerji & Akaryakıt")
    e1, e2, e3 = st.columns(3)
    d_brent = emtia_karti(e1, "🛢️ Brent Petrol ($/Bbl)", "BRENT_PETROL", 78.0, 82.0)
    d_wti = emtia_karti(e2, "🛢️ WTI Petrol ($/Bbl)", "WTI_PETROL", 75.0, 79.0)
    d_gaz = emtia_karti(e3, "🔥 Doğal Gaz ($/MMBtu)", "DOGALGAZ", 2.10, 2.45)

    a1, a2 = st.columns(2)
    benzin_yeni_val = yakit_guncel.get("benzin", 44.0)
    motorin_yeni_val = yakit_guncel.get("motorin", 45.0)
    is_proxy = False
    if evds_fuel_ilk["benzin"] > 0:
        benzin_eski_val = evds_fuel_ilk["benzin"]
        motorin_eski_val = evds_fuel_ilk["motorin"]
    else:
        is_proxy = True
        usd_ilk, usd_son = piyasa["USDTRY"]["ilk"], piyasa["USDTRY"]["son"]
        ratio = usd_ilk / usd_son if usd_son > 0 and usd_ilk > 0 else 1.0
        benzin_eski_val, motorin_eski_val = round(benzin_yeni_val * ratio, 2), round(motorin_yeni_val * ratio, 2)

    with a1:
        st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b>", unsafe_allow_html=True)
        st.markdown(f"<label style='font-size:13px;'>{'Eski (TL) ✅ TCMB' if not is_proxy else 'Eski (TL) ⚠️ Tahmin'}</label>", unsafe_allow_html=True)
        b_eski = st.number_input("bo", value=benzin_eski_val, key=f"bo_{d_key}", label_visibility="collapsed")
        st.markdown("<label style='font-size:13px;'>Yeni (TL)</label>", unsafe_allow_html=True)
        b_yeni = st.number_input("bn", value=benzin_yeni_val, key=f"bn_{d_key}", label_visibility="collapsed")
        d_benzin = ((b_yeni-b_eski)/b_eski)*100 if b_eski > 0 else 0
        st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

    with a2:
        st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b>", unsafe_allow_html=True)
        st.markdown(f"<label style='font-size:13px;'>{'Eski (TL) ✅ TCMB' if not is_proxy else 'Eski (TL) ⚠️ Tahmin'}</label>", unsafe_allow_html=True)
        m_eski = st.number_input("mo", value=motorin_eski_val, key=f"mo_{d_key}", label_visibility="collapsed")
        st.markdown("<label style='font-size:13px;'>Yeni (TL)</label>", unsafe_allow_html=True)
        m_yeni = st.number_input("mn", value=motorin_yeni_val, key=f"mn_{d_key}", label_visibility="collapsed")
        d_dizel = ((m_yeni-m_eski)/m_eski)*100 if m_eski > 0 else 0
        st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)


    st.markdown("### 🏗️ Endüstriyel & Değerli Metaller")
    m1, m2, m3 = st.columns(3)
    d_bakir = emtia_karti(m1, "🔌 Bakır ($/lb)", "BAKIR", 4.10, 4.35)
    d_alum  = emtia_karti(m2, "🏗️ Alüminyum ($/Ton)", "ALUMINYUM", 2380.0, 2450.0)
    d_gumus = emtia_karti(m3, "🪙 Gümüş ($/oz)", "GUMUS", 28.50, 31.20)
    
    m4, m5, m6 = st.columns(3)
    d_platin = emtia_karti(m4, "💍 Platin ($/oz)", "PLATIN", 980.0, 1020.0)
    d_paladyum = emtia_karti(m5, "🔋 Paladyum ($/oz)", "PALADYUM", 950.0, 990.0)
    kutu(m6, "ABD 10Y Tahvil", "ABD_TAHVIL", "🇺🇸")


    st.markdown("### 🌾 Tarım & Soft Emtialar")
    t1, t2, t3 = st.columns(3)
    d_kereste = emtia_karti(t1, "🪵 Kereste ($/1000bd ft)", "KERESTE", 520.0, 560.0)
    d_bugday  = emtia_karti(t2, "🍞 Buğday ($/Bu)", "BUGDAY", 610.0, 580.0)
    d_misir   = emtia_karti(t3, "🌽 Mısır ($/Bu)", "MISIR", 450.0, 430.0)

    t4, t5, t6 = st.columns(3)
    d_kahve = emtia_karti(t4, "☕ Kahve ($/lb)", "KAHVE", 210.0, 235.0)
    d_pamuk = emtia_karti(t5, "👕 Pamuk ($/lb)", "PAMUK", 75.0, 72.0)
    st.markdown("")

# ============================================================================
# PNX DÖVİZ ÇEVRİM MATRİSİ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.subheader("💱 PNX Value Matrix: Alım Gücü Analizi")
    u_son, e_son = piyasa["USDTRY"]["son"] or 1.0, piyasa["EURTRY"]["son"] or 1.0
    u_ilk, e_ilk = piyasa["USDTRY"]["ilk"] or u_son, piyasa["EURTRY"]["ilk"] or e_son
    
    tutar_usd_baslangic, tutar_usd_guncel = sozlesme_tutari / u_ilk, sozlesme_tutari / u_son
    tutar_eur_baslangic, tutar_eur_guncel = sozlesme_tutari / e_ilk, sozlesme_tutari / e_son

    c_usd, c_eur = st.columns(2)
    with c_usd:
        st.markdown(f"**💵 USD Bazlı Değerleme**")
        col_u1, col_u2, col_u3 = st.columns(3)
        col_u1.metric("Başlangıç ($)", tr_fmt(tutar_usd_baslangic))
        col_u2.metric("Güncel ($)", tr_fmt(tutar_usd_guncel))
        col_u3.metric("Erime ($)", tr_fmt(tutar_usd_guncel - tutar_usd_baslangic))
    with c_eur:
        st.markdown(f"**💶 EUR Bazlı Değerleme**")
        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("Başlangıç (€)", tr_fmt(tutar_eur_baslangic))
        col_e2.metric("Güncel (€)", tr_fmt(tutar_eur_guncel))
        col_e3.metric("Erime (€)", tr_fmt(tutar_eur_guncel - tutar_eur_baslangic))

# ============================================================================
# HESAPLAMA MOTORU & SEPET
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_header, c_link = st.columns([3, 1])
    with c_header: st.subheader("⚡ Enflasyon & Sepet Hesabı")
    with c_link: st.link_button("🔗 Manuel Hesaplama Sitesi", "https://tufehesaplama-serzan.streamlit.app/")

    if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
    else: st.warning(f"⚠️ {tcmb['Msg']}")

    tum_sektorler = [col for col in df_hufe.columns if col not in ['Tarih', 'Donem']] if not df_hufe.empty else ["Veri Yüklenemedi"]
    preselect_idx, search_keyword = 0, ""
    if sozlesme_tipi == "Güvenlik Hizmetleri": search_keyword = "Güvenlik"
    elif sozlesme_tipi == "Personel Taşımacılık": search_keyword = "Kara"
    elif sozlesme_tipi == "Yiyecek-İçecek Hizmetleri": search_keyword = "Yiyecek"
    elif sozlesme_tipi == "Yazılım / Lisans": search_keyword = "Bilgi"
    
    if search_keyword:
        for i, s in enumerate(tum_sektorler):
            if search_keyword in s: preselect_idx = i; break

    c_search, c_select, c_manuel = st.columns([2, 3, 1])
    with c_search: filter_text = st.text_input("🔍 Sektör Ara", value=search_keyword)
    filtered_list = [s for s in tum_sektorler if filter_text.lower() in s.lower()] if filter_text else tum_sektorler
    
    with c_select: selected_sector = st.selectbox("📋 Sektör", filtered_list, index=0 if tum_sektorler[preselect_idx] not in filtered_list else filtered_list.index(tum_sektorler[preselect_idx]), label_visibility="collapsed")
    with c_manuel: st.link_button("🔗 TÜİK", "https://data.tuik.gov.tr/Kategori/GetKategori?p=Enflasyon-ve-Fiyat-106")

    val_hufe_final = 0.0
    debug_sheet = st.expander(f"🕵️ H-ÜFE Hesaplama Detayı: {selected_sector}", expanded=False)

    if not df_hufe.empty and selected_sector:
        try:
            row_s = df_hufe.loc[(df_hufe['Tarih'] - pd.to_datetime(start_date)).abs().idxmin()]
            row_e = df_hufe.loc[(df_hufe['Tarih'] - pd.to_datetime(end_date)).abs().idxmin()]
            v1, v2 = safe_float(row_s[selected_sector]), safe_float(row_e[selected_sector])
            debug_sheet.write(f"**Başlangıç:** {row_s['Tarih'].strftime('%d.%m.%Y')} (Değer: {v1}) | **Bitiş:** {row_e['Tarih'].strftime('%d.%m.%Y')} (Değer: {v2})")
            if v1 > 0: 
                val_hufe_final = ((v2 - v1) / v1) * 100
                debug_sheet.success(f"Değişim: %{val_hufe_final:.2f}")
        except Exception as e: debug_sheet.error(f"Hata: {str(e)}")

    val_tufe, val_ufe = safe_float(tcmb["TUFE"]), safe_float(tcmb["UFE"])
    val_iscilik, asgari_eski, asgari_yeni = get_asgari_ucret_degisim(start_date, end_date)

    ec1, ec2, ec_mix, ec3, ec4, ec5 = st.columns(6)
    tufe = ec1.number_input("TÜFE %", value=val_tufe, key=f"t_{d_key}")
    ufe = ec2.number_input("ÜFE %", value=val_ufe, key=f"u_{d_key}")
    ort_mix_giris = ec_mix.number_input("Ort(TÜFE+ÜFE)", value=((val_tufe+val_ufe)/2), key=f"mix_{d_key}")
    h_ufe = ec3.number_input("H-ÜFE %", value=val_hufe_final, key=f"h_{d_key}")
    iscilik = ec4.number_input("İşçilik %", value=val_iscilik, key=f"i_{d_key}")
    abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")

    st.markdown("---")
    st.markdown("#### ⚖️ Kapsamlı Sepet Ağırlıkları Matrisi")
    
    # Ağırlık Inputları (4 Sütunlu Grid)
    aw1, aw2, aw3, aw4 = st.columns(4)
    w_mix_oran = aw1.number_input("TÜFE+ÜFE Ort. %", value=auto_weights.get("mix", 0))
    w_tufe = aw2.number_input("Saf TÜFE %", value=auto_weights.get("tufe", 0))
    w_ufe = aw3.number_input("Saf ÜFE %", value=auto_weights.get("ufe", 0))
    w_hufe = aw4.number_input("H-ÜFE %", value=auto_weights.get("hufe", 0))
    
    aw5, aw6, aw7, aw8 = st.columns(4)
    w_iscilik = aw5.number_input("İşçilik %", value=auto_weights.get("iscilik", 0))
    w_usd = aw6.number_input("USD %", value=auto_weights.get("usd", 0))
    w_eur = aw7.number_input("EUR %", value=auto_weights.get("eur", 0))
    w_altin = aw8.number_input("Altın %", value=auto_weights.get("altin", 0))
    
    aw9, aw10, aw11, aw12 = st.columns(4)
    w_benzin = aw9.number_input("Benzin %", value=auto_weights.get("benzin", 0))
    w_dizel = aw10.number_input("Motorin %", value=auto_weights.get("dizel", 0))
    w_brent = aw11.number_input("Brent %", value=auto_weights.get("brent", 0))
    w_wti = aw12.number_input("WTI Petrol %", value=auto_weights.get("wti", 0))
    
    aw13, aw14, aw15, aw16 = st.columns(4)
    w_bakir = aw13.number_input("Bakır %", value=auto_weights.get("bakir", 0))
    w_alum  = aw14.number_input("Alüminyum %", value=auto_weights.get("alum", 0))
    w_gumus = aw15.number_input("Gümüş %", value=auto_weights.get("gumus", 0))
    w_platin= aw16.number_input("Platin %", value=auto_weights.get("platin", 0))
    
    aw17, aw18, aw19, aw20 = st.columns(4)
    w_paladyum = aw17.number_input("Paladyum %", value=auto_weights.get("paladyum", 0))
    w_gaz   = aw18.number_input("Doğal Gaz %", value=auto_weights.get("gaz", 0))
    w_kereste = aw19.number_input("Kereste %", value=auto_weights.get("kereste", 0))
    w_bugday = aw20.number_input("Buğday %", value=auto_weights.get("bugday", 0))
    
    aw21, aw22, aw23, aw24 = st.columns(4)
    w_misir = aw21.number_input("Mısır %", value=auto_weights.get("misir", 0))
    w_kahve = aw22.number_input("Kahve %", value=auto_weights.get("kahve", 0))
    w_pamuk = aw23.number_input("Pamuk %", value=auto_weights.get("pamuk", 0))
    w_abd = aw24.number_input("ABD Enf. %", value=auto_weights.get("abd", 0))

    toplam = sum([w_mix_oran, w_tufe, w_ufe, w_hufe, w_iscilik, w_usd, w_eur, w_altin, 
                  w_benzin, w_dizel, w_brent, w_wti, w_bakir, w_alum, w_gumus, w_platin, 
                  w_paladyum, w_gaz, w_kereste, w_bugday, w_misir, w_kahve, w_pamuk, w_abd])
                  
    if toplam == 100: st.success("✅ Sepet Tamamlandı: %100")
    else: st.info(f"ℹ️ Toplam Ağırlık: %{toplam:.2f} (Hedef: %100)")

    etkiler = [
        ("TÜFE+ÜFE", ort_mix_giris, w_mix_oran), ("TÜFE", tufe, w_tufe), ("ÜFE", ufe, w_ufe), ("H-ÜFE", h_ufe, w_hufe),
        ("İşçilik", iscilik, w_iscilik), ("USD", d_usd, w_usd), ("EUR", d_eur, w_eur), ("Altın", d_gram, w_altin),
        ("Benzin", d_benzin, w_benzin), ("Motorin", d_dizel, w_dizel), 
        ("Brent", d_brent, w_brent), ("WTI", d_wti, w_wti), 
        ("Bakır", d_bakir, w_bakir), ("Alüminyum", d_alum, w_alum), 
        ("Gümüş", d_gumus, w_gumus), ("Platin", d_platin, w_platin), ("Paladyum", d_paladyum, w_paladyum),
        ("Doğal Gaz", d_gaz, w_gaz), ("Kereste", d_kereste, w_kereste), 
        ("Buğday", d_bugday, w_bugday), ("Mısır", d_misir, w_misir), 
        ("Kahve", d_kahve, w_kahve), ("Pamuk", d_pamuk, w_pamuk), 
        ("ABD Enf", abd_enf, w_abd)
    ]
    
    zam = sum([(e[1] * e[2])/100 for e in etkiler])
    fark = sozlesme_tutari * (zam / 100)
    yeni = sozlesme_tutari + fark
    
    st.markdown("---")
    r1, r2, r3 = st.columns(3)
    r1.metric("Toplam Artış", f"%{zam:.2f}")
    r2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
    r3.metric("YENİ TUTAR", f"{tr_fmt(yeni)} TL")
    
    df = pd.DataFrame([{"Kalem": e[0], "Değişim %": e[1], "Ağırlık %": e[2], "Etki %": (e[1]*e[2])/100} for e in etkiler if e[2] > 0])
    st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
    
    if HAS_XLSX:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: df.to_excel(writer, sheet_name='Detay', index=False)
        st.download_button("📥 Excel Raporu İndir", data=buffer.getvalue(), file_name=f"Hakedis.xlsx", mime="application/vnd.ms-excel")

# ============================================================================
# JARVIS PROJEKSİYONU & GRAFİKLER
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.header("🔮 Jarvis Gelecek Projeksiyonu & Senaryo Analizi")
    proj_months = 12
    dates_str = [(date.today() + relativedelta(months=i)).strftime("%Y-%m") for i in range(1, proj_months + 1)]
    base_monthly_inc = (zam / 12) if zam > 5 else 2.5
    
    sc1, sc2, sc3 = st.columns(3)
    rate_opt = sc1.number_input("İyimser Aylık Artış (%)", value=base_monthly_inc * 0.7, step=0.1)
    rate_base = sc2.number_input("Gerçekçi Aylık Artış (%)", value=base_monthly_inc, step=0.1)
    rate_pes = sc3.number_input("Kötümser Aylık Artış (%)", value=base_monthly_inc * 1.5, step=0.1)

    def calc_proj(val, rate): 
        res, curr = [], val
        for _ in range(proj_months):
            curr = curr * (1 + rate/100)
            res.append(curr)
        return res

    vals_opt, vals_base, vals_pes = calc_proj(yeni, rate_opt), calc_proj(yeni, rate_base), calc_proj(yeni, rate_pes)

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("İyimser Toplam", f"{tr_fmt(sum(vals_opt))} TL")
    kpi2.metric("Gerçekçi Toplam", f"{tr_fmt(sum(vals_base))} TL")
    kpi3.metric("Kötümser Toplam", f"{tr_fmt(sum(vals_pes))} TL")

    tab_line, tab_bar = st.tabs(["📈 Aylık Trend Analizi", "📊 Kümülatif Bütçe Yükü"])
    with tab_line:
        if HAS_MATPLOTLIB:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(dates_str, vals_pes, color='#C0392B', linestyle='--', label='Kötümser')
            ax.plot(dates_str, vals_base, color='#2980B9', linewidth=2, label='Gerçekçi')
            ax.plot(dates_str, vals_opt, color='#27AE60', linestyle='-.', label='İyimser')
            ax.set_title("12 Aylık Fiyat Projeksiyonu")
            ax.legend(); ax.grid(True, alpha=0.3); plt.xticks(rotation=45)
            st.pyplot(fig)
    with tab_bar:
        if HAS_MATPLOTLIB:
            fig2, ax2 = plt.subplots(figsize=(10, 4))
            x = np.arange(len(dates_str))
            ax2.bar(x, np.cumsum(vals_base), color='#5DADE2', label='Gerçekçi Kümülatif')
            ax2.set_title("Yıl Sonu Kümülatif Yük")
            ax2.set_xticks(x); ax2.set_xticklabels(dates_str, rotation=45)
            st.pyplot(fig2)

# ============================================================================
# JARVIS AI MODÜLÜ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.markdown("### 🤖 Jarvis Finansal Yorumu")
    if st.button("🧠 Yapay Zeka ile Analiz Et"):
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # Dinamik olarak ağırlığı olan kalemleri filtreleyip yoruma ekle
                aktif_etkiler = [f"- {e[0]}: Değişim %{e[1]:.2f}, Ağırlık %{e[2]:.2f}" for e in etkiler if e[2] > 0]
                etki_str = "\n".join(aktif_etkiler)
                
                prompt = f"""
                Sen TAV Havalimanları Holding standartlarında çalışan kıdemli bir Satın Alma Yöneticisi ve Finansal Danışmansın (Jarvis). Kullanıcıya 'Sir' de.
                Aşağıdaki genişletilmiş emtia ve piyasa verilerini analiz ederek, sözleşmedeki fiyat artışının (veya düşüşünün) temel sebeplerini ve projeksiyon risklerini 3-4 cümle ile özetle.
                
                VERİLER:
                - Toplam Fiyat Artışı: %{zam:.2f}
                - Eski Tutar: {tr_fmt(sozlesme_tutari)} TL
                - Yeni Tutar: {tr_fmt(yeni)} TL
                
                SEPETİ ETKİLEYEN KALEMLER:
                {etki_str}
                
                YÖNERGE:
                Sepette en çok ağırlığı ve değişimi olan "maliyet sürücülerini" tespit et.
                Değerli metaller, enerji veya tarım emtialarında bir ralli varsa bunu hedging açısından değerlendir.
                """
                st.markdown(model.generate_content(prompt).text)
            except Exception as e: st.error(f"Hata: {str(e)}")
        else: st.error("Gemini API Key bulunamadı.")
