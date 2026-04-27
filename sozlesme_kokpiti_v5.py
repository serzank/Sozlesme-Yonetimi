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
    MY_API_KEY = None 

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

# --- ASGARİ ÜCRET HESAPLAYICI ---
def get_asgari_ucret_degisim(d_start, d_end):
    """
    Seçilen tarih aralığındaki Net Asgari Ücret değişimini hesaplar.
    """
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

# --- GOOGLE SHEET H-ÜFE ÇEKİCİ (YENİ ENTEGRASYON) ---
@st.cache_data(ttl=600)
def get_google_sheet_data():
    try:
        sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKKPo73sRdzL227kxw9PRvtd6teIyu74v0bw4NCZUCDmJBXgKxZ3AHYmD4zrkalxVgkOSc1lK6p7PF/pub?output=csv"
        df = pd.read_csv(sheet_url)
        df.columns = df.columns.str.strip()
        df = df.dropna(how='all')
        
        # Tarih Formatı
        df['Tarih'] = pd.to_datetime(df['Tarih'], format='%Y-%m-%d', errors='coerce')
        df = df.dropna(subset=['Tarih'])
        df['Donem'] = df['Tarih'].dt.strftime('%Y-%m') # Eşleştirme için Yıl-Ay formatı
        
        # Sayısal Dönüşüm
        for col in df.columns:
            if col not in ['Tarih', 'Donem']:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

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
        
        # EVDS aylık serilerde hata vermemesi için ayın 1'ini ve sonunu baz alıyoruz
        s_date = start_date - relativedelta(months=2)
        e_date = end_date + relativedelta(months=1)
        
        start_q = s_date.replace(day=1).strftime("%d-%m-%Y")
        
        next_month = e_date + relativedelta(months=1)
        last_day_date = next_month.replace(day=1) - timedelta(days=1)
        end_q = last_day_date.strftime("%d-%m-%Y")

        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1"]
        
        raw_df = evds_service.get_data(series, startdate=start_q, enddate=end_q)
        if raw_df is None or raw_df.empty:
            res["Msg"] = "EVDS'den veri dönmedi. Tarih aralığını kontrol edin."
            return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m', errors='coerce')
        if raw_df['Tarih_Dt'].isna().all():
            raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], errors='coerce')
            
        raw_df = raw_df.dropna(subset=['Tarih_Dt']).copy()
        
        # --- ZIRH: EKSİK (GELECEK) VERİ KORUMASI ---
        # EVDS açıklanmamış aylara 'Boş' atar, bu da %-100 hatasına neden olur.
        data_cols = [c for c in raw_df.columns if c.startswith('TP')]
        for c in data_cols:
            # Boşlukları veya hatalı metinleri sayısal NaN değere zorla
            raw_df[c] = pd.to_numeric(raw_df[c], errors='coerce')
            
        if data_cols:
            # Açıklanmayan henüz boş olan ayı, en son açıklanan ayın verisiyle doldur (Forward Fill)
            raw_df[data_cols] = raw_df[data_cols].ffill()
            raw_df = raw_df.dropna(subset=data_cols, how='all')
            
        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')

        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        if row_start.empty:
            row_start = raw_df[raw_df['Tarih_Dt'] >= pd.to_datetime(start_date.replace(day=1))].head(1)
        
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        if row_end.empty:
            row_end = raw_df.tail(1)

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
            
        res.update({
            "TUFE": round(calc(t_end, t_start), 2),
            "UFE": round(calc(u_end, u_start), 2),
            "HUFE": round(calc(h_end, h_start), 2),
            "Status": True,
            "Msg": f"Veri Aralığı: {row_start['Tarih'].values[0] if not row_start.empty else '?'} - {row_end['Tarih'].values[0] if not row_end.empty else '?'}"
        })
    except Exception as e: 
        res["Msg"] = f"EVDS Bağlantı Hatası: {str(e)}"
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
# ANA EKRAN - ÜST KISIM (TARİH SEÇİMİ VE VERİ ÇEKME KÖPRÜSÜ)
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

# --- VERİ KÖPRÜSÜ (TCMB, EVDS, SHEET, WEB) ---
with st.spinner("PNX Veritabanlarına Bağlanıyor..."):
    tcmb = get_tcmb_data(MY_API_KEY, start_date, end_date)
    yakit_guncel = guncel_akaryakit_cek()
    canli_veri = canli_piyasa_cek()
    evds_gold_ilk = get_evds_gold_history(MY_API_KEY, start_date)
    evds_fuel_ilk = get_evds_fuel_history(MY_API_KEY, start_date)
    
    # Google Sheet'ten H-ÜFE Verisi Çekme (YENİ)
    df_hufe = get_google_sheet_data()

# ============================================================================
# PİYASA VERİSİ İŞLEME (GRAFİKLER İÇİN)
# ============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def piyasa_verisi_al_tekli(d_start, d_end, live_data, evds_gold_start):
    y_end = d_end
    if y_end > date.today(): y_end = date.today()
    
    symbol_map = [("USDTRY", "TRY=X"), ("EURTRY", "EURTRY=X"), ("EURUSD", "EURUSD=X"), 
                  ("ONS_ALTIN", "GC=F"), ("BRENT_PETROL", "BZ=F"), ("ABD_TAHVIL", "^TNX")]
    data_dict = {}
    
    # ZIRH: Yahoo'nun engellememesi için oturum yapılandırması
    import requests
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    for key, symbol in symbol_map:
        ilk, son = 0.0, 0.0
        try:
            # Tarih Aralığı (Haftasonlarını kurtarmak için marjı geniş tuttuk)
            s_str = (d_start - timedelta(days=10)).strftime("%Y-%m-%d")
            e_str = (y_end + timedelta(days=3)).strftime("%Y-%m-%d")
            
            # download metodu genellikle toplu çekimde daha kararlıdır
            df = yf.download(symbol, start=s_str, end=e_str, progress=False, session=session)
            
            if not df.empty:
                # Çok Katmanlı (MultiIndex) Sütun Yapısını Temizle
                if isinstance(df.columns, pd.MultiIndex):
                    # Sadece 'Close' olan sütun seviyesini al
                    seri = df.xs('Close', axis=1, level=0)
                    if isinstance(seri, pd.DataFrame):
                        seri = seri.iloc[:, 0]
                elif 'Close' in df.columns:
                    seri = df['Close']
                else:
                    seri = df.iloc[:, 0]
                
                # Sayısal olmayanları temizle
                seri = pd.to_numeric(seri, errors='coerce').dropna()
                
                if not seri.empty:
                    # Zaman Dilimi (Timezone) Ayıklama
                    if seri.index.tz is not None:
                        clean_index = seri.index.tz_localize(None)
                    else:
                        clean_index = seri.index
                    
                    # Başlangıç tarihine en yakın veriyi bul
                    target_ts = pd.Timestamp(d_start)
                    best_pos = (clean_index - target_ts).abs().argmin()
                    
                    ilk = float(seri.iloc[best_pos])
                    son = float(seri.iloc[-1])
                    
        except Exception:
            ilk, son = 0.0, 0.0
        
        # Canlı veri varsa Yahoo verisinin üzerine yaz
        if key == "USDTRY" and live_data.get("USD", 0) > 0: son = live_data["USD"]
        elif key == "EURTRY" and live_data.get("EUR", 0) > 0: son = live_data["EUR"]
        
        degisim = 0.0
        if ilk > 0: degisim = ((son - ilk) / ilk) * 100
        data_dict[key] = {"ilk": ilk, "son": son, "degisim": degisim}

    # Altın Hesaplama Fallback
    gold_ilk = evds_gold_start
    if gold_ilk <= 0:
        ons_i = data_dict.get("ONS_ALTIN", {}).get("ilk", 0)
        usd_i = data_dict.get("USDTRY", {}).get("ilk", 0)
        if ons_i > 0 and usd_i > 0: gold_ilk = (ons_i / 31.1035) * usd_i

    gold_son = live_data.get("ALTIN", 0)
    if gold_son <= 0:
        ons_s = data_dict.get("ONS_ALTIN", {}).get("son", 0)
        usd_s = data_dict.get("USDTRY", {}).get("son", 0)
        if ons_s > 0 and usd_s > 0: gold_son = (ons_s / 31.1035) * usd_s

    g_deg = ((gold_son - gold_ilk) / gold_ilk * 100) if gold_ilk > 0 else 0.0
    data_dict["GRAM_ALTIN_TL"] = {"ilk": gold_ilk, "son": gold_son, "degisim": g_deg}
    
    return data_dict

piyasa = piyasa_verisi_al_tekli(start_date, end_date, canli_veri, evds_gold_ilk)

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
# PNX DÖVİZ ÇEVRİM MATRİSİ (VALUE MATRIX)
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
        col_u1.metric("Başlangıç ($)", f"{tr_fmt(tutar_usd_baslangic)}")
        col_u2.metric("Güncel ($)", f"{tr_fmt(tutar_usd_guncel)}")
        col_u3.metric("Erime ($)", f"{tr_fmt(fark_usd)}", delta_color="normal")
    
    with c_eur:
        st.markdown(f"**💶 EUR Bazlı Değerleme**")
        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("Başlangıç (€)", f"{tr_fmt(tutar_eur_baslangic)}")
        col_e2.metric("Güncel (€)", f"{tr_fmt(tutar_eur_guncel)}")
        col_e3.metric("Erime (€)", f"{tr_fmt(fark_eur)}", delta_color="normal")
        
    st.markdown(f"<div style='font-size:11px; color:gray; text-align:right'>*Hesaplama: Girilen {tr_fmt(sozlesme_tutari)} TL'nin, başlangıç tarihi ve bugünkü kurlar üzerinden karşılığıdır.</div>", unsafe_allow_html=True)


# ============================================================================
# HESAPLAMA MOTORU (GOOGLE SHEET H-ÜFE ENTEGRASYONLU - v5.0)
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_header, c_link = st.columns([3, 1])
    with c_header: st.subheader("⚡ Enflasyon & Sepet Hesabı")
    with c_link: st.link_button("🔗 Manuel Hesaplama Sitesi", "https://tufehesaplama-serzan.streamlit.app/")

    if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
    else: st.warning(f"⚠️ {tcmb['Msg']}")

    # --- H-ÜFE SHEET İŞLEMLERİ ---
    tum_sektorler = []
    if not df_hufe.empty:
        tum_sektorler = [col for col in df_hufe.columns if col not in ['Tarih', 'Donem']]
    else:
        tum_sektorler = ["Veri Yüklenemedi"]

    # Otomatik Sektör Eşleştirme (Mapping)
    preselect_idx = 0
    search_keyword = ""
    
    # Sözleşme tipine göre arama kelimesini belirle
    if sozlesme_tipi == "Güvenlik Hizmetleri": search_keyword = "Güvenlik"
    elif sozlesme_tipi == "Personel Taşımacılık": search_keyword = "Kara"
    elif sozlesme_tipi == "Yiyecek-İçecek Hizmetleri": search_keyword = "Yiyecek"
    elif sozlesme_tipi == "Yazılım / Lisans": search_keyword = "Bilgi"
    
    # Listede o kelimeyi bul
    if search_keyword:
        for i, s in enumerate(tum_sektorler):
            if search_keyword in s:
                preselect_idx = i
                break

    # --- SEKTÖR SEÇİM VE ARAMA ---
    st.markdown("##### 📊 H-ÜFE Sektör Seçimi")
    c_search, c_select, c_manuel = st.columns([2, 3, 1])
    
    with c_search:
        filter_text = st.text_input("🔍 Sektör Ara (Filtre)", value=search_keyword)
    
    # Listeyi filtrele
    filtered_list = tum_sektorler
    if filter_text:
        filtered_list = [s for s in tum_sektorler if filter_text.lower() in s.lower()]
        if not filtered_list: filtered_list = tum_sektorler # Bulamazsa hepsini göster
    
    with c_select:
        # Eğer otomatik eşleşme (preselect) filtrelenmiş listede varsa onu seç
        final_idx = 0
        if tum_sektorler[preselect_idx] in filtered_list:
            final_idx = filtered_list.index(tum_sektorler[preselect_idx])
            
        selected_sector = st.selectbox("📋 Listeden Seçiniz", filtered_list, index=final_idx, label_visibility="collapsed")
    
    with c_manuel:
        st.link_button("🔗 TÜİK Kontrol", "https://data.tuik.gov.tr/Kategori/GetKategori?p=Enflasyon-ve-Fiyat-106")

    # --- SHEET'TEN VERİ HESAPLAMA (GÜÇLENDİRİLMİŞ & DEBUG MODLU) ---
    val_hufe_final = 0.0
    
    # Teşhis kutusunu sadece geliştirme aşamasında açık tutalım, sonra kapatabilirsiniz.
    debug_sheet = st.expander(f"🕵️ H-ÜFE Hesaplama Detayı: {selected_sector}", expanded=False)

    if not df_hufe.empty and selected_sector:
        try:
            # 1. Tarihleri Standartlaştır (Timestamp Formatına Çevir)
            target_start = pd.to_datetime(start_date)
            target_end = pd.to_datetime(end_date)
            
            # 2. En Yakın Tarihleri Bul (Matematiksel Olarak En Yakın Satır)
            # Bu yöntem "Tam Eşleşme" aramaz, en yakın tarihi bulur. Hata payını sıfırlar.
            
            # Başlangıç için en yakın tarih indeksi
            idx_start = (df_hufe['Tarih'] - target_start).abs().idxmin()
            # Bitiş için en yakın tarih indeksi
            idx_end = (df_hufe['Tarih'] - target_end).abs().idxmin()
            
            # 3. Değerleri Çek
            row_s = df_hufe.loc[idx_start]
            row_e = df_hufe.loc[idx_end]
            
            v1 = safe_float(row_s[selected_sector])
            v2 = safe_float(row_e[selected_sector])
            
            d1_str = row_s['Tarih'].strftime('%d.%m.%Y')
            d2_str = row_e['Tarih'].strftime('%d.%m.%Y')

            # 4. Debugger'a Yaz (Kanıt)
            debug_sheet.write(f"**Hedef Başlangıç:** {start_date} ➡️ **Bulunan:** {d1_str} (Değer: {v1})")
            debug_sheet.write(f"**Hedef Bitiş:** {end_date} ➡️ **Bulunan:** {d2_str} (Değer: {v2})")

            # 5. Hesapla
            if v1 > 0:
                val_hufe_final = ((v2 - v1) / v1) * 100
                debug_sheet.success(f"✅ Hesaplanan Değişim: %{val_hufe_final:.2f}")
            else:
                debug_sheet.error("Başlangıç değeri 0 olduğu için hesaplanamadı.")
                
        except Exception as e:
            debug_sheet.error(f"Hesaplama Hatası: {str(e)}")
            val_hufe_final = 0.0

    # --- VERİ HAZIRLIĞI ---
    val_tufe = safe_float(tcmb["TUFE"])
    val_ufe = safe_float(tcmb["UFE"])
    val_mix = (val_tufe + val_ufe) / 2
    
    val_iscilik, asgari_eski, asgari_yeni = get_asgari_ucret_degisim(start_date, end_date)
    iscilik_notu = f"{tr_fmt(asgari_eski)} ➡️ {tr_fmt(asgari_yeni)} TL"

    # --- INPUT ALANLARI ---
    ec1, ec2, ec_mix, ec3, ec4, ec5 = st.columns(6)
    tufe = ec1.number_input("TÜFE %", value=val_tufe, key=f"t_{d_key}")
    ufe = ec2.number_input("ÜFE %", value=val_ufe, key=f"u_{d_key}")
    ort_mix_giris = ec_mix.number_input("Ort(TÜFE+ÜFE)", value=val_mix, key=f"mix_{d_key}")
    
    # ✅ Düzeltilmiş Satır (Key kısmına selected_sector eklendi)
    h_ufe = ec3.number_input("H-ÜFE %", value=val_hufe_final, key=f"h_{d_key}_{selected_sector}", help=f"Seçilen Sektör: {selected_sector}")
    
    iscilik = ec4.number_input("İşçilik %", value=val_iscilik, key=f"i_{d_key}", help=f"Otomatik Hesaplanan Asgari Ücret:\n{iscilik_notu}")
    abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")
    
    if val_iscilik > 0:
        ec4.markdown(f"<div style='font-size:10px; color:#27AE60'>ASG: {iscilik_notu}</div>", unsafe_allow_html=True)
    
    # Seçilen sektör bilgisini göster
    ec3.markdown(f"<div style='font-size:10px; color:#F39C12'>{selected_sector[:15]}...</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### ⚖️ Sepet Ağırlıkları")

    # --- AĞIRLIK INPUTLARI ---
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

    # --- TOPLAM KONTROLÜ VE HESAPLAMA ---
    toplam = w_mix_oran+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd
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
# JARVIS PROJEKSİYONU (SENARYO ANALİZİ & BÜTÇE SİMÜLASYONU) v2.0
# ============================================================================
st.markdown("---")
with st.container(border=True):
    c_p1, c_p2 = st.columns([3,1])
    with c_p1: st.header("🔮 Jarvis Gelecek Projeksiyonu & Senaryo Analizi")
    with c_p2: st.markdown("<div style='text-align:right; font-size:12px; color:gray'>*Tahminler bileşik faiz etkisiyle hesaplanır.</div>", unsafe_allow_html=True)
    
    # --- AYARLAR ---
    proj_months = 12
    dates = [date.today() + relativedelta(months=i) for i in range(1, proj_months + 1)]
    dates_str = [d.strftime("%Y-%m") for d in dates]

    # Baz Oran (Mevcut hesaplanan zam oranı üzerinden aylık etki)
    base_monthly_inc = (zam / 12) if zam > 5 else 2.5
    
    col_set1, col_set2, col_set3 = st.columns(3)
    with col_set1:
        st.markdown("**📉 İyimser Senaryo**")
        rate_opt = st.number_input("Aylık Artış Beklentisi (%)", value=base_monthly_inc * 0.7, step=0.1, key="rate_opt")
    with col_set2:
        st.markdown("**Example: 📊 Gerçekçi Senaryo (Jarvis)**")
        rate_base = st.number_input("Aylık Artış Beklentisi (%)", value=base_monthly_inc, step=0.1, key="rate_base")
    with col_set3:
        st.markdown("**📈 Kötümser Senaryo**")
        rate_pes = st.number_input("Aylık Artış Beklentisi (%)", value=base_monthly_inc * 1.5, step=0.1, key="rate_pes")

    # --- HESAPLAMA MOTORU ---
    def calculate_projection(start_val, monthly_rate, months):
        values = []
        curr = start_val
        for _ in range(months):
            curr = curr * (1 + monthly_rate/100)
            values.append(curr)
        return values

    vals_opt = calculate_projection(yeni, rate_opt, proj_months)
    vals_base = calculate_projection(yeni, rate_base, proj_months)
    vals_pes = calculate_projection(yeni, rate_pes, proj_months)
    
    # Toplam Yıllık Maliyet (Kümülatif)
    total_opt = sum(vals_opt)
    total_base = sum(vals_base)
    total_pes = sum(vals_pes)

    # --- KPI KARTLARI ---
    st.markdown("##### 🗓️ 12 Aylık Toplam Tahmini Bütçe")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("İyimser Toplam", f"{tr_fmt(total_opt)} TL", delta=f"Ort. Aylık: {tr_fmt(total_opt/12)}")
    kpi2.metric("Gerçekçi Toplam", f"{tr_fmt(total_base)} TL", delta=f"Ort. Aylık: {tr_fmt(total_base/12)}", delta_color="off")
    kpi3.metric("Kötümser Toplam", f"{tr_fmt(total_pes)} TL", delta=f"Risk Farkı: {tr_fmt(total_pes - total_base)}", delta_color="inverse")

    # --- GRAFİKLER (TAB YAPISI) ---
    tab_line, tab_bar = st.tabs(["📈 Aylık Trend Analizi", "📊 Kümülatif Bütçe Yükü"])

    with tab_line:
        if HAS_MATPLOTLIB:
            fig, ax = plt.subplots(figsize=(10, 5))
            
            # Senaryo Çizgileri
            ax.plot(dates_str, vals_pes, color='#C0392B', linestyle='--', marker='o', linewidth=2, label=f'Kötümser (%{rate_pes:.1f}/ay)')
            ax.plot(dates_str, vals_base, color='#2980B9', marker='s', linewidth=3, label=f'Gerçekçi (%{rate_base:.1f}/ay)')
            ax.plot(dates_str, vals_opt, color='#27AE60', linestyle='-.', marker='^', linewidth=2, label=f'İyimser (%{rate_opt:.1f}/ay)')
            
            # Alan Boyama (Range)
            ax.fill_between(dates_str, vals_opt, vals_pes, color='gray', alpha=0.1)
            
            ax.set_title(f"Gelecek 12 Ay Fiyat Projeksiyonu (Başlangıç: {tr_fmt(yeni)} TL)", fontsize=12)
            ax.set_ylabel("Aylık Fatura Tutarı (TL)")
            ax.legend()
            ax.grid(True, alpha=0.3, linestyle='--')
            plt.xticks(rotation=45)
            
            # Değerleri Göster (Sadece Baş ve Son)
            for i, val in enumerate([vals_base[0], vals_base[-1]]):
                idx = 0 if i==0 else -1
                ax.annotate(f"{tr_fmt(val)}", (dates_str[idx], vals_base[idx]), xytext=(0,10), textcoords='offset points', ha='center', fontsize=9, fontweight='bold', color='#2980B9')

            st.pyplot(fig)
        else:
            st.line_chart(pd.DataFrame({"İyimser": vals_opt, "Gerçekçi": vals_base, "Kötümser": vals_pes}, index=dates_str))

    with tab_bar:
        # Kümülatif Artış Grafiği
        if HAS_MATPLOTLIB:
            fig2, ax2 = plt.subplots(figsize=(10, 5))
            x = np.arange(len(dates_str))
            width = 0.25
            
            # Kümülatif Veri Hazırlığı
            cum_opt = np.cumsum(vals_opt)
            cum_base = np.cumsum(vals_base)
            cum_pes = np.cumsum(vals_pes)
            
            rects1 = ax2.bar(x - width, cum_opt, width, label='İyimser', color='#A9DFBF')
            rects2 = ax2.bar(x, cum_base, width, label='Gerçekçi', color='#5DADE2')
            rects3 = ax2.bar(x + width, cum_pes, width, label='Kötümser', color='#E6B0AA')
            
            ax2.set_ylabel('Kümülatif Toplam (TL)')
            ax2.set_title('Yıl Sonu Toplam Maliyet Birikimi')
            ax2.set_xticks(x)
            ax2.set_xticklabels(dates_str, rotation=45)
            ax2.legend()
            ax2.grid(axis='y', alpha=0.3)
            
            st.pyplot(fig2)
        else:
             st.info("Kümülatif grafik için matplotlib gereklidir.")

# ============================================================================
# JARVIS AI & YORUM MODÜLÜ (MASTER SÜRÜM - v1.6 - FUTURE READY / 2.5 FLASH)
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
                with st.spinner("Jarvis (Gemini 2.5 Flash) verileri işliyor..."):
                    try:
                        # AI Konfigürasyonu
                        genai.configure(api_key=GEMINI_API_KEY)
                        
                        # --- TAV STANDARDI: GÜNCEL MODEL SEÇİMİ ---
                        # Sizin listenizdeki en hızlı ve güncel model:
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
                        - İşçilik: %{iscilik:.2f}
                        - Akaryakıt: %{d_dizel:.2f}
                        
                        SEPET AĞIRLIKLARI:
                        - Döviz: %{w_usd + w_eur}
                        - İşçilik: %{w_iscilik}
                        - Enerji: %{w_benzin + w_dizel}
                        - Enflasyon: %{w_tufe + w_ufe + w_mix_oran}

                        YÖNERGE:
                        Hangi kalemin artışa en çok sebep olduğunu tespit et. 
                        Eğer artış piyasa ortalamasının üzerindeyse uyar, altındaysa "başarılı bir hedging" olduğunu belirt.
                        Sonuçları akıcı bir paragraf olarak sun.
                        """
                        
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(prompt)
                        
                        st.success(f"Analiz Tamamlandı (Motor: {model_name})")
                        st.markdown(response.text)
                        
                    except Exception as e:
                        st.error(f"Bir hata oluştu: {str(e)}")
                        st.info("Eğer yine hata alırsanız, lütfen model adını 'gemini-2.5-pro' olarak değiştirip deneyin.")
        else:
            st.info("Jarvis şu an beklemede. Güncel verileri yapay zeka ile yorumlamak için butona basınız.")




