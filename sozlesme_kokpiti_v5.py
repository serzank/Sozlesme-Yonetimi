import streamlit as st
import pandas as pd
import yfinance as yf
from evds import evdsAPI
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import urllib3
import io
import requests
from bs4 import BeautifulSoup
import plotly.express as px

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
# TAV/Procurement çalışmaları için API Key
MY_API_KEY = "Uol1kIOQos" 

# --- Sayfa Ayarları ---
st.set_page_config(page_title="TAV - Procurement Master", layout="wide", page_icon="🛡️")

# --- CSS Tasarım (Kurumsal) ---
st.markdown("""
    <style>
    .logo-text { font-size: 24px !important; font-weight: 900 !important; color: #1E3D59 !important; font-family: sans-serif; margin-bottom: 5px; }
    .sub-text { font-size: 14px; color: #666; margin-bottom: 20px; }
    .kutu, .kutu-enerji { padding: 15px; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; color: #1E3D59 !important; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; color: #1E3D59 !important; }
    .kutu *, .kutu-enerji *, .kutu b, .kutu-enerji b { color: #1E3D59 !important; }
    .pozitif { color: #27AE60 !important; font-weight: bold; font-size: 18px; }
    .negatif { color: #C0392B !important; font-weight: bold; font-size: 18px; }
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; text-decoration: none; }
    .jarvis-note { background-color: #e8f4f8; padding: 15px; border-radius: 8px; border: 1px solid #bce8f1; color: #31708f; font-size: 15px; }
    .badge-live { background-color: #27AE60; color: white !important; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; vertical-align: middle; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
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

# --- 1. WEB SCRAPING: YENİLENMİŞ YAKIT MODÜLÜ ---
@st.cache_data(ttl=3600)
def guncel_akaryakit_cek():
    """Doviz.com İstanbul Avrupa Yakası Fiyatlarını Çeker"""
    url = "https://www.doviz.com/akaryakit-fiyatlari/istanbul-avrupa"
    headers = {'User-Agent': 'Mozilla/5.0'}
    fiyatlar = {"benzin": 0.0, "motorin": 0.0}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find('table')
            if table:
                tbody = table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    if rows:
                        first_row = rows[0] 
                        cols = first_row.find_all('td')
                        if len(cols) >= 3:
                            raw_benzin = cols[1].get_text().replace('₺', '').strip().replace(',', '.')
                            raw_motorin = cols[2].get_text().replace('₺', '').strip().replace(',', '.')
                            fiyatlar["benzin"] = float(raw_benzin)
                            fiyatlar["motorin"] = float(raw_motorin)
    except Exception as e:
        pass
    return fiyatlar

# --- 2. KONSOLİDE TCMB VERİ MOTORU ---
@st.cache_data(ttl=3600)
def get_consolidated_data(api_key, start_date, end_date):
    """
    Hem Döviz kurlarını hem de seçilen iki tarih arasındaki net TÜFE/ÜFE değişimini hesaplar.
    """
    res = {
        "TUFE_ORAN": 0.0, "UFE_ORAN": 0.0, "HUFE_ORAN": 0.0,
        "USD_ILK": 0.0, "USD_SON": 0.0, "USD_DEG": 0.0,
        "EUR_ILK": 0.0, "EUR_SON": 0.0, "EUR_DEG": 0.0,
        "Trend_Data": None,
        "Status": False, "Msg": "Veri Yok"
    }
    
    if not api_key: return res

    try:
        evds_service = evdsAPI(api_key)
        
        # Tarih Formatı (Geniş aralık alıp içinden seçeceğiz)
        # Veri eksiği olmaması için 1 ay geriden ve 1 ay ileriden başlatıyoruz
        s_query = (start_date - relativedelta(months=2)).strftime("%d-%m-%Y")
        e_query = (end_date + relativedelta(months=1)).strftime("%d-%m-%Y")
        
        # SERİLER:
        # TP.FG.J0: TÜFE
        # TP.TUFE1YI.T1: Yİ-ÜFE
        # TP.HKFE01.I1: H-ÜFE (Hizmet)
        # TP.DK.USD.A.YTL: Dolar Alış
        # TP.DK.EUR.A.YTL: Euro Alış
        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1", "TP.DK.USD.A.YTL", "TP.DK.EUR.A.YTL"]
        
        raw_df = evds_service.get_data(series, startdate=s_query, enddate=e_query)
        
        if raw_df is None or raw_df.empty:
            res["Msg"] = "API Boş Döndü"
            return res
            
        # Kolon İsimlerini Temizle
        raw_df.rename(columns={
            "TP_FG_J0": "TÜFE",
            "TP_TUFE1YI_T1": "Yİ-ÜFE",
            "TP_HKFE01_I1": "H-ÜFE",
            "TP_DK_USD_A_YTL": "USD",
            "TP_DK_EUR_A_YTL": "EUR",
            "Tarih": "Tarih_Str"
        }, inplace=True)
        
        # Tarih İşleme
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih_Str'], format='%Y-%m') if 'Tarih_Str' in raw_df.columns else pd.to_datetime(raw_df['Tarih_Dt'])
        
        # Sayısallaştırma
        cols_to_num = ["TÜFE", "Yİ-ÜFE", "H-ÜFE", "USD", "EUR"]
        for c in cols_to_num:
            if c in raw_df.columns:
                raw_df[c] = pd.to_numeric(raw_df[c], errors='coerce')

        # --- DÖVİZ İÇİN (Günlük/Aylık En Yakın Değer) ---
        # Başlangıç ve Bitiş tarihine en yakın satırları bul
        mask_start = raw_df['Tarih_Dt'] >= pd.to_datetime(start_date)
        mask_end = raw_df['Tarih_Dt'] <= pd.to_datetime(end_date)
        
        # Döviz mantığı: Start date'e en yakın veri, End date'e en yakın veri
        # Not: EVDS aylık veri döndürüyorsa o ayın değerini alır.
        
        # --- ENFLASYON İÇİN (AY BAZLI EŞLEŞTİRME) ---
        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')
        
        row_start_inf = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        row_end_inf = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        
        # Eğer tam o ayın verisi yoksa (Örn: Ayın 1'indeyiz, enflasyon açıklanmadı), bir önceki ayı dene
        if row_end_inf.empty or pd.isna(row_end_inf["TÜFE"].values[0]):
             p_end_prev = p_end - 1
             row_end_inf = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end_prev]
             res["Msg"] = f"Not: {p_end} verisi açıklanmadığı için {p_end_prev} kullanıldı."
        else:
             res["Msg"] = "Veriler Güncel"

        # Hesaplama Fonksiyonu
        def calc_degisim(start_row, end_row, col_name):
            try:
                if start_row.empty or end_row.empty: return 0.0
                val_s = float(start_row[col_name].values[0])
                val_e = float(end_row[col_name].values[0])
                if val_s == 0: return 0.0
                return ((val_e - val_s) / val_s) * 100
            except: return 0.0
            
        res["TUFE_ORAN"] = calc_degisim(row_start_inf, row_end_inf, "TÜFE")
        res["UFE_ORAN"] = calc_degisim(row_start_inf, row_end_inf, "Yİ-ÜFE")
        res["HUFE_ORAN"] = calc_degisim(row_start_inf, row_end_inf, "H-ÜFE")
        
        # Döviz Değerlerini Al (Satır boşsa 0 dön)
        def get_val(r, c): return float(r[c].values[0]) if not r.empty and pd.notna(r[c].values[0]) else 0.0
        
        res["USD_ILK"] = get_val(row_start_inf, "USD")
        res["USD_SON"] = get_val(row_end_inf, "USD")
        res["EUR_ILK"] = get_val(row_start_inf, "EUR")
        res["EUR_SON"] = get_val(row_end_inf, "EUR")
        
        # Döviz Değişim
        if res["USD_ILK"] > 0: res["USD_DEG"] = ((res["USD_SON"] - res["USD_ILK"]) / res["USD_ILK"]) * 100
        if res["EUR_ILK"] > 0: res["EUR_DEG"] = ((res["EUR_SON"] - res["EUR_ILK"]) / res["EUR_ILK"]) * 100
        
        # Grafik için Dataframe'i kaydet
        res["Trend_Data"] = raw_df[(raw_df['Tarih_Dt'].dt.to_period('M') >= p_start) & (raw_df['Tarih_Dt'].dt.to_period('M') <= p_end)]
        
        res["Status"] = True
        
    except Exception as e:
        res["Msg"] = f"Hata: {str(e)}"
    
    return res

# --- 3. PIYASA VERISI ---
@st.cache_data(ttl=600)
def piyasa_verisi_al(d_start, d_end):
    tickers = { "ONS_ALTIN": "XAUUSD=X", "BRENT_PETROL": "BZ=F" }
    data_dict = {"ONS_ALTIN": {"ilk":0,"son":0}, "BRENT_PETROL": {"ilk":0,"son":0,"degisim":0}}
    
    try:
        raw_data = yf.download(list(tickers.values()), start=d_start, end=d_end + timedelta(days=1), progress=False)['Close']
        raw_data = raw_data.ffill().bfill()
        
        if not raw_data.empty:
            for key, symbol in tickers.items():
                try:
                    c_name = [c for c in raw_data.columns if symbol in str(c)]
                    if not c_name: continue
                    seri = raw_data[c_name[0]]
                    if len(seri) > 0:
                        data_dict[key]["ilk"] = float(seri.iloc[0])
                        data_dict[key]["son"] = float(seri.iloc[-1])
                        if key == "BRENT_PETROL" and data_dict[key]["ilk"] > 0:
                            data_dict[key]["degisim"] = ((data_dict[key]["son"] - data_dict[key]["ilk"]) / data_dict[key]["ilk"]) * 100
                except: pass
    except: pass
    return data_dict

# ============================================================================
# SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">TAV Procurement<br>Master Cockpit</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-text">Contract & Escalation Specialist</div>', unsafe_allow_html=True)
    
    st.header("📅 Hakediş Dönemi")
    
    today = date.today()
    default_start = today - relativedelta(years=1)
    
    start_date = st.date_input("Sözleşme Başlangıcı", value=default_start)
    end_date = st.date_input("Hakediş Tarihi", value=today)
    
    if start_date >= end_date: st.error("Hata: Başlangıç < Bitiş olmalı")
    
    # KONSOLİDE VERİ ÇEKİMİ
    with st.spinner("TCMB ve Piyasalar Analiz Ediliyor..."):
        # 1. EVDS'den Otomatik Hesapla
        main_data = get_consolidated_data(MY_API_KEY, start_date, end_date)
        # 2. Yahoo'dan Ons Altın ve Brent Çek
        piyasa = piyasa_verisi_al(start_date, end_date)
        # 3. Web'den Yakıt Çek
        yakit_data = guncel_akaryakit_cek()
    
    st.markdown("---")
    sozlesme_tutari = st.number_input("Sözleşme Tutarı (TL):", value=100000.0, step=1000.0, format="%.2f")
    d_key = f"{start_date}_{end_date}"
    
    st.caption("Sir, veriler TAV network'ü dışından çekilmektedir.")

# ============================================================================
# GRAM ALTIN HESAPLAMA (TCMB KUR * SPOT ONS)
# ============================================================================
gram_ilk = 0.0
gram_son = 0.0
gram_deg = 0.0

if piyasa["ONS_ALTIN"]["ilk"] > 0 and main_data["USD_ILK"] > 0:
    gram_ilk = (piyasa["ONS_ALTIN"]["ilk"] * main_data["USD_ILK"]) / 31.1035
    gram_son = (piyasa["ONS_ALTIN"]["son"] * main_data["USD_SON"]) / 31.1035
    if gram_ilk > 0: gram_deg = ((gram_son - gram_ilk) / gram_ilk) * 100

# ============================================================================
# GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans & Sözleşme Kokpiti v5.0")
st.caption(f"Analiz Dönemi: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} | {main_data['Msg']}")

# Kutu Fonksiyonu
def kutu_goster(col, baslik, ilk, son, degisim, ikon, kaynak=""):
    with col:
        st.markdown(f"<div class='kutu'><div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:5px;'><div><span style='font-size:20px; margin-right:8px;'>{ikon}</span><b>{baslik}</b></div><small style='color:#999'>{kaynak}</small></div>", unsafe_allow_html=True)
        renk = "pozitif" if degisim >= 0 else "negatif"
        st.markdown(f"<div style='font-size:12px; color:#666 !important;'>Baz: {tr_fmt(ilk)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:baseline;'><span class='big-metric'>{tr_fmt(son)}</span><span class='{renk}'>%{degisim:.2f}</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
kutu_goster(k1, "USD/TL", main_data["USD_ILK"], main_data["USD_SON"], main_data["USD_DEG"], "💵", "TCMB")
kutu_goster(k2, "EUR/TL", main_data["EUR_ILK"], main_data["EUR_SON"], main_data["EUR_DEG"], "💶", "TCMB")
kutu_goster(k3, "Gram Altın", gram_ilk, gram_son, gram_deg, "🥇", "Hesap")

parite_ilk = main_data["EUR_ILK"] / main_data["USD_ILK"] if main_data["USD_ILK"] > 0 else 0
parite_son = main_data["EUR_SON"] / main_data["USD_SON"] if main_data["USD_SON"] > 0 else 0
parite_deg = ((parite_son-parite_ilk)/parite_ilk)*100 if parite_ilk > 0 else 0
kutu_goster(k4, "EUR/USD", parite_ilk, parite_son, parite_deg, "⚖️", "TCMB")

# ENERJİ
st.markdown("---")
col_link, _ = st.columns([1,3])
col_link.link_button("⛽ Petrol Ofisi Arşiv", "https://www.petrolofisi.com.tr/arsiv-fiyatlari")

st.markdown("### 🛢️ Enerji & Lojistik Giderleri")
e1, e2, e3 = st.columns(3)

# Brent
kutu_goster(e1, "Brent ($)", piyasa["BRENT_PETROL"]["ilk"], piyasa["BRENT_PETROL"]["son"], piyasa["BRENT_PETROL"]["degisim"], "🛢️", "Global")

# Yakıt (Manuel/Scrape)
oto_benzin = yakit_data.get("benzin", 0.0)
oto_motorin = yakit_data.get("motorin", 0.0)

with e2:
    badge = f"<span class='badge-live'>CANLI: {oto_benzin} TL</span>" if oto_benzin > 0 else ""
    st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b> {badge}", unsafe_allow_html=True)
    b_eski = st.number_input("Eski (TL)", value=41.0, key=f"bo_{d_key}")
    val_bn = oto_benzin if oto_benzin > 0 else 44.0
    b_yeni = st.number_input("Yeni (TL)", value=val_bn, key=f"bn_{d_key}")
    d_benzin = ((b_yeni-b_eski)/b_eski)*100 if b_eski > 0 else 0.0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    badge_m = f"<span class='badge-live'>CANLI: {oto_motorin} TL</span>" if oto_motorin > 0 else ""
    st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b> {badge_m}", unsafe_allow_html=True)
    m_eski = st.number_input("Eski (TL)", value=42.0, key=f"mo_{d_key}")
    val_mn = oto_motorin if oto_motorin > 0 else 45.0
    m_yeni = st.number_input("Yeni (TL)", value=val_mn, key=f"mn_{d_key}")
    d_dizel = ((m_yeni-m_eski)/m_eski)*100 if m_eski > 0 else 0.0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

# ENFLASYON & ŞABLONLAR
st.markdown("---")
st.subheader("📊 Enflasyon Verileri (Otomatik Hesaplanan)")
st.info(f"ℹ️ Seçilen tarih aralığında ({start_date} - {end_date}) TCMB endekslerine göre hesaplanan net değişim oranları aşağıdadır.")

ec1, ec2, ec3, ec4, ec5 = st.columns(5)
# Buradaki değerler artık API'den dönen "Date-to-Date" hesaplamasıdır.
tufe = ec1.number_input("TÜFE %", value=safe_float(main_data["TUFE_ORAN"]), key=f"t_{d_key}", help="Seçilen iki ay arasındaki net TÜFE değişimi")
ufe = ec2.number_input("Yİ-ÜFE %", value=safe_float(main_data["UFE_ORAN"]), key=f"u_{d_key}", help="Seçilen iki ay arasındaki net ÜFE değişimi")
h_ufe = ec3.number_input("H-ÜFE %", value=safe_float(main_data["HUFE_ORAN"]), key=f"h_{d_key}", help="Hizmet Üretici Fiyat Endeksi")
iscilik = ec4.number_input("İşçilik %", value=0.0, help="Asgari Ücret Farkı (Manuel Giriniz)", key=f"i_{d_key}")
abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")
ozel_oran = (tufe + ufe) / 2

# AKILLI ŞABLONLAR
st.markdown("---")
col_title_w, col_temp = st.columns([2, 2])
col_title_w.markdown("#### ⚖️ Fiyat Farkı Formül Ağırlıkları")

sablonlar = {
    "Manuel Giriş": {},
    "🏗️ İnşaat/Tadilat (MEP)": {"tufe": 10, "ufe": 40, "usd": 30, "eur": 20},
    "🧹 Temizlik/Personel": {"iscilik": 80, "tufe": 20},
    "💻 IT/Lisanslama (Oracle/MS)": {"usd": 80, "eur": 20},
    "🚛 Lojistik/Nakliye": {"dizel": 40, "iscilik": 30, "tufe": 30},
    "🍽️ Catering (Yemek)": {"tufe": 50, "iscilik": 30, "benzin": 20},
    "🏢 Genel Müteahhitlik (GC)": {"ufe": 60, "tufe": 10, "iscilik": 30}
}
secilen_sablon = col_temp.selectbox("⚡ Hızlı Şablon Seç:", list(sablonlar.keys()))
def get_def(k, default=0): return sablonlar[secilen_sablon].get(k, 0) if secilen_sablon != "Manuel Giriş" else default

w1, w2, w3, w4 = st.columns(4)
w_ozel = w1.number_input("Karma (T+Ü)/2 %", value=get_def("mix", 0))
w_tufe = w2.number_input("TÜFE %", value=get_def("tufe", 30))
w_ufe = w3.number_input("ÜFE %", value=get_def("ufe", 0))
w_hufe = w4.number_input("H-ÜFE %", value=get_def("hufe", 10))

w5, w6, w7, w8 = st.columns(4)
w_iscilik = w5.number_input("İşçilik %", value=get_def("iscilik", 30))
w_usd = w6.number_input("USD %", value=get_def("usd", 20))
w_eur = w7.number_input("EUR %", value=get_def("eur", 10))
w_altin = w8.number_input("Altın %", value=get_def("altin", 0))

w9, w10, w11, w12 = st.columns(4)
w_benzin = w9.number_input("Benzin %", value=get_def("benzin", 0))
w_dizel = w10.number_input("Motorin %", value=get_def("dizel", 0))
w_brent = w11.number_input("Brent %", value=get_def("brent", 0))
w_abd = w12.number_input("ABD Enf.%", value=get_def("abd", 0))

toplam = w_ozel+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd
if toplam != 100: st.error(f"⚠️ Ağırlık Toplamı: %{toplam} (100 olmalı)")

# HESAPLAMA
etkiler = [
    ("Karma (T+Ü)/2", safe_float(ozel_oran), safe_float(w_ozel)), 
    ("TÜFE", safe_float(tufe), safe_float(w_tufe)), 
    ("Yİ-ÜFE", safe_float(ufe), safe_float(w_ufe)), 
    ("H-ÜFE", safe_float(h_ufe), safe_float(w_hufe)),
    ("İşçilik", safe_float(iscilik), safe_float(w_iscilik)), 
    ("USD", safe_float(main_data["USD_DEG"]), safe_float(w_usd)), 
    ("EUR", safe_float(main_data["EUR_DEG"]), safe_float(w_eur)), 
    ("Altın", safe_float(gram_deg), safe_float(w_altin)),
    ("Benzin", safe_float(d_benzin), safe_float(w_benzin)), 
    ("Motorin", safe_float(d_dizel), safe_float(w_dizel)), 
    ("Brent", safe_float(piyasa["BRENT_PETROL"]["degisim"]), safe_float(w_brent)), 
    ("ABD Enf", safe_float(abd_enf), safe_float(w_abd))
]
zam = sum([(e[1] * e[2])/100 for e in etkiler])
fark = sozlesme_tutari * (zam / 100)
yeni = sozlesme_tutari + fark

st.markdown("---")
r1, r2, r3 = st.columns(3)
r1.metric("Toplam Fiyat Farkı Oranı", f"%{zam:.2f}")
r2.metric("Fiyat Farkı Tutarı", f"{tr_fmt(fark)} TL")
r3.metric("YENİ SÖZLEŞME TUTARI", f"{tr_fmt(yeni)} TL", delta_color="normal")

# JARVIS YORUMU
df_temp = pd.DataFrame(etkiler, columns=["Kalem", "Degisim", "Agirlik"])
df_temp["Etki"] = (df_temp["Degisim"] * df_temp["Agirlik"]) / 100
df_sorted = df_temp.sort_values(by="Etki", ascending=False)
if not df_sorted.empty and zam > 0:
    top = df_sorted.iloc[0]
    st.markdown(f"""<div class="jarvis-note">💡 <b>Jarvis Analizi:</b> Sir, bu dönemdeki artışın ana kaynağı <b>{top['Kalem']}</b> kalemidir. 
    Toplam %{zam:.2f} artışın <b>%{top['Etki']:.2f}</b> puanlık kısmı buradan gelmektedir.</div>""", unsafe_allow_html=True)

# GRAFİK ANALİZİ (YENİ EKLENTİ)
if main_data["Trend_Data"] is not None and not main_data["Trend_Data"].empty:
    with st.expander("📈 Enflasyon ve Kur Trend Grafiğini Göster"):
        fig = px.line(main_data["Trend_Data"], x="Tarih_Dt", y=["TÜFE", "Yİ-ÜFE", "USD", "EUR"], 
                      title="Seçilen Dönemde Endeks ve Kur Hareketleri", markers=True)
        st.plotly_chart(fig, use_container_width=True)

# TABLO & EXCEL
st.markdown("---")
df = pd.DataFrame([{"Kalem":e[0], "Değişim %":e[1], "Ağırlık %":e[2], "Etki %":(e[1]*e[2])/100} for e in etkiler if e[2]>0])
t1, t2 = st.columns([3, 1])
with t1: st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)

with t2:
    st.write("")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Hesap_Detay', index=False)
        # Ozet Tablo
        pd.DataFrame({
            'Parametre': ['Dönem Başı', 'Dönem Sonu', 'Eski Tutar', 'Yeni Tutar', 'Fark'], 
            'Deger': [start_date, end_date, sozlesme_tutari, yeni, fark]
        }).to_excel(writer, sheet_name='Ozet', index=False)
        # Trend Verisi
        if main_data["Trend_Data"] is not None:
             main_data["Trend_Data"].to_excel(writer, sheet_name='TCMB_Verileri', index=False)
             
    st.download_button("📥 Excel Raporu İndir", data=buffer.getvalue(), file_name=f"Hakedis_{start_date}_{end_date}.xlsx", mime="application/vnd.ms-excel", type="primary")
