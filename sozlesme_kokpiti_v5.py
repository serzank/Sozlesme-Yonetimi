import streamlit as st
import pandas as pd
import yfinance as yf
import evds
from datetime import datetime, date

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement", layout="wide", page_icon="⛽")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    .logo-text { font-size: 22px !important; font-weight: 900 !important; color: #D91E18 !important; font-family: sans-serif; margin-bottom: 20px; }
    .kutu, .kutu-enerji { padding: 15px; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; color: #1E3D59 !important; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; color: #1E3D59 !important; }
    .kutu *, .kutu-enerji * { color: #1E3D59 !important; }
    .pozitif { color: #27AE60 !important; font-weight: bold; font-size: 18px; }
    .negatif { color: #C0392B !important; font-weight: bold; font-size: 18px; }
    .prediction-tag { font-size: 11px; background-color: #e8f5e9 !important; color: #2e7d32 !important; padding: 3px 6px; border-radius: 4px; font-weight: bold; display: inline-block; margin-bottom: 4px; }
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; text-decoration: none; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def tr_fmt(deger):
    if isinstance(deger, (int, float)):
        s = "{:,.2f}".format(deger)
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return deger

# --- TCMB GENİŞ ARALIKLI VERİ ÇEKME (v15.0) ---
@st.cache_data(ttl=3600)
def get_dynamic_inflation(api_key, donem_adi):
    # Varsayılan
    result = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": ""}
    
    if not api_key:
        result["Msg"] = "Anahtar Yok"
        return result

    try:
        evds_api = evds.evdsAPI(api_key)
        
        # STRATEJİ DEĞİŞİKLİĞİ: Son 24 ayı komple çek, Python ile filtrele.
        # Bu yöntem "tarih bulunamadı" hatasını engeller.
        end_date = datetime.now().strftime("%d-%m-%Y")
        start_date = (datetime.now() - pd.DateOffset(months=24)).strftime("%d-%m-%Y")
        
        # Kodlar: TÜFE, Yİ-ÜFE, H-ÜFE
        series = ['TP.FG.J0', 'TP.TUFE1YI.K1', 'TP.HKFE01.I1']
        df = evds_api.get_data(series, startdate=start_date, enddate=end_date)
        
        if df is None or df.empty:
            result["Msg"] = "API Bağlandı ama veri boş"
            return result
            
        # Sadece TÜFE ve ÜFE dolu olan satırları al (H-ÜFE bazen eksik olabilir, onu ayrı tut)
        df_clean = df.dropna(subset=['TP_FG_J0', 'TP_TUFE1YI_K1']).copy()
        
        if len(df_clean) < 2:
            result["Msg"] = "Yetersiz Veri (Satır < 2)"
            return result

        # --- DÖNEM SEÇİMİ ---
        # Veriler sondan başa doğru (En son tarih en altta)
        son_veri = df_clean.iloc[-1]
        
        # Kaç ay geriye gideceğiz?
        lookback = 1
        if donem_adi == "3 Ay": lookback = 3
        elif donem_adi == "6 Ay": lookback = 6
        elif donem_adi == "1 Yıl": lookback = 12
        elif donem_adi == "Yılbaşından Bugüne (YTD)":
            bugun_ay = datetime.now().month
            # Yılbaşından beri geçen ay sayısı (Ocak=1 ise lookback=1)
            lookback = bugun_ay if len(df_clean) >= bugun_ay else len(df_clean)-1

        # İndeks Hesaplama (Listeden taşmamak için kontrol)
        if lookback >= len(df_clean):
            ilk_veri = df_clean.iloc[0] # Yeterince veri yoksa en başı al
        else:
            ilk_veri = df_clean.iloc[-(lookback + 1)] 
        
        # --- HESAPLAMA ---
        # ((Yeni - Eski) / Eski) * 100
        
        # 1. TÜFE
        try:
            t_son = float(son_veri['TP_FG_J0'])
            t_ilk = float(ilk_veri['TP_FG_J0'])
            result["TUFE"] = round(((t_son - t_ilk) / t_ilk) * 100, 2)
        except: result["TUFE"] = 0.0

        # 2. ÜFE
        try:
            u_son = float(son_veri['TP_TUFE1YI_K1'])
            u_ilk = float(ilk_veri['TP_TUFE1YI_K1'])
            result["UFE"] = round(((u_son - u_ilk) / u_ilk) * 100, 2)
        except: result["UFE"] = 0.0
        
        # 3. H-ÜFE (Hata verirse 0 geç)
        try:
            # H-ÜFE verisi bazen ana tabloda NaN olabilir, orijinal df'den kontrol edelim
            h_series = df['TP_HKFE01.I1'].dropna()
            if len(h_series) > lookback:
                h_son = float(h_series.iloc[-1])
                h_ilk = float(h_series.iloc[-(lookback + 1)])
                result["HUFE"] = round(((h_son - h_ilk) / h_ilk) * 100, 2)
        except: result["HUFE"] = 0.0

        result["Status"] = True
        result["Msg"] = f"Veri: {ilk_veri['Tarih']} - {son_veri['Tarih']}"
        
    except Exception as e:
        result["Msg"] = f"Hata: {str(e)}"
        
    return result

# ============================================================================
# 1. SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("⚙️ Ayarlar")
    
    tcmb_key = st.text_input("TCMB API Anahtarı:", type="password", placeholder="Anahtarı buraya yapıştırın...")
    
    st.markdown("---")
    donem_secimi = st.selectbox("Analiz Dönemi:", ["1 Ay", "3 Ay", "6 Ay", "Yılbaşından Bugüne (YTD)", "1 Yıl"], index=0)
    
    # ENFLASYON ÇEKME (Yeni Fonksiyon)
    if tcmb_key:
        with st.spinner("TCMB Verisi Taranıyor..."):
            tcmb_data = get_dynamic_inflation(tcmb_key, donem_secimi)
    else:
        tcmb_data = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Anahtar Yok"}

    period_map = {"1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "Yılbaşından Bugüne (YTD)": "ytd", "1 Yıl": "1y"}
    selected_period = period_map[donem_secimi]

    st.markdown("---")
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    try:
        temiz_tutar = tutar_giris.replace(".", "").replace(",", ".")
        sozlesme_tutari = float(temiz_tutar)
    except:
        st.error("Lütfen geçerli bir sayı giriniz")
        sozlesme_tutari = 0.0

# ============================================================================
# 2. YAHOO VERİ ÇEKME
# ============================================================================
@st.cache_data(ttl=600)
def piyasa_verisi_al(periyot):
    tickers = {
        "USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "EURUSD": "EURUSD=X",
        "ONS_ALTIN": "GC=F", "BRENT_PETROL": "BZ=F", "ABD_TAHVIL": "^TNX"
    }
    data_dict = {}
    hata = False
    try:
        df = yf.download(list(tickers.values()), period=periyot, progress=False)['Close']
        if df.empty:
            hata = True
        else:
            for key, symbol in tickers.items():
                try:
                    col_name = symbol
                    if col_name not in df.columns:
                        col_temp = [c for c in df.columns if symbol in str(c)]
                        if col_temp: col_name = col_temp[0]
                        else: continue
                    seri = df[col_name].dropna()
                    if len(seri) > 1:
                        ilk, son = float(seri.iloc[0]), float(seri.iloc[-1])
                        degisim = ((son - ilk) / ilk) * 100
                        data_dict[key] = {"ilk": ilk, "son": son, "degisim": degisim}
                    else: data_dict[key] = {"ilk": 0, "son": 0, "degisim": 0}
                except: data_dict[key] = {"ilk": 0, "son": 0, "degisim": 0}
            
            if "ONS_ALTIN" in data_dict and "USDTRY" in data_dict:
                g_son = (data_dict["ONS_ALTIN"]["son"] / 31.1035) * data_dict["USDTRY"]["son"]
                g_ilk = (data_dict["ONS_ALTIN"]["ilk"] / 31.1035) * data_dict["USDTRY"]["ilk"]
                g_deg = ((g_son - g_ilk) / g_ilk) * 100 if g_ilk > 0 else 0
                data_dict["GRAM_ALTIN_TL"] = {"ilk": g_ilk, "son": g_son, "degisim": g_deg}
    except: hata = True
    return data_dict, hata

piyasa, hata = piyasa_verisi_al(selected_period)
if hata:
    st.warning("⚠️ Yahoo verisi alınamadı.")
    for d in ["USDTRY", "EURTRY", "EURUSD", "ONS_ALTIN", "BRENT_PETROL", "GRAM_ALTIN_TL"]:
        if d not in piyasa: piyasa[d] = {"ilk": 0, "son": 0, "degisim": 0}

# ============================================================================
# 3. GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans Kokpiti")
st.markdown(f"**Dönem:** {donem_secimi}")

def kutu(col, baslik, key, ikon):
    val = piyasa.get(key, {"ilk":0, "son":0, "degisim":0})
    ilk, son, deg = val["ilk"], val["son"], val["degisim"]
    with col:
        st.markdown(f"""
        <div class='kutu'>
            <div style='display:flex; align-items:center; margin-bottom:5px;'>
                <span style='font-size:20px; margin-right:8px;'>{ikon}</span>
                <b style='font-size:16px;'>{baslik}</b>
            </div>
        """, unsafe_allow_html=True)
        
        if son == 0: deg = st.number_input(f"{baslik} (%)", value=0.0, step=0.1, key=key)
        else:
            renk_class = "pozitif" if deg >= 0 else "negatif"
            st.markdown(f"<div style='font-size:12px; color:#666 !important;'>Eski: {tr_fmt(ilk)}</div>", unsafe_allow_html=True)
            st.markdown(f"""
                <div style='display:flex; justify-content:space-between; align-items:baseline;'>
                    <span style='font-size:22px; font-weight:bold; color:#1E3D59 !important;'>{tr_fmt(son)}</span>
                    <span class='{renk_class}'>%{deg:+.2f}</span>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    return deg

k1, k2, k3, k4 = st.columns(4)
d_usd = kutu(k1, "USD/TL", "USDTRY", "💵")
d_eur = kutu(k2, "EUR/TL", "EURTRY", "💶")
d_gram = kutu(k3, "Gram Altın", "GRAM_ALTIN_TL", "🥇")
d_parite = kutu(k4, "EUR/USD", "EURUSD", "⚖️")

# ============================================================================
# 4. ENERJİ
# ============================================================================
st.markdown("---")
col_link_fuel, _ = st.columns([1,3])
col_link_fuel.link_button("⛽ Petrol Ofisi Arşiv", "https://www.petrolofisi.com.tr/arsiv-fiyatlari")

st.markdown("### 🛢️ Enerji")
e1, e2, e3, e4 = st.columns(4)

d_brent = kutu(e1, "Brent ($)", "BRENT_PETROL", "🛢️")
ref_tahmin = d_brent + d_usd

with e2:
    st.markdown(f"""
    <div class='kutu-enerji'>
        <div style='display:flex; align-items:center;'>
             <span style='font-size:20px; margin-right:8px;'>⛽</span> <b>Benzin</b>
        </div>
        <span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>
    """, unsafe_allow_html=True)
    b_eski = st.number_input("Eski (TL)", value=42.0, step=0.5, key="b_o")
    b_yeni = st.number_input("Yeni (TL)", value=44.0, step=0.5, key="b_n")
    if b_eski > 0: d_benzin = ((b_yeni - b_eski) / b_eski) * 100
    else: d_benzin = 0.0
    renk_class = "pozitif" if d_benzin >= 0 else "negatif"
    st.markdown(f"<div style='text-align:right;'><span class='{renk_class}'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    st.markdown(f"""
    <div class='kutu-enerji'>
        <div style='display:flex; align-items:center;'>
             <span style='font-size:20px; margin-right:8px;'>🚛</span> <b>Motorin</b>
        </div>
        <span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>
    """, unsafe_allow_html=True)
    m_eski = st.number_input("Eski (TL)", value=43.0, step=0.5, key="m_o")
    m_yeni = st.number_input("Yeni (TL)", value=45.0, step=0.5, key="m_n")
    if m_eski > 0: d_dizel = ((m_yeni - m_eski) / m_eski) * 100
    else: d_dizel = 0.0
    renk_class = "pozitif" if d_dizel >= 0 else "negatif"
    st.markdown(f"<div style='text-align:right;'><span class='{renk_class}'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON (DİNAMİK + GENİŞ ARALIK)
# ============================================================================
st.markdown("---")
c_inf_title, c_inf_status = st.columns([2, 2])
with c_inf_title:
    st.markdown("### 📈 Enflasyon & Sepet")
with c_inf_status:
    if tcmb_data["Status"]:
        st.success(f"✅ {tcmb_data['Msg']}")
    else:
        # Hata mesajını daha detaylı göster
        st.error(f"⚠️ {tcmb_data['Msg']}")

ec1, ec2, ec3, ec4 = st.columns(4)

# Değerleri Otomatik Doldur
tufe = ec1.number_input("TÜFE %", value=tcmb_data["TUFE"])
ufe = ec2.number_input("ÜFE %", value=tcmb_data["UFE"])
h_ufe = ec3.number_input("H-ÜFE %", value=tcmb_data["HUFE"])
abd_enf = ec4.number_input("ABD Enf.%", value=0.4)
ozel_oran = (tufe + ufe) / 2

st.markdown("---")
st.markdown("#### ⚖️ Sepet Ağırlıkları (Toplam 100 olmalı)")

w1, w2, w3 = st.columns(3)
w_ozel = w1.number_input("Karma (Mix) %", value=0)
w_tufe = w2.number_input("Saf TÜFE %", value=40)
w_ufe = w3.number_input("Saf ÜFE %", value=0)

w4, w5, w6 = st.columns(3)
w_hufe = w4.number_input("H-ÜFE %", value=20)
w_usd = w5.number_input("USD %", value=20)
w_eur = w6.number_input("EUR %", value=10)

w7, w8, w9 = st.columns(3)
w_benzin = w7.number_input("Benzin %", value=0)
w_dizel = w8.number_input("Motorin %", value=10)
w_brent = w9.number_input("Brent %", value=0)
w_altin = st.number_input("Altın %", value=0)

toplam_agirlik = w_ozel+w_tufe+w_ufe+w_hufe+w_usd+w_eur+w_brent+w_benzin+w_dizel+w_altin

if toplam_agirlik != 100:
    st.error(f"⚠️ Toplam: %{toplam_agirlik}")
else:
    etki_ozel = w_ozel * ozel_oran
    etki_tufe = w_tufe * tufe
    etki_ufe = w_ufe * ufe
    etki_hufe = w_hufe * h_ufe
    etki_usd = w_usd * d_usd
    etki_eur = w_eur * d_eur
    etki_brent = w_brent * d_brent
    etki_benzin = w_benzin * d_benzin
    etki_dizel = w_dizel * d_dizel
    etki_altin = w_altin * d_gram 
    
    zam = (etki_ozel + etki_tufe + etki_ufe + etki_hufe + etki_usd + etki_eur + etki_brent + etki_benzin + etki_dizel + etki_altin) / 100
    fark = sozlesme_tutari * (zam / 100)
    yeni_tutar = sozlesme_tutari + fark
    
    st.success(f"YENİ TUTAR: {tr_fmt(yeni_tutar)} TL")
    st.info(f"Fark: {tr_fmt(fark)} TL (+%{zam:.2f})")
    
    data = {
        "Kalem": ["TÜFE+ÜFE/2", "TÜFE", "ÜFE", "H-ÜFE", "Dolar", "Euro", "Brent", "Benzin", "Motorin", "Altın"],
        "Değişim %": [ozel_oran, tufe, ufe, h_ufe, d_usd, d_eur, d_brent, d_benzin, d_dizel, d_gram],
        "Ağırlık %": [w_ozel, w_tufe, w_ufe, w_hufe, w_usd, w_eur, w_brent, w_benzin, w_dizel, w_altin]
    }
    df = pd.DataFrame(data)
    df = df[df["Ağırlık %"] > 0]
    df["Etki %"] = (df["Değişim %"] * df["Ağırlık %"]) / 100
    
    st.dataframe(
        df.style.format({
            "Değişim %": "{:.2f}",
            "Ağırlık %": "{:.0f}",
            "Etki %": "{:.2f}"
        }),
        use_container_width=True
    )
