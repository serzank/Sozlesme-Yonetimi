import streamlit as st
import pandas as pd
import yfinance as yf
import evds
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import urllib3
import numpy as np

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
MY_API_KEY = "Uol1kIOQos"

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement", layout="wide", page_icon="🚀")

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

# --- TCMB MOTORU (TARİH ARALIĞI MODU) ---
@st.cache_data(ttl=3600)
def get_tcmb_date_range(api_key, start_d, end_d):
    # Başlangıç
    res = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Yok"}
    
    if not api_key: return res

    try:
        evds_api = evds.evdsAPI(api_key)
        
        # API için tarih formatı (DD-MM-YYYY)
        # Geniş aralık çekelim ki "o gün veri yoktu" demesin
        q_start = (start_d - relativedelta(months=2)).strftime("%d-%m-%Y")
        q_end = (end_d + relativedelta(months=1)).strftime("%d-%m-%Y")
        
        # Kodlar: TP.FG.J0 (TÜFE), TP.TUFE1YI.T1 (Yİ-ÜFE), TP.HKFE01.I1 (H-ÜFE)
        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1"]
        
        raw_df = evds_api.get_data(series, startdate=q_start, enddate=q_end)
        
        if raw_df is None or raw_df.empty:
            res["Msg"] = "API Boş Döndü"
            return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
        
        # HEDEF AYLARI BELİRLE (Period)
        p_start = pd.Period(start_d, freq='M')
        p_end = pd.Period(end_d, freq='M')
        
        # Gelecek tarihi seçtiysek son veriye çek
        max_date = raw_df['Tarih_Dt'].max()
        if p_end > pd.Period(max_date, freq='M'):
            p_end = pd.Period(max_date, freq='M')
            
        # Satırları Bul
        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        
        # Fallback: Eğer tam başlangıç ayı yoksa bir sonrakini dene
        if row_start.empty:
            mask = raw_df['Tarih_Dt'] >= pd.to_datetime(start_d)
            if mask.any():
                row_start = raw_df.loc[mask].iloc[[0]]
                p_start = pd.Period(row_start['Tarih_Dt'].values[0], freq='M')
        
        # Fallback: Bitiş ayı yoksa bir öncekini dene
        if row_end.empty:
            row_end = raw_df.iloc[[-1]]
            p_end = pd.Period(row_end['Tarih_Dt'].values[0], freq='M')
        
        if row_start.empty or row_end.empty:
            res["Msg"] = "Tarih Aralığı Bulunamadı"
            return res

        # Sütun İsim Kontrolü
        cols = raw_df.columns
        c_t = "TP_FG_J0" if "TP_FG_J0" in cols else "TP.FG.J0"
        c_u = "TP_TUFE1YI_T1" if "TP_TUFE1YI_T1" in cols else "TP.TUFE1YI.T1"
        c_h = "TP_HKFE01_I1" if "TP_HKFE01_I1" in cols else "TP.HKFE01.I1"
        
        def get_val(row, c):
            if c in row.columns and pd.notna(row[c].values[0]):
                return float(row[c].values[0])
            return 0.0

        t_start = get_val(row_start, c_t)
        t_end = get_val(row_end, c_t)
        
        u_start = get_val(row_start, c_u)
        u_end = get_val(row_end, c_u)
        
        h_start = get_val(row_start, c_h)
        h_end = get_val(row_end, c_h)
        
        def calc(n, o):
            if o == 0: return 0.0
            return ((n - o) / o) * 100
            
        res["TUFE"] = round(calc(t_end, t_start), 2)
        res["UFE"] = round(calc(u_end, u_start), 2)
        res["HUFE"] = round(calc(h_end, h_start), 2)
        
        res["Status"] = True
        res["Msg"] = f"{p_start} ➡️ {p_end}"
        
    except Exception as e:
        res["Msg"] = f"Hata: {str(e)}"
        
    return res


# ============================================================================
# SOL MENÜ (TARİH SEÇİCİ)
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("📅 Tarih Aralığı")
    
    # 1. TARİH SEÇİMİ (DROPDOWN YOK, TAKVİM VAR)
    today = date.today()
    default_start = today - relativedelta(years=1)
    
    start_date = st.date_input("Başlangıç Tarihi", value=default_start)
    end_date = st.date_input("Bitiş Tarihi (Güncel)", value=today)
    
    if start_date >= end_date:
        st.error("Hata: Başlangıç, Bitişten küçük olmalı!")
    
    # VERİ ÇEK (Artık fonksiyon ismi doğru)
    with st.spinner("Veriler Hesaplanıyor..."):
        tcmb = get_tcmb_date_range(MY_API_KEY, start_date, end_date)

    st.markdown("---")
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    try: sozlesme_tutari = float(tutar_giris.replace(".", "").replace(",", "."))
    except: sozlesme_tutari = 0.0
    
    # Widget Key için tarih stringi
    d_key = f"{start_date}_{end_date}"

# ============================================================================
# 2. YAHOO VERİ (TARİHLİ)
# ============================================================================
@st.cache_data(ttl=600)
def piyasa_verisi_al(d_start, d_end):
    tickers = { "USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "EURUSD": "EURUSD=X", "ONS_ALTIN": "GC=F", "BRENT_PETROL": "BZ=F", "ABD_TAHVIL": "^TNX" }
    data_dict = {}
    
    for k in tickers: data_dict[k] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}

    try:
        # Yahoo'ya tarih aralığını veriyoruz
        df = yf.download(list(tickers.values()), start=d_start, end=d_end + timedelta(days=1), progress=False)['Close']
        df = df.fillna(method='ffill').fillna(method='bfill')
        
        if not df.empty:
            for key, symbol in tickers.items():
                try:
                    c_name = [c for c in df.columns if symbol in str(c)]
                    if not c_name: continue
                    seri = df[c_name[0]]
                    if len(seri) > 0:
                        ilk = float(seri.iloc[0]) # Seçilen Başlangıçtaki kur
                        son = float(seri.iloc[-1]) # Seçilen Bitişteki kur
                        if ilk > 0:
                            degisim = ((son - ilk) / ilk) * 100
                            data_dict[key] = {"ilk": ilk, "son": son, "degisim": degisim}
                except: pass
            
            # Gram Altın
            if data_dict["ONS_ALTIN"]["son"] > 0 and data_dict["USDTRY"]["son"] > 0:
                g_son = (data_dict["ONS_ALTIN"]["son"] / 31.1035) * data_dict["USDTRY"]["son"]
                g_ilk = (data_dict["ONS_ALTIN"]["ilk"] / 31.1035) * data_dict["USDTRY"]["ilk"]
                g_deg = 0.0
                if g_ilk > 0:
                    g_deg = ((g_son - g_ilk) / g_ilk) * 100
                data_dict["GRAM_ALTIN_TL"] = {"ilk": g_ilk, "son": g_son, "degisim": g_deg}
    except: pass
    return data_dict

piyasa = piyasa_verisi_al(start_date, end_date)
if "GRAM_ALTIN_TL" not in piyasa: 
    piyasa["GRAM_ALTIN_TL"] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}

# ============================================================================
# 3. GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans & Sözleşme Kokpiti")
st.caption(f"Aralık: {start_date.strftime('%d.%m.%Y')} ➡️ {end_date.strftime('%d.%m.%Y')}")

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

# ENERJİ
st.markdown("---")
col_link, _ = st.columns([1,3])
col_link.link_button("⛽ Petrol Ofisi Arşiv", "https://www.petrolofisi.com.tr/arsiv-fiyatlari")

st.markdown("### 🛢️ Enerji")
e1, e2, e3, e4 = st.columns(4)
d_brent = kutu(e1, "Brent ($)", "BRENT_PETROL", "🛢️")
ref_tahmin = d_brent + d_usd

with e2:
    st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    b_eski = st.number_input("Eski", value=42.0, key=f"bo_{d_key}")
    b_yeni = st.number_input("Yeni", value=44.0, key=f"bn_{d_key}")
    d_benzin = 0.0
    if b_eski > 0: d_benzin = ((b_yeni-b_eski)/b_eski)*100
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    m_eski = st.number_input("Eski", value=43.0, key=f"mo_{d_key}")
    m_yeni = st.number_input("Yeni", value=45.0, key=f"mn_{d_key}")
    d_dizel = 0.0
    if m_eski > 0: d_dizel = ((m_yeni-m_eski)/m_eski)*100
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON (TARİHLİ MOD)
# ============================================================================
st.markdown("---")
tab1, tab2 = st.tabs(["⚡ Otomatik Hesap", "🔗 Diğer Site"])

with tab1:
    c_inf_title, c_inf_status = st.columns([2, 2])
    with c_inf_status:
        if tcmb["Status"]: st.success(f"✅ {tcmb['Msg']}")
        else: st.warning(f"⚠️ {tcmb['Msg']}")

    ec1, ec2, ec3, ec4, ec5 = st.columns(5)
    # Otomatik veriler
    tufe = ec1.number_input("TÜFE %", value=safe_float(tcmb["TUFE"]), key=f"t_{d_key}")
    ufe = ec2.number_input("ÜFE %", value=safe_float(tcmb["UFE"]), key=f"u_{d_key}")
    h_ufe = ec3.number_input("H-ÜFE %", value=safe_float(tcmb["HUFE"]), key=f"h_{d_key}")
    iscilik = ec4.number_input("İşçilik %", value=0.0, help="Asgari Ücret", key=f"i_{d_key}")
    abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{d_key}")
    ozel_oran = (tufe + ufe) / 2

with tab2:
    st.info("Manuel kontrol için:")
    st.components.v1.iframe("https://tufehesaplama-serzan.streamlit.app/", height=500, scrolling=True)

# ============================================================================
# 6. SEPET VE HESAPLAMA
# ============================================================================
st.markdown("---")
st.markdown("#### ⚖️ Sepet Ağırlıkları (Toplam 100 olmalı)")

w1, w2, w3, w4 = st.columns(4)
w_ozel = w1.number_input("Karma (Mix) %", value=0)
w_tufe = w2.number_input("Saf TÜFE %", value=30)
w_ufe = w3.number_input("Saf ÜFE %", value=0)
w_hufe = w4.number_input("H-ÜFE %", value=10)

w5, w6, w7, w8 = st.columns(4)
w_iscilik = w5.number_input("İşçilik %", value=30)
w_usd = w6.number_input("USD %", value=20)
w_eur = w7.number_input("EUR %", value=10)
w_altin = w8.number_input("Altın %", value=0)

w9, w10, w11, w12 = st.columns(4)
w_benzin = w9.number_input("Benzin %", value=0)
w_dizel = w10.number_input("Motorin %", value=0)
w_brent = w11.number_input("Brent %", value=0)
w_abd = w12.number_input("ABD Enf. %", value=0)

toplam = w_ozel+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd

if toplam != 100:
    st.error(f"⚠️ Toplam Ağırlık: %{toplam} (100 olmalı)")
else:
    # NaN HATASI ÇÖZÜMÜ
    etkiler = [
        ("Karma", safe_float(ozel_oran), safe_float(w_ozel)), 
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
            data["Kalem"].append(ad)
            data["Değişim %"].append(deg)
            data["Ağırlık %"].append(agr)
            data["Etki %"].append((deg*agr)/100)
            
    df = pd.DataFrame(data)
    st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
