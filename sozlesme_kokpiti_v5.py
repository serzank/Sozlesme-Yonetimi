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

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
try:
    MY_API_KEY = st.secrets["EVDS_KEY"]
except:
    MY_API_KEY = "Uol1kIOQos" 

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement v4.0", layout="wide", page_icon="🛡️")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    .logo-text { font-size: 22px !important; font-weight: 900 !important; color: #D91E18 !important; font-family: sans-serif; margin-bottom: 20px; }
    .kutu, .kutu-enerji { padding: 15px; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; color: #1E3D59 !important; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; color: #1E3D59 !important; }
    .kutu *, .kutu-enerji *, .kutu b, .kutu-enerji b { color: #1E3D59 !important; }
    .pozitif { color: #27AE60 !important; font-weight: bold; font-size: 18px; }
    .negatif { color: #C0392B !important; font-weight: bold; font-size: 18px; }
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; text-decoration: none; }
    div[data-testid="stNumberInput"] label { font-size: 13px !important; color: #333 !important; }
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
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

# --- 2. TCMB MOTORU (ENFLASYON + DÖVİZ) ---
@st.cache_data(ttl=3600)
def get_tcmb_data(api_key, start_date, end_date):
    res = {
        "TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, 
        "USD_ILK": 0.0, "USD_SON": 0.0, "USD_DEG": 0.0,
        "EUR_ILK": 0.0, "EUR_SON": 0.0, "EUR_DEG": 0.0,
        "Status": False, "Msg": "Veri Yok"
    }
    
    if not api_key: return res

    try:
        evds_service = evdsAPI(api_key)
        # Tarih Aralığını Geniş Tut (Veri eksiği olmasın)
        start_q = (start_date - relativedelta(months=2)).strftime("%d-%m-%Y")
        end_q = (end_date + relativedelta(months=1)).strftime("%d-%m-%Y")
        
        # SERİLER GÜNCELLENDİ: Döviz kurlarını da ekledik
        # TP.FG.J0: TÜFE, TP.TUFE1YI.T1: Yİ-ÜFE, TP.HKFE01.I1: H-ÜFE
        # TP.DK.USD.A.YTL: Dolar Alış, TP.DK.EUR.A.YTL: Euro Alış
        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1", "TP.DK.USD.A.YTL", "TP.DK.EUR.A.YTL"]
        
        raw_df = evds_service.get_data(series, startdate=start_q, enddate=end_q)
        if raw_df is None or raw_df.empty:
            res["Msg"] = "API Boş Döndü"
            return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m') if 'Tarih' in raw_df.columns else pd.to_datetime(raw_df['Tarih_Dt'])
        
        # 1. ENFLASYON (Aylık Period Mantığı)
        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')
        
        # Kolon Eşleştirme (Bazen _ bazen . döner)
        cols = raw_df.columns
        def find_col(k): return next((c for c in cols if k in c.replace("_", ".")), None)
        
        c_tufe = find_col("TP.FG.J0")
        c_ufe = find_col("TP.TUFE1YI.T1")
        c_hufe = find_col("TP.HKFE01.I1")
        c_usd = find_col("TP.DK.USD.A.YTL")
        c_eur = find_col("TP.DK.EUR.A.YTL")

        # Veriyi Al (Satır Filtreleme)
        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        
        # Fallback
        if row_start.empty: 
             mask = raw_df['Tarih_Dt'] >= pd.to_datetime(start_date)
             if mask.any(): row_start = raw_df.loc[mask].iloc[[0]]
             else: row_start = raw_df.iloc[[0]]

        if row_end.empty: row_end = raw_df.iloc[[-1]]

        def get_v(r, c): return float(r[c].values[0]) if c and pd.notna(r[c].values[0]) else 0.0

        # Enflasyon Hesapla
        tufe_s, tufe_e = get_v(row_start, c_tufe), get_v(row_end, c_tufe)
        ufe_s, ufe_e = get_v(row_start, c_ufe), get_v(row_end, c_ufe)
        hufe_s, hufe_e = get_v(row_start, c_hufe), get_v(row_end, c_hufe)

        def calc(n, o): return ((n-o)/o)*100 if o!=0 else 0.0

        res["TUFE"] = round(calc(tufe_e, tufe_s), 2)
        res["UFE"] = round(calc(ufe_e, ufe_s), 2)
        res["HUFE"] = round(calc(hufe_e, hufe_s), 2)

        # Döviz Değerlerini Kaydet (TCMB Resmi Kur)
        # Not: EVDS'den gelen veri aylık/günlük karışıksa en yakın değeri alır
        res["USD_ILK"], res["USD_SON"] = get_v(row_start, c_usd), get_v(row_end, c_usd)
        res["EUR_ILK"], res["EUR_SON"] = get_v(row_start, c_eur), get_v(row_end, c_eur)
        
        if res["USD_ILK"] > 0: res["USD_DEG"] = calc(res["USD_SON"], res["USD_ILK"])
        if res["EUR_ILK"] > 0: res["EUR_DEG"] = calc(res["EUR_SON"], res["EUR_ILK"])

        res["Status"] = True
        res["Msg"] = "TCMB Verileri Alındı"
        
    except Exception as e:
        res["Msg"] = f"Hata: {str(e)}"
    return res

# --- 3. PIYASA VERISI (SADECE BRENT VE ONS ALTIN) ---
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
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("📅 Tarih Aralığı")
    
    today = date.today()
    default_start = today - relativedelta(years=1)
    
    start_date = st.date_input("Başlangıç Tarihi", value=default_start)
    end_date = st.date_input("Bitiş Tarihi (Güncel)", value=today)
    
    if start_date >= end_date: st.error("Hata: Başlangıç < Bitiş olmalı")
    
    with st.spinner("TCMB Resmi Kur & Piyasa Verileri..."):
        # 1. TCMB'den Döviz ve Enflasyon Çek
        tcmb = get_tcmb_data(MY_API_KEY, start_date, end_date)
        # 2. Yahoo'dan Ons Altın ve Brent Çek
        piyasa = piyasa_verisi_al(start_date, end_date)
        # 3. Web'den Yakıt Çek
        yakit_data = guncel_akaryakit_cek()
    
    st.markdown("---")
    sozlesme_tutari = st.number_input("Sözleşme Tutarı (TL):", value=100000.0, step=1000.0, format="%.2f")
    d_key = f"{start_date}_{end_date}"

# ============================================================================
# GRAM ALTIN HESAPLAMA (TCMB KUR * SPOT ONS)
# ============================================================================
gram_ilk = 0.0
gram_son = 0.0
gram_deg = 0.0

if piyasa["ONS_ALTIN"]["ilk"] > 0 and tcmb["USD_ILK"] > 0:
    # Formül: (Ons * Dolar) / 31.1035
    gram_ilk = (piyasa["ONS_ALTIN"]["ilk"] * tcmb["USD_ILK"]) / 31.1035
    gram_son = (piyasa["ONS_ALTIN"]["son"] * tcmb["USD_SON"]) / 31.1035
    if gram_ilk > 0: gram_deg = ((gram_son - gram_ilk) / gram_ilk) * 100

# ============================================================================
# GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans & Sözleşme Kokpiti v4.0")
st.caption(f"Analiz Dönemi: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")

# Kutu Fonksiyonu
def kutu_goster(col, baslik, ilk, son, degisim, ikon, kaynak=""):
    with col:
        st.markdown(f"<div class='kutu'><div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:5px;'><div><span style='font-size:20px; margin-right:8px;'>{ikon}</span><b>{baslik}</b></div><small style='color:#999'>{kaynak}</small></div>", unsafe_allow_html=True)
        renk = "pozitif" if degisim >= 0 else "negatif"
        st.markdown(f"<div style='font-size:12px; color:#666 !important;'>Eski: {tr_fmt(ilk)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:baseline;'><span class='big-metric'>{tr_fmt(son)}</span><span class='{renk}'>%{degisim:.2f}</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
# Dövizleri TCMB verisinden gösteriyoruz
kutu_goster(k1, "USD/TL", tcmb["USD_ILK"], tcmb["USD_SON"], tcmb["USD_DEG"], "💵", "TCMB")
kutu_goster(k2, "EUR/TL", tcmb["EUR_ILK"], tcmb["EUR_SON"], tcmb["EUR_DEG"], "💶", "TCMB")
# Altını hesaplanan veriden gösteriyoruz
kutu_goster(k3, "Gram Altın", gram_ilk, gram_son, gram_deg, "🥇", "Hesap")
# Parite (Elle hesapla)
parite_ilk = tcmb["EUR_ILK"] / tcmb["USD_ILK"] if tcmb["USD_ILK"] > 0 else 0
parite_son = tcmb["EUR_SON"] / tcmb["USD_SON"] if tcmb["USD_SON"] > 0 else 0
parite_deg = ((parite_son-parite_ilk)/parite_ilk)*100 if parite_ilk > 0 else 0
kutu_goster(k4, "EUR/USD", parite_ilk, parite_son, parite_deg, "⚖️", "TCMB")

# ENERJİ
st.markdown("---")
col_link, _ = st.columns([1,3])
col_link.link_button("⛽ Petrol Ofisi Arşiv", "https://www.petrolofisi.com.tr/arsiv-fiyatlari")

st.markdown("### 🛢️ Enerji & Emtia")
e1, e2, e3, e4 = st.columns(4)
kutu_goster(e1, "Brent ($)", piyasa["BRENT_PETROL"]["ilk"], piyasa["BRENT_PETROL"]["son"], piyasa["BRENT_PETROL"]["degisim"], "🛢️", "Piyasa")

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
c_inf_title, c_inf_status = st.columns([2, 2])
with c_inf_status:
    if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
    else: st.warning(f"⚠️ {tcmb['Msg']}")

ec1, ec2, ec3, ec4, ec5 = st.columns(5)
tufe = ec1.number_input("TÜFE %", value=safe_float(tcmb["TUFE"]), key=f"t_{d_key}")
ufe = ec2.number_input("ÜFE %", value=safe_float(tcmb["UFE"]), key=f"u_{d_key}")
h_ufe = ec3.number_input("H-ÜFE %", value=safe_float(tcmb["HUFE"]), key=f"h_{d_key}")
iscilik = ec4.number_input("İşçilik %", value=0.0, help="Asgari Ücret", key=f"i_{d_key}")
abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")
ozel_oran = (tufe + ufe) / 2

# AKILLI ŞABLONLAR
st.markdown("---")
col_title_w, col_temp = st.columns([2, 2])
col_title_w.markdown("#### ⚖️ Sepet Ağırlıkları (Toplam 100 olmalı)")

sablonlar = {
    "Manuel Giriş": {},
    "🏗️ İnşaat/Tadilat (MEP)": {"tufe": 10, "ufe": 40, "usd": 30, "eur": 20},
    "🧹 Temizlik/Personel": {"iscilik": 80, "tufe": 20},
    "💻 IT/Lisanslama": {"usd": 80, "eur": 20},
    "🚛 Lojistik/Nakliye": {"dizel": 40, "iscilik": 30, "tufe": 30},
    "🍽️ Catering": {"tufe": 50, "iscilik": 30, "benzin": 20}
}
secilen_sablon = col_temp.selectbox("⚡ Hızlı Şablon Seç:", list(sablonlar.keys()))
def get_def(k, default=0): return sablonlar[secilen_sablon].get(k, 0) if secilen_sablon != "Manuel Giriş" else default

w1, w2, w3, w4 = st.columns(4)
w_ozel = w1.number_input("Karma %", value=get_def("mix", 0))
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
if toplam != 100: st.error(f"⚠️ Toplam: %{toplam} (100 olmalı)")

# HESAPLAMA
etkiler = [
    ("Karma", safe_float(ozel_oran), safe_float(w_ozel)), 
    ("TÜFE", safe_float(tufe), safe_float(w_tufe)), 
    ("ÜFE", safe_float(ufe), safe_float(w_ufe)), 
    ("H-ÜFE", safe_float(h_ufe), safe_float(w_hufe)),
    ("İşçilik", safe_float(iscilik), safe_float(w_iscilik)), 
    ("USD", safe_float(tcmb["USD_DEG"]), safe_float(w_usd)), 
    ("EUR", safe_float(tcmb["EUR_DEG"]), safe_float(w_eur)), 
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
r1.metric("Toplam Artış", f"%{zam:.2f}")
r2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
r3.metric("YENİ TUTAR", f"{tr_fmt(yeni)} TL", delta_color="normal")

# JARVIS YORUMU
df_temp = pd.DataFrame(etkiler, columns=["Kalem", "Degisim", "Agirlik"])
df_temp["Etki"] = (df_temp["Degisim"] * df_temp["Agirlik"]) / 100
df_sorted = df_temp.sort_values(by="Etki", ascending=False)
if not df_sorted.empty and zam > 0:
    top = df_sorted.iloc[0]
    st.markdown(f"""<div class="jarvis-note">💡 <b>Jarvis Analizi:</b> Fiyat farkını en çok şişiren kalem <b>{top['Kalem']}</b>. Tek başına <b>%{top['Etki']:.2f}</b> puan etki etti.</div>""", unsafe_allow_html=True)

# TABLO & EXCEL
st.markdown("---")
df = pd.DataFrame([{"Kalem":e[0], "Değişim %":e[1], "Ağırlık %":e[2], "Etki %":(e[1]*e[2])/100} for e in etkiler if e[2]>0])
t1, t2 = st.columns([3, 1])
with t1: st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)

with t2:
    st.write("")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Detay', index=False)
        pd.DataFrame({'Bilgi': ['Tarih', 'Eski', 'Yeni', 'Fark'], 'Deger': [f"{start_date} - {end_date}", sozlesme_tutari, yeni, fark]}).to_excel(writer, sheet_name='Ozet', index=False)
    st.download_button("📥 Excel Raporu İndir", data=buffer.getvalue(), file_name=f"Hakedis_{start_date}_{end_date}.xlsx", mime="application/vnd.ms-excel", type="primary")
