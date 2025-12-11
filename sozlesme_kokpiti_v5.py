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
try:
    MY_API_KEY = st.secrets["EVDS_KEY"]
except:
    MY_API_KEY = "Uol1kIOQos" 

try:
    GEMINI_API_KEY = st.secrets["GEMINI_KEY"]
except:
    GEMINI_API_KEY = None

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
    <svg width="280" height="70" viewBox="0 0 280 70" xmlns="http://www.w3.org/2000/svg">
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
      <text x="75" y="45" font-family="Verdana" font-weight="900" font-size="32" fill="#1E3D59" letter-spacing="-1">COST NEXUS</text>
      <text x="155" y="32" font-family="Arial" font-size="10" fill="#888" font-weight="bold">Procurement</text>
      <text x="155" y="44" font-family="Arial" font-size="10" fill="#27AE60" font-weight="bold">Vision</text>
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

# --- SÖZLEŞME AĞIRLIK MANTIĞI ---
def get_auto_weights(contract_type):
    w = {
        "mix": 0, "tufe": 0, "ufe": 0, "hufe": 0,
        "iscilik": 0, "usd": 0, "eur": 0, "altin": 0,
        "benzin": 0, "dizel": 0, "brent": 0, "abd": 0
    }
    if contract_type == "Personel Taşımacılık":
        w["dizel"] = 35; w["iscilik"] = 40; w["tufe"] = 25
    elif contract_type == "Yiyecek-İçecek Hizmetleri":
        w["tufe"] = 40; w["iscilik"] = 40; w["hufe"] = 10; w["usd"] = 10
    elif contract_type == "Yazılım / Lisans":
        w["usd"] = 60; w["eur"] = 20; w["tufe"] = 20
    elif contract_type == "Bilişim Sarf (Donanım)":
        w["usd"] = 100
    elif contract_type == "Güvenlik Hizmetleri":
        w["iscilik"] = 85; w["tufe"] = 10; w["hufe"] = 5
    elif contract_type == "Serzan'ın Klasiği (TÜFE+ÜFE)":
        w["mix"] = 100
    else: 
        w["tufe"] = 30; w["iscilik"] = 30; w["usd"] = 20; w["eur"] = 10; w["hufe"] = 10
    return w

# --- VERİ ÇEKME FONKSİYONLARI ---
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
                        raw_benzin = cols[1].get_text().replace('₺', '').strip().replace(',', '.')
                        raw_motorin = cols[2].get_text().replace('₺', '').strip().replace(',', '.')
                        fiyatlar["benzin"] = float(raw_benzin)
                        fiyatlar["motorin"] = float(raw_motorin)
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
                if box:
                    raw = box.get_text().strip().replace(".", "").replace(",", ".")
                    sonuclar[key] = float(raw)
        except: pass
    return sonuclar

@st.cache_data(ttl=3600)
def get_tcmb_data(api_key, start_date, end_date):
    res = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Yok"}
    if not api_key: return res
    try:
        evds_service = evdsAPI(api_key)
        start_q = (start_date - relativedelta(months=2)).strftime("%d-%m-%Y")
        end_q = (end_date + relativedelta(months=1)).strftime("%d-%m-%Y")
        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1"]
        if end_date > date.today(): end_q = date.today().strftime("%d-%m-%Y")

        raw_df = evds_service.get_data(series, startdate=start_q, enddate=end_q)
        if raw_df is None or raw_df.empty:
            res["Msg"] = "API Boş Döndü"
            return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')
        max_date = raw_df['Tarih_Dt'].max()
        if p_end > pd.Period(max_date, freq='M'): p_end = pd.Period(max_date, freq='M')

        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        
        if row_start.empty:
            mask = raw_df['Tarih_Dt'] >= pd.to_datetime(start_date)
            if mask.any(): row_start = raw_df.loc[mask].iloc[[0]]
            else: row_start = raw_df.iloc[[0]]

        if row_end.empty: row_end = raw_df.iloc[[-1]]
        
        def get_val(row, codes):
            for c in codes:
                if c in row.columns and pd.notna(row[c].values[0]): return float(row[c].values[0])
            return 0.0
            
        cols_t = ["TP_FG_J0", "TP.FG.J0"]
        cols_u = ["TP_TUFE1YI_T1", "TP.TUFE1YI.T1"]
        cols_h = ["TP_HKFE01_I1", "TP.HKFE01.I1"]

        t_start, t_end = get_val(row_start, cols_t), get_val(row_end, cols_t)
        u_start, u_end = get_val(row_start, cols_u), get_val(row_end, cols_u)
        h_start, h_end = get_val(row_start, cols_h), get_val(row_end, cols_h)
        
        def calc(n, o):
            if o == 0: return 0.0
            return ((n - o) / o) * 100
            
        res["TUFE"] = round(calc(t_end, t_start), 2)
        res["UFE"] = round(calc(u_end, u_start), 2)
        res["HUFE"] = round(calc(h_end, h_start), 2)
        res["Status"] = True
        res["Msg"] = f"{p_start} ➡️ {p_end}"
    except Exception as e: res["Msg"] = f"Hata: {str(e)}"
    return res

@st.cache_data(ttl=3600)
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

@st.cache_data(ttl=3600)
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
                s_b = pd.to_numeric(df[cols_b[0]], errors='coerce').dropna()
                if not s_b.empty: res["benzin"] = float(s_b.iloc[-1])
            cols_m = [c for c in df.columns if "TP_AK_MTR" in c or "TP.AK.MTR" in c]
            if cols_m:
                s_m = pd.to_numeric(df[cols_m[0]], errors='coerce').dropna()
                if not s_m.empty: res["motorin"] = float(s_m.iloc[-1])
    except: pass
    return res

# ============================================================================
# SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown(render_svg_logo(), unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)
    
    st.info("ℹ️ Merhaba, finansal düğümlerin çözüldüğü yerdesiniz.")
    st.markdown("---")
    
    sozlesme_tipi = st.selectbox(
        "📄 Sözleşme Türü",
        ["Serzan'ın Klasiği (TÜFE+ÜFE)", "Manuel Giriş", "Personel Taşımacılık", "Yiyecek-İçecek Hizmetleri", "Yazılım / Lisans", "Bilişim Sarf (Donanım)", "Güvenlik Hizmetleri"]
    )
    
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    try: sozlesme_tutari = float(tutar_giris.replace(".", "").replace(",", "."))
    except: sozlesme_tutari = 0.0
    
    auto_weights = get_auto_weights(sozlesme_tipi)

# ============================================================================
# ANA EKRAN - ÜST KISIM
# ============================================================================
if 'ss_start' not in st.session_state:
    st.session_state.ss_start = date.today() - relativedelta(years=1)
if 'ss_end' not in st.session_state:
    st.session_state.ss_end = date.today()

def set_quick_date(months):
    st.session_state.ss_start = st.session_state.ss_end - relativedelta(months=months)

with st.container(border=True): 
    st.markdown("##### 📅 Tarih Aralığı Seçimi")
    c_date1, c_date2 = st.columns(2)
    
    with c_date1:
        start_date = st.date_input("Başlangıç Tarihi", key="ss_start", format="DD.MM.YYYY")
    with c_date2:
        end_date = st.date_input("Bitiş Tarihi (Güncel)", key="ss_end", format="DD.MM.YYYY")
        
    b1, b2, b3, b4 = st.columns([1, 1, 1, 3])
    with b1: st.button("3 Ay", on_click=set_quick_date, args=(3,), use_container_width=True)
    with b2: st.button("6 Ay", on_click=set_quick_date, args=(6,), use_container_width=True)
    with b3: st.button("1 Yıl", on_click=set_quick_date, args=(12,), use_container_width=True)
    with b4: st.markdown(f"<div style='padding-top:10px; font-size:12px; color:gray'>*Seçili Bitiş Tarihine göre hesaplar.</div>", unsafe_allow_html=True)

if start_date >= end_date: st.error("Hata: Başlangıç < Bitiş olmalı!")
d_key = f"{start_date}_{end_date}"

# VERİ ÇEKME
with st.spinner("PNX Veritabanlarına Bağlanıyor..."):
    tcmb = get_tcmb_data(MY_API_KEY, start_date, end_date)
    yakit_guncel = guncel_akaryakit_cek()
    canli_veri = canli_piyasa_cek()
    evds_gold_ilk = get_evds_gold_history(MY_API_KEY, start_date)
    evds_fuel_ilk = get_evds_fuel_history(MY_API_KEY, start_date)

# ============================================================================
# PİYASA VERİSİ
# ============================================================================
@st.cache_data(ttl=600)
def piyasa_verisi_al_tekli(d_start, d_end, live_data, evds_gold_start):
    y_end = d_end
    if y_end > date.today(): y_end = date.today()
    symbol_map = [("USDTRY", "TRY=X"), ("EURTRY", "EURTRY=X"), ("EURUSD", "EURUSD=X"), 
                  ("ONS_ALTIN", "GC=F"), ("BRENT_PETROL", "BZ=F"), ("ABD_TAHVIL", "^TNX")]
    data_dict = {}
    for key, symbol in symbol_map:
        ilk, son = 0.0, 0.0
        try:
            df = yf.download(symbol, start=d_start, end=y_end + timedelta(days=1), progress=False)
            if isinstance(df, pd.DataFrame):
                seri = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            else: seri = df 
            seri = seri.dropna()
            if len(seri) > 0: ilk, son = float(seri.iloc[0]), float(seri.iloc[-1])
        except: pass
        
        if key == "USDTRY" and live_data.get("USD", 0) > 0: son = live_data["USD"]
        elif key == "EURTRY" and live_data.get("EUR", 0) > 0: son = live_data["EUR"]
        
        degisim = 0.0
        if ilk > 0: degisim = ((son - ilk) / ilk) * 100
        data_dict[key] = {"ilk": ilk, "son": son, "degisim": degisim}

    gold_ilk = evds_gold_start
    if gold_ilk == 0:
        ons_ilk = data_dict.get("ONS_ALTIN", {}).get("ilk", 0)
        usd_ilk = data_dict.get("USDTRY", {}).get("ilk", 0)
        if ons_ilk > 0 and usd_ilk > 0: gold_ilk = (ons_ilk / 31.1035) * usd_ilk

    gold_son = live_data.get("ALTIN", 0)
    if gold_son == 0:
        ons_son = data_dict.get("ONS_ALTIN", {}).get("son", 0)
        usd_son = data_dict.get("USDTRY", {}).get("son", 0)
        gold_son = (ons_son / 31.1035) * usd_son

    g_deg = 0.0
    if gold_ilk > 0: g_deg = ((gold_son - gold_ilk) / gold_ilk) * 100
    data_dict["GRAM_ALTIN_TL"] = {"ilk": gold_ilk, "son": gold_son, "degisim": g_deg}
    return data_dict

piyasa = piyasa_verisi_al_tekli(start_date, end_date, canli_veri, evds_gold_ilk)

# ============================================================================
# GÖSTERGE PANELİ
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
                ek_bilgi = " (Canlı)" if ("GRAM" in key or "USD" in key or "EUR" in key) and canli_veri.get("USD",0) > 0 else ""
                st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:baseline;'><span class='big-metric'>{tr_fmt(son)}</span><span class='{renk}'>%{deg:+.2f}</span></div>", unsafe_allow_html=True)
                if ek_bilgi: st.markdown(f"<div style='font-size:10px; color:#27AE60; text-align:right;'>{ek_bilgi}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        return deg

    k1, k2, k3, k4 = st.columns(4)
    d_usd = kutu(k1, "USD/TL", "USDTRY", "💵")
    d_eur = kutu(k2, "EUR/TL", "EURTRY", "💶")
    d_gram = kutu(k3, "Gram Altın", "GRAM_ALTIN_TL", "🥇")
    d_parite = kutu(k4, "EUR/USD", "EURUSD", "⚖️")

    st.markdown("### 🛢️ Enerji")
    e1, e2, e3, e4 = st.columns(4)
    d_brent = kutu(e1, "Brent ($)", "BRENT_PETROL", "🛢️")

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

# ============================================================================
# PNX DÖVİZ ÇEVRİM MATRİSİ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.subheader("💱 PNX Value Matrix: Alım Gücü Analizi")
    
    u_ilk = piyasa["USDTRY"]["ilk"] if piyasa["USDTRY"]["ilk"] > 0 else 1.0
    u_son = piyasa["USDTRY"]["son"] if piyasa["USDTRY"]["son"] > 0 else 1.0
    
    e_ilk = piyasa["EURTRY"]["ilk"] if piyasa["EURTRY"]["ilk"] > 0 else 1.0
    e_son = piyasa["EURTRY"]["son"] if piyasa["EURTRY"]["son"] > 0 else 1.0
    
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
        col_u1.metric("Başlangıç ($)", f"{tutar_usd_baslangic:,.0f}")
        col_u2.metric("Güncel ($)", f"{tutar_usd_guncel:,.0f}")
        col_u3.metric("Erime ($)", f"{fark_usd:,.0f}", delta_color="normal")
    
    with c_eur:
        st.markdown(f"**💶 EUR Bazlı Değerleme**")
        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("Başlangıç (€)", f"{tutar_eur_baslangic:,.0f}")
        col_e2.metric("Güncel (€)", f"{tutar_eur_guncel:,.0f}")
        col_e3.metric("Erime (€)", f"{fark_eur:,.0f}", delta_color="normal")
        
    st.markdown(f"<div style='font-size:11px; color:gray; text-align:right'>*Hesaplama: Girilen {tr_fmt(sozlesme_tutari)} TL'nin, başlangıç tarihi ve bugünkü kurlar üzerinden karşılığıdır.</div>", unsafe_allow_html=True)


# ============================================================================
# HESAPLAMA MOTORU (DİNAMİK KONTROL EKLENDİ - v1.1)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_header, c_link = st.columns([3, 1])
    with c_header: st.subheader("⚡ Enflasyon & Sepet Hesabı")
    with c_link: st.link_button("🔗 Manuel Hesaplama Sitesi", "https://tufehesaplama-serzan.streamlit.app/")

    if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
    else: st.warning(f"⚠️ {tcmb['Msg']}")

    val_tufe = safe_float(tcmb["TUFE"])
    val_ufe = safe_float(tcmb["UFE"])
    val_mix = (val_tufe + val_ufe) / 2

    ec1, ec2, ec_mix, ec3, ec4, ec5 = st.columns(6)
    tufe = ec1.number_input("TÜFE %", value=val_tufe, key=f"t_{d_key}")
    ufe = ec2.number_input("ÜFE %", value=val_ufe, key=f"u_{d_key}")
    ort_mix_giris = ec_mix.number_input("Ort(TÜFE+ÜFE)", value=val_mix, key=f"mix_{d_key}")
    h_ufe = ec3.number_input("H-ÜFE %", value=safe_float(tcmb["HUFE"]), key=f"h_{d_key}")
    iscilik = ec4.number_input("İşçilik %", value=0.0, key=f"i_{d_key}")
    abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")

    st.markdown("---")
    st.markdown("#### ⚖️ Sepet Ağırlıkları")

    # --- INPUT BLOKLARI ---
    w1, w2, w3, w4 = st.columns(4)
    w_mix_oran = w1.number_input("TÜFE+ÜFE Ort. %", value=auto_weights["mix"])
    w_tufe = w2.number_input("Saf TÜFE %", value=auto_weights["tufe"])
    w_ufe = w3.number_input("Saf ÜFE %", value=auto_weights["ufe"])
    w_hufe = w4.number_input("H-ÜFE %", value=auto_weights["hufe"])
    
    w5, w6, w7, w8 = st.columns(4)
    w_iscilik = w5.number_input("İşçilik %", value=auto_weights["iscilik"])
    w_usd = w6.number_input("USD %", value=auto_weights["usd"])
    w_eur = w7.number_input("EUR %", value=auto_weights["eur"])
    w_altin = w8.number_input("Altın %", value=auto_weights["altin"])
    
    w9, w10, w11, w12 = st.columns(4)
    w_benzin = w9.number_input("Benzin %", value=auto_weights["benzin"])
    w_dizel = w10.number_input("Motorin %", value=auto_weights["dizel"])
    w_brent = w11.number_input("Brent %", value=auto_weights["brent"])
    w_abd = w12.number_input("ABD Enf. %", value=auto_weights["abd"])

    # --- YENİ DİNAMİK TOPLAM KONTROLÜ ---
    toplam = w_mix_oran+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd
    kalan = 100.0 - toplam
    
    # Görsel Bildirim Çubuğu
    if kalan == 0:
        st.success(f"✅ Sepet Tamamlandı: Toplam %100")
    elif kalan > 0:
        st.info(f"ℹ️ Henüz %100 olmadı. Kalan Dağıtılacak Ağırlık: %{kalan:.2f}")
    else:
        st.error(f"⚠️ HATA: Toplam %100'ü geçti! (Mevcut: %{toplam:.2f} -> Fazlalık: %{abs(kalan):.2f})")
    
    # --- HESAPLAMA DEVAM EDER ---
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
        ("ABD Enf", safe_float(abd_enf), safe_float(w_abd))
    ]
    zam = sum([(e[1] * e[2])/100 for e in etkiler])
    fark = sozlesme_tutari * (zam / 100)
    yeni = sozlesme_tutari + fark
    
    st.markdown("---")
    r1, r2, r3 = st.columns(3)
    r1.metric("Toplam Artış", f"%{zam:.2f}")
    r2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
    r3.metric("YENİ TUTAR", f"{tr_fmt(yeni)} TL", delta_color="normal")
    
    data = {"Kalem": [], "Değişim %": [], "Ağırlık %": [], "Etki %": []}
    for ad, deg, agr in etkiler:
        if agr > 0:
            data["Kalem"].append(ad); data["Değişim %"].append(deg)
            data["Ağırlık %"].append(agr); data["Etki %"].append((deg*agr)/100)
    df = pd.DataFrame(data)
    st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
    
    if HAS_XLSX:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Detay', index=False)
        st.download_button("📥 Excel Raporu İndir", data=buffer.getvalue(), file_name=f"Hakedis.xlsx", mime="application/vnd.ms-excel")

# ============================================================================
# JARVIS PROJEKSİYONU
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.header("🔮 Jarvis Gelecek Projeksiyonu")
    
    proj_months = 12
    proj_dates = [date.today() + relativedelta(months=i) for i in range(1, proj_months + 1)]
    proj_dates_str = [d.strftime("%Y-%m") for d in proj_dates]
    
    aylik_artis_tahmini = zam / 12 if zam > 0 else 2.5 
    if aylik_artis_tahmini < 0: aylik_artis_tahmini = 0.5
    
    sim_tutar = [yeni]
    sim_kur = [piyasa["USDTRY"]["son"]]
    
    for i in range(proj_months - 1):
        sim_tutar.append(sim_tutar[-1] * (1 + aylik_artis_tahmini/100))
        sim_kur.append(sim_kur[-1] * (1 + 0.025)) 
    
    if HAS_MATPLOTLIB:
        fig, ax1 = plt.subplots(figsize=(10, 4))
        ax1.set_xlabel('Gelecek 12 Ay')
        ax1.set_ylabel('Tahmini Sözleşme Tutarı (TL)', color='tab:blue')
        ax1.plot(proj_dates_str, sim_tutar, color='tab:blue', marker='o', linewidth=2, label="Sözleşme Tutarı")
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.set_xticklabels(proj_dates_str, rotation=45)
        ax1.grid(True, alpha=0.3)
        
        ax2 = ax1.twinx()
        ax2.set_ylabel('Tahmini USD Kuru', color='tab:green')
        ax2.plot(proj_dates_str, sim_kur, color='tab:green', linestyle='--', label="USD Trendi")
        ax2.tick_params(axis='y', labelcolor='tab:green')
        plt.title(f"Gelecek Dönem Projeksiyonu")
        fig.tight_layout()
        st.pyplot(fig)
    else:
        st.warning("⚠️ Gelişmiş grafikler için `requirements.txt` dosyasına `matplotlib` ekleyiniz. Şimdilik basitleştirilmiş görünüm aktif.")
        chart_df = pd.DataFrame({"Tarih": proj_dates_str, "Sözleşme Tutarı": sim_tutar, "USD Kuru": sim_kur})
        st.line_chart(chart_df, x="Tarih", y="Sözleşme Tutarı")

# ============================================================================
# JARVIS AI & YORUM MODÜLÜ
# ============================================================================
st.markdown("---")
with st.container(border=True):
    # ============================================================================
# JARVIS AI & YORUM MODÜLÜ (MODEL GÜNCELLENDİ: GEMINI-PRO)
# ============================================================================
st.markdown("---")
with st.container(border=True):

# ============================================================================
# JARVIS AI & YORUM MODÜLÜ (MODEL GÜNCELLENDİ: GEMINI-PRO)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    st.markdown("### 🤖 Jarvis Finansal Yorumu")
    
    col_j1, col_j2 = st.columns([1, 4])
    
    # Risk Skoru Hesabı
    risk_durumu = "Yüksek" if zam > 20 else "Düşük"
    with col_j1:
        st.metric("Risk Skoru", risk_durumu, delta="Dikkat" if zam > 20 else "Stabil", delta_color="inverse")

    with col_j2:
        if st.button("🧠 Yapay Zeka ile Analiz Et"):
            if not GEMINI_API_KEY:
                st.error("⚠️ API Anahtarı Bulunamadı! Lütfen Streamlit Secrets ayarlarını kontrol edin.")
            else:
                with st.spinner("Jarvis piyasa verilerini ve sözleşme yapısını inceliyor..."):
                    try:
                        # Yapay Zekaya Gidecek Veri Seti (Prompt)
                        prompt = f"""
                        Sen TAV Havalimanları Holding standartlarında çalışan kıdemli bir Satın Alma Yöneticisi ve Finansal Danışmansın (Jarvis).
                        Aşağıdaki verileri analiz ederek, sözleşmedeki fiyat artışının temel sebeplerini ve riskleri 3-4 cümle ile özetle.
                        
                        Kullanıcıya "Sir" diye hitap et. Profesyonel, net ve kurumsal bir dil kullan.

                        VERİLER:
                        - Sözleşme Tipi: {sozlesme_tipi}
                        - Toplam Fiyat Artışı: %{zam:.2f}
                        - Eski Tutar: {tr_fmt(sozlesme_tutari)} TL
                        - Yeni Tutar: {tr_fmt(yeni)} TL
                        - SEPET TOPLAM KONTROL: %{toplam} (Eğer 100 değilse kullanıcıyı uyar)
                        
                        PİYASA DEĞİŞİMLERİ (Dönem İçindeki Artışlar):
                        - Dolar (USD): %{piyasa['USDTRY']['degisim']:.2f}
                        - Euro (EUR): %{piyasa['EURTRY']['degisim']:.2f}
                        - Enflasyon (TÜFE): %{val_tufe:.2f}
                        - İşçilik/Asgari Ücret Etkisi: %{iscilik:.2f}
                        - Akaryakıt (Dizel): %{d_dizel:.2f}
                        - Altın: %{piyasa['GRAM_ALTIN_TL']['degisim']:.2f}
                        
                        SEPET AĞIRLIKLARI:
                        - Döviz: %{w_usd + w_eur}
                        - İşçilik: %{w_iscilik}
                        - Enerji: %{w_benzin + w_dizel}
                        - Enflasyon: %{w_tufe + w_ufe + w_mix_oran}

                        YÖNERGE:
                        Hangi kalemin (Döviz mi, Enflasyon mu, Yakıt mı?) artışa en çok sebep olduğunu tespit et. 
                        Eğer artış piyasa ortalamasının üzerindeyse uyar, altındaysa "başarılı bir hedging" olduğunu belirt.
                        Sonuçları madde madde değil, akıcı bir paragraf olarak sun.
                        """
                        
                        # AI Konfigürasyonu
                        genai.configure(api_key=GEMINI_API_KEY)
                        
                        # DÜZELTME BURADA YAPILDI: 'gemini-1.5-flash' yerine 'gemini-pro' kullanıldı.
                        model = genai.GenerativeModel('gemini-pro')
                        
                        response = model.generate_content(prompt)
                        
                        st.success("Analiz Tamamlandı")
                        st.markdown(response.text)
                        
                    except Exception as e:
                        st.error(f"Jarvis Bağlantı Hatası: {str(e)}")
        else:
            st.info("Jarvis şu an beklemede. Güncel verileri yapay zeka ile yorumlamak için butona basınız.")


