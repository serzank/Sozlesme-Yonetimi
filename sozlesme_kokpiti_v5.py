import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement", layout="wide", page_icon="⛽")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    .logo-text { font-size: 24px !important; font-weight: 900 !important; color: #D91E18 !important; font-family: 'Arial', sans-serif; margin-bottom: 20px; }
    .kutu { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #1E3D59; margin-bottom: 10px; }
    .kutu-enerji { background-color: #fffcf5; padding: 15px; border-radius: 8px; border-left: 5px solid #F39C12; margin-bottom: 10px; }
    .big-metric { font-size: 24px !important; font-weight: bold; color: #1E3D59; }
    .old-price { font-size: 13px !important; color: #888; }
    .prediction-tag { font-size: 11px; background-color: #e8f5e9; color: #2e7d32; padding: 2px 6px; border-radius: 4px; font-weight: bold; display: block; margin-bottom: 5px; }
    .header-style { background-color: #1E3D59; color: white; padding: 10px; border-radius: 5px; text-align: center; font-weight: bold; }
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; }
    
    /* Input alanlarını sıkılaştırma */
    div[data-testid="stNumberInput"] label { font-size: 13px; }
    div[data-testid="stNumberInput"] input { font-size: 14px; min-height: 0px; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYON: TÜRKÇE PARA FORMATI ---
def tr_fmt(deger):
    """
    Sayıyı 1.234,56 formatına çevirir.
    """
    if isinstance(deger, (int, float)):
        # Önce standart virgüllü format yap (1,234.56)
        s = "{:,.2f}".format(deger)
        # Sonra yer değiştir: Virgül -> X, Nokta -> Virgül, X -> Nokta
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return deger

# ============================================================================
# 1. SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("⚙️ Ayarlar")
    
    donem_secimi = st.selectbox("Analiz Dönemi:", ["1 Ay", "3 Ay", "6 Ay", "Yılbaşından Bugüne (YTD)", "1 Yıl"], index=0)
    period_map = {"1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "Yılbaşından Bugüne (YTD)": "ytd", "1 Yıl": "1y"}
    selected_period = period_map[donem_secimi]

    st.markdown("---")
    # Not: Input alanında teknik olarak nokta kullanmak zorundayız ama sonuçlar TR formatında olacak.
    sozlesme_tutari = st.number_input("Mevcut Sözleşme Tutarı (TL):", value=100000.0, format="%.2f")
    st.caption(f"Görünüm: {tr_fmt(sozlesme_tutari)} TL") # Kullanıcıya teyit için formatlı gösterim

# ============================================================================
# 2. VERİ ÇEKME MOTORU
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
    st.warning("⚠️ Firewall engeli. Manuel mod aktif.")
    for d in ["USDTRY", "EURTRY", "EURUSD", "ONS_ALTIN", "BRENT_PETROL", "GRAM_ALTIN_TL"]:
        if d not in piyasa: piyasa[d] = {"ilk": 0, "son": 0, "degisim": 0}

# ============================================================================
# 3. FİNANSAL GÖSTERGELER
# ============================================================================
st.title("⛽ Sözleşme & Enerji Kokpiti")
st.markdown(f"**Seçilen Dönem:** {donem_secimi}")

def kutu(col, baslik, key, ikon):
    val = piyasa.get(key, {"ilk":0, "son":0, "degisim":0})
    ilk, son, deg = val["ilk"], val["son"], val["degisim"]
    with col:
        st.markdown(f"<div class='kutu'><b>{ikon} {baslik}</b><br>", unsafe_allow_html=True)
        if son == 0: deg = st.number_input(f"{baslik} (%)", value=0.0, step=0.1, key=key)
        else:
            st.markdown(f"<span class='old-price'>Eski: {tr_fmt(ilk)}</span>", unsafe_allow_html=True)
            renk = "#27AE60" if deg >= 0 else "#C0392B"
            # Formatlı gösterim
            st.markdown(f"<span class='big-metric'>{tr_fmt(son)}</span> <span style='color:{renk};font-weight:bold'>%{deg:+.2f}</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    return deg

k1, k2, k3, k4 = st.columns(4)
d_usd = kutu(k1, "USD/TL", "USDTRY", "💵")
d_eur = kutu(k2, "EUR/TL", "EURTRY", "💶")
d_gram = kutu(k3, "Gram Altın (TL)", "GRAM_ALTIN_TL", "🥇")
d_parite = kutu(k4, "EUR/USD Parite", "EURUSD", "⚖️")

# ============================================================================
# 4. ENERJİ VE AKARYAKIT
# ============================================================================
st.markdown("---")
col_link_fuel, _ = st.columns([1,3])
col_link_fuel.link_button("⛽ Petrol Ofisi Arşiv Fiyatları", "https://www.petrolofisi.com.tr/arsiv-fiyatlari")

st.markdown("### 🛢️ Enerji & Akaryakıt")
e1, e2, e3, e4 = st.columns(4)

# 1. Brent Petrol (Otomatik)
d_brent = kutu(e1, "Brent Petrol ($)", "BRENT_PETROL", "🛢️")

# Referans Tahmin
ref_tahmin = d_brent + d_usd

# 2. Benzin (Fiyat Girişli)
with e2:
    st.markdown(f"<div class='kutu-enerji'><b>⛽ TR Benzin</b><br>", unsafe_allow_html=True)
    st.markdown(f"<span class='prediction-tag'>Brent'e Göre Olması Gereken: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    
    c_e1, c_e2 = st.columns(2)
    b_eski = c_e1.number_input("Eski (TL)", value=42.0, step=0.5, key="b_old")
    b_yeni = c_e2.number_input("Yeni (TL)", value=44.0, step=0.5, key="b_new")
    
    if b_eski > 0:
        d_benzin = ((b_yeni - b_eski) / b_eski) * 100
    else:
        d_benzin = 0.0
        
    renk = "#27AE60" if d_benzin >= 0 else "#C0392B"
    st.markdown(f"<div style='text-align:right; font-weight:bold; font-size:18px; color:{renk}'>%{d_benzin:.2f}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# 3. Motorin (Fiyat Girişli)
with e3:
    st.markdown(f"<div class='kutu-enerji'><b>🚛 TR Motorin</b><br>", unsafe_allow_html=True)
    st.markdown(f"<span class='prediction-tag'>Brent'e Göre Olması Gereken: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    
    c_d1, c_d2 = st.columns(2)
    m_eski = c_d1.number_input("Eski (TL)", value=43.0, step=0.5, key="m_old")
    m_yeni = c_d2.number_input("Yeni (TL)", value=45.0, step=0.5, key="m_new")
    
    if m_eski > 0:
        d_dizel = ((m_yeni - m_eski) / m_eski) * 100
    else:
        d_dizel = 0.0
        
    renk = "#27AE60" if d_dizel >= 0 else "#C0392B"
    st.markdown(f"<div style='text-align:right; font-weight:bold; font-size:18px; color:{renk}'>%{d_dizel:.2f}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# 4. Tahvil
kutu(e4, "ABD 10Y Tahvil", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON
# ============================================================================
st.markdown("---")
col_link_tuik, _ = st.columns([1,3])
col_link_tuik.link_button("🔗 Güncel TÜFE/ÜFE Verisi", "https://data.tuik.gov.tr/Search/Search?text=t%C3%BCfe")

st.markdown("### 📈 Enflasyon Endeksleri")
ec1, ec2, ec3, ec4, ec5 = st.columns(5)
tufe = ec1.number_input("TÜFE (%)", value=3.45)
ufe = ec2.number_input("ÜFE (Mal) (%)", value=4.15)
h_ufe = ec3.number_input("H-ÜFE (Hizmet) (%)", value=5.00)
abd_enf = ec4.number_input("ABD Enf. (%)", value=0.4)
eu_enf = ec5.number_input("Euro Enf. (%)", value=0.3)
ozel_oran = (tufe + ufe) / 2

# ============================================================================
# 6. SEPET & HESAPLAMA
# ============================================================================
st.markdown("---")
st.markdown('<div class="header-style">⚖️ SÖZLEŞME AĞIRLIK SEPETİ</div>', unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
c6, c7, c8, c9, c10 = st.columns(5)

w_ozel = c1.number_input("Karma (TÜFE+ÜFE)/2 %", value=0)
w_tufe = c2.number_input("Saf TÜFE %", value=40)
w_ufe = c3.number_input("Saf ÜFE %", value=0)
w_hufe = c4.number_input("Saf H-ÜFE %", value=20)
w_usd = c5.number_input("USD %", value=20)
w_eur = c6.number_input("EUR %", value=10)
w_brent = c7.number_input("Brent Petrol %", value=0)
w_benzin = c8.number_input("TR Benzin %", value=0)
w_dizel = c9.number_input("TR Motorin %", value=10)
w_altin = c10.number_input("Altın %", value=0)

toplam_agirlik = w_ozel+w_tufe+w_ufe+w_hufe+w_usd+w_eur+w_brent+w_benzin+w_dizel+w_altin

if toplam_agirlik != 100:
    st.error(f"⚠️ Toplam Ağırlık: %{toplam_agirlik}. Lütfen 100 yapınız.")
else:
    # Hesaplama
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
    
    st.markdown("---")
    res1, res2, res3 = st.columns(3)
    
    # SONUÇLARI TÜRKÇE FORMATLA GÖSTERİYORUZ (tr_fmt)
    res1.metric("Genel Artış Oranı", f"%{zam:.2f}")
    res2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
    res3.metric("YENİ TUTAR", f"{tr_fmt(yeni_tutar)} TL")
    
    st.markdown("#### 📋 Sepet Detayı")
    data = {
        "Kalem": ["TÜFE+ÜFE/2", "TÜFE", "ÜFE", "H-ÜFE", "Dolar", "Euro", "Brent", "Benzin (TR)", "Motorin (TR)", "Altın"],
        "Değişim (%)": [ozel_oran, tufe, ufe, h_ufe, d_usd, d_eur, d_brent, d_benzin, d_dizel, d_gram],
        "Ağırlık (%)": [w_ozel, w_tufe, w_ufe, w_hufe, w_usd, w_eur, w_brent, w_benzin, w_dizel, w_altin]
    }
    df = pd.DataFrame(data)
    df = df[df["Ağırlık (%)"] > 0]
    df["Fiyata Etkisi (%)"] = (df["Değişim (%)"] * df["Ağırlık (%)"]) / 100
    
    # Dataframe'deki sayıları da TR formatına çeviriyoruz
    # Not: Dataframe'i string'e çevirdiğimiz için sıralama bozulabilir, bu sadece görsel tablo
    df_gorsel = df.copy()
    for col in ["Değişim (%)", "Fiyata Etkisi (%)"]:
        df_gorsel[col] = df_gorsel[col].apply(lambda x: f"{x:.2f}".replace(".", ","))
    df_gorsel["Ağırlık (%)"] = df_gorsel["Ağırlık (%)"].apply(lambda x: f"{x:.0f}")

    st.dataframe(df_gorsel, use_container_width=True)