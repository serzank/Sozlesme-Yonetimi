import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime

# SSL Hatalarını Yoksay (Firewall takılmaması için)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
MY_API_KEY = "Uol1kIOQos"
ST_PAGE_TITLE = "SK - Procurement"

st.set_page_config(page_title=ST_PAGE_TITLE, layout="wide", page_icon="🚀")

# --- CSS (Görünüm) ---
st.markdown("""
    <style>
    .big-metric { font-size: 26px !important; font-weight: bold; color: #1E3D59; }
    .kutu { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1E3D59; margin-bottom: 10px; }
    .stButton button { width: 100%; background-color: #1E3D59; color: white; }
    div[data-testid="stNumberInput"] label { font-size: 13px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. TCMB VERİ MOTORU (SAF REQUESTS) ---
@st.cache_data(ttl=3600)
def tcmb_verilerini_al(api_key):
    """
    TCMB'den son 5 yılın TÜFE, ÜFE ve H-ÜFE endekslerini çeker.
    """
    # Tarih Aralığı (Son 60 Ay)
    end_date = datetime.now().strftime("%d-%m-%Y")
    start_date = (datetime.now() - pd.DateOffset(months=60)).strftime("%d-%m-%Y")
    
    # Kodlar: 
    # TP.FG.J0      = TÜFE (Genel)
    # TP.TUFE1YI.K1 = Yİ-ÜFE (Genel)
    # TP.HKFE01.I1  = H-ÜFE (Hizmet - Genel)
    series_code = "TP.FG.J0-TP.TUFE1YI.K1-TP.HKFE01.I1"
    
    url = f"https://evds2.tcmb.gov.tr/service/evds/series={series_code}&startDate={start_date}&endDate={end_date}&type=json&key={api_key}&frequency=1"
    
    try:
        # Tarayıcı gibi davran (Maskeleme)
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                df = pd.DataFrame(data["items"])
                
                # Gereksiz sütunları at, isimleri düzelt
                # TCMB bazen NULL değerleri string "null" olarak dönebilir, temizleyelim
                for col in ['TP_FG_J0', 'TP_TUFE1YI_K1', 'TP_HKFE01_I1']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Tarih formatı YYYY-A şeklinde gelir (Örn: 2024-1)
                return df
    except Exception as e:
        st.error(f"Bağlantı Hatası: {e}")
        
    return pd.DataFrame() # Hata varsa boş dön

# --- 2. HESAPLAMA MOTORU ---
def oran_hesapla(df, ay_geriye):
    """
    Verilen tablodan 'son veri' ile 'X ay önceki veriyi' bulup değişim oranını hesaplar.
    """
    sonuclar = {"TÜFE": 0.0, "ÜFE": 0.0, "H-ÜFE": 0.0, "Msg": "Veri Yok"}
    
    if df.empty:
        return sonuclar
        
    # Boş olmayan son satırı bul (En güncel veri)
    df_clean = df.dropna(subset=['TP_FG_J0', 'TP_TUFE1YI_K1'])
    
    if len(df_clean) < ay_geriye + 1:
        sonuclar["Msg"] = "Yetersiz Tarihçesi"
        return sonuclar
        
    son_veri = df_clean.iloc[-1]
    
    # Geçmiş veriyi bul (İndeksleme ile)
    # Eğer listede 100 satır var, biz 6 ay geriyi istiyorsak -> index -7
    idx_gecmis = -(ay_geriye + 1)
    gecmis_veri = df_clean.iloc[idx_gecmis]
    
    # Hesaplama Fonksiyonu: ((Yeni-Eski)/Eski)*100
    def calc(yeni, eski):
        try:
            return ((float(yeni) - float(eski)) / float(eski)) * 100
        except: return 0.0

    sonuclar["TÜFE"] = calc(son_veri['TP_FG_J0'], gecmis_veri['TP_FG_J0'])
    sonuclar["ÜFE"] = calc(son_veri['TP_TUFE1YI_K1'], gecmis_veri['TP_TUFE1YI_K1'])
    
    # H-ÜFE ayrı kontrol (Bazen geç açıklanır)
    try:
        val_h_son = df_clean['TP_HKFE01_I1'].iloc[-1]
        val_h_ilk = df_clean['TP_HKFE01_I1'].iloc[idx_gecmis]
        sonuclar["H-ÜFE"] = calc(val_h_son, val_h_ilk)
    except:
        sonuclar["H-ÜFE"] = 0.0
        
    sonuclar["Msg"] = f"{gecmis_veri['Tarih']} ➡️ {son_veri['Tarih']}"
    return sonuclar

# =========================================================
# ARAYÜZ (FRONTEND)
# =========================================================

# SOL MENÜ
with st.sidebar:
    st.header("⚙️ Ayarlar")
    
    # Dönem Seçimi
    donemler = {
        "1 Ay": 1,
        "3 Ay": 3,
        "6 Ay": 6,
        "1 Yıl (12 Ay)": 12,
        "2 Yıl (24 Ay)": 24
    }
    secilen_etiket = st.selectbox("Analiz Dönemi:", list(donemler.keys()))
    secilen_ay = donemler[secilen_etiket]
    
    st.markdown("---")
    tutar = st.number_input("Sözleşme Tutarı (TL):", value=100000.0, format="%.2f")

# ANA EKRAN
st.title("🚀 SK - Enflasyon & Sözleşme Kokpiti")

# 1. Verileri Çek
df_tcmb = tcmb_verilerini_al(MY_API_KEY)

# 2. Seçilen Döneme Göre Hesapla
oranlar = oran_hesapla(df_tcmb, secilen_ay)

# 3. Bilgi Çubuğu
st.info(f"📅 **Baz Alınan Dönem Aralığı:** {oranlar['Msg']}")

# 4. GÖSTERGE KUTULARI (TÜFE / ÜFE / H-ÜFE)
c1, c2, c3, c4 = st.columns(4)

def metric_kutu(col, baslik, deger):
    with col:
        st.markdown(f"""
        <div class="kutu">
            <div style="font-size:14px; color:#555;">{baslik}</div>
            <div class="big-metric">%{deger:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

metric_kutu(c1, "TÜFE (Tüketici)", oranlar["TÜFE"])
metric_kutu(c2, "Yİ-ÜFE (Üretici)", oranlar["ÜFE"])
metric_kutu(c3, "H-ÜFE (Hizmet)", oranlar["H-ÜFE"])

# Ortalama (TÜFE+ÜFE)/2
ortalama = (oranlar["TÜFE"] + oranlar["ÜFE"]) / 2
metric_kutu(c4, "Ortalama (T+Ü)/2", ortalama)

st.markdown("---")

# 5. SÖZLEŞME HESAPLAMA (AĞIRLIKLI)
st.subheader("⚖️ Sözleşme Fiyat Farkı Hesabı")

w1, w2, w3, w4 = st.columns(4)
a_tufe = w1.number_input("TÜFE Ağırlığı %", value=0)
a_ufe = w2.number_input("ÜFE Ağırlığı %", value=0)
a_hufe = w3.number_input("H-ÜFE Ağırlığı %", value=0)
a_ort = w4.number_input("Ortalama ((T+Ü)/2) %", value=100)

toplam_agirlik = a_tufe + a_ufe + a_hufe + a_ort

if toplam_agirlik != 100:
    st.error(f"⚠️ Ağırlıkların toplamı 100 olmalı! (Şu an: {toplam_agirlik})")
else:
    # Nihai Zam Oranı
    zam_orani = (
        (a_tufe * oranlar["TÜFE"]) + 
        (a_ufe * oranlar["ÜFE"]) + 
        (a_hufe * oranlar["H-ÜFE"]) + 
        (a_ort * ortalama)
    ) / 100
    
    fark_tl = tutar * (zam_orani / 100)
    yeni_tutar = tutar + fark_tl
    
    # Sonuç Gösterimi
    st.success(f"YENİ SÖZLEŞME TUTARI: {yeni_tutar:,.2f} TL")
    st.info(f"Uygulanan Zam: %{zam_orani:.2f} | Fiyat Farkı: {fark_tl:,.2f} TL")
    
    # Tablo
    st.write("Detaylı Döküm:")
    data = {
        "Kalem": ["TÜFE", "ÜFE", "H-ÜFE", "Ortalama"],
        "Dönemsel Artış (%)": [oranlar["TÜFE"], oranlar["ÜFE"], oranlar["H-ÜFE"], ortalama],
        "Sözleşme Ağırlığı (%)": [a_tufe, a_ufe, a_hufe, a_ort],
        "Fiyata Etkisi (%)": [
            (oranlar["TÜFE"]*a_tufe)/100, 
            (oranlar["ÜFE"]*a_ufe)/100, 
            (oranlar["H-ÜFE"]*a_hufe)/100, 
            (ortalama*a_ort)/100
        ]
    }
    
    # Sadece ağırlığı olanları göster
    df_sonuc = pd.DataFrame(data)
    df_sonuc = df_sonuc[df_sonuc["Sözleşme Ağırlığı (%)"] > 0]
    
    # Formatlama Hatasını Önleyen Yöntem
    st.dataframe(
        df_sonuc.style.format("{:.2f}"), 
        use_container_width=True
    )
