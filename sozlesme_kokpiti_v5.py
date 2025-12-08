import streamlit as st
import pandas as pd
import evds
from datetime import datetime

# --- YAPILANDIRMA ---
MY_API_KEY = "Uol1kIOQos"  # Sizin Anahtarınız

st.set_page_config(page_title="SK - Enflasyon Kokpiti", layout="wide", page_icon="📈")

# --- CSS ---
st.markdown("""
    <style>
    .main-header { font-size: 24px; font-weight: bold; color: #1E3D59; }
    .kutu { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #1E3D59; margin-bottom: 10px; }
    div[data-testid="stMetricValue"] { font-size: 20px; color: #1E3D59; }
    </style>
    """, unsafe_allow_html=True)

# --- VERİ ÇEKME MOTORU ---
@st.cache_data(ttl=3600)
def tcmb_verilerini_getir():
    try:
        evds_api = evds.evdsAPI(MY_API_KEY)
        
        # Son 5 Yılın verisini çek (Geniş havuz)
        end = datetime.now().strftime("%d-%m-%Y")
        start = (datetime.now() - pd.DateOffset(months=60)).strftime("%d-%m-%Y")
        
        # Kodlar: TÜFE(TP.FG.J0), Yİ-ÜFE(TP.TUFE1YI.K1), H-ÜFE(TP.HKFE01.I1)
        series = ['TP.FG.J0', 'TP.TUFE1YI.K1', 'TP.HKFE01.I1']
        
        df = evds_api.get_data(series, startdate=start, enddate=end)
        
        if df is None or df.empty:
            return None, "Boş veri döndü."

        # Temizlik
        df.dropna(subset=['TP_FG_J0', 'TP_TUFE1YI_K1'], inplace=True)
        
        # Sütun İsimlerini Düzelt
        df.rename(columns={
            'TP_FG_J0': 'TÜFE',
            'TP_TUFE1YI_K1': 'ÜFE',
            'TP_HKFE01_I1': 'H-ÜFE'
        }, inplace=True)
        
        return df, "OK"
        
    except Exception as e:
        return None, str(e)

# --- UYGULAMA ---
st.title("🚀 SK - Enflasyon & Sözleşme Kokpiti")

# 1. Veri Çekme
df_tcmb, msg = tcmb_verilerini_getir()

if df_tcmb is None:
    st.error(f"Veri Çekilemedi: {msg}")
    st.stop()

# 2. Sol Menü Ayarları
with st.sidebar:
    st.header("⚙️ Hesaplama Ayarları")
    
    # Dönem Seçimi
    donem_map = {
        "1 Ay": 1,
        "3 Ay": 3,
        "6 Ay": 6,
        "1 Yıl (12 Ay)": 12,
        "2 Yıl (24 Ay)": 24
    }
    secilen_etiket = st.selectbox("Analiz Dönemi:", list(donem_map.keys()))
    ay_geriye = donem_map[secilen_etiket]
    
    st.markdown("---")
    tutar = st.number_input("Sözleşme Tutarı (TL):", value=100000.0, format="%.2f")

# 3. Hesaplama Mantığı
# Son satır (En güncel)
son_veri = df_tcmb.iloc[-1]
# Geçmiş satır
if len(df_tcmb) > ay_geriye:
    eski_veri = df_tcmb.iloc[-(ay_geriye + 1)]
else:
    eski_veri = df_tcmb.iloc[0] # Veri yetmezse en başı al

def oran_bul(kolon):
    try:
        yeni = float(son_veri[kolon])
        eski = float(eski_veri[kolon])
        return ((yeni - eski) / eski) * 100
    except: return 0.0

d_tufe = oran_bul('TÜFE')
d_ufe = oran_bul('ÜFE')
d_hufe = oran_bul('H-ÜFE')
d_ort = (d_tufe + d_ufe) / 2

# 4. Gösterge Paneli
st.info(f"📅 **Baz Alınan Dönem:** {eski_veri['Tarih']} ➡️ {son_veri['Tarih']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("TÜFE (Tüketici)", f"%{d_tufe:.2f}")
c2.metric("Yİ-ÜFE (Üretici)", f"%{d_ufe:.2f}")
c3.metric("H-ÜFE (Hizmet)", f"%{d_hufe:.2f}")
c4.metric("Ortalama (T+Ü)/2", f"%{d_ort:.2f}")

st.markdown("---")

# 5. Ağırlıklı Sepet Hesabı
st.subheader("⚖️ Sözleşme Artış Simülasyonu")

col_w, col_res = st.columns([1, 2])

with col_w:
    st.markdown('<div class="kutu">', unsafe_allow_html=True)
    st.write("**Ağırlıklar (Toplam 100)**")
    w_tufe = st.number_input("TÜFE %", 0, 100, 0)
    w_ufe = st.number_input("ÜFE %", 0, 100, 0)
    w_hufe = st.number_input("H-ÜFE %", 0, 100, 0)
    w_ort = st.number_input("Ortalama %", 0, 100, 100)
    st.markdown('</div>', unsafe_allow_html=True)

with col_res:
    toplam_w = w_tufe + w_ufe + w_hufe + w_ort
    
    if toplam_w != 100:
        st.error(f"⚠️ Toplam Ağırlık: {toplam_w} (100 olmalı)")
    else:
        # Final Hesap
        zam_orani = (
            (w_tufe * d_tufe) +
            (w_ufe * d_ufe) +
            (w_hufe * d_hufe) +
            (w_ort * d_ort)
        ) / 100
        
        fark = tutar * (zam_orani / 100)
        yeni_tutar = tutar + fark
        
        st.success(f"YENİ SÖZLEŞME TUTARI: {yeni_tutar:,.2f} TL")
        st.info(f"Fiyat Farkı: {fark:,.2f} TL (+%{zam_orani:.2f})")
        
        # Tablo Hazırlığı
        data = {
            "Kalem": ["TÜFE", "ÜFE", "H-ÜFE", "Ortalama"],
            "Dönemsel Artış (%)": [d_tufe, d_ufe, d_hufe, d_ort],
            "Sözleşme Ağırlığı (%)": [w_tufe, w_ufe, w_hufe, w_ort],
            "Fiyata Etkisi (%)": [
                (d_tufe * w_tufe)/100,
                (d_ufe * w_ufe)/100,
                (d_hufe * w_hufe)/100,
                (d_ort * w_ort)/100
            ]
        }
        
        df_sonuc = pd.DataFrame(data)
        # Sadece ağırlığı olanları göster
        df_sonuc = df_sonuc[df_sonuc["Sözleşme Ağırlığı (%)"] > 0]
        
        # HATA DÜZELTİLEN YER: FORMATLAMA
        # Tüm tabloya değil, sadece sayısal sütunlara format uyguluyoruz.
        format_dict = {
            "Dönemsel Artış (%)": "{:.2f}",
            "Sözleşme Ağırlığı (%)": "{:.2f}",
            "Fiyata Etkisi (%)": "{:.2f}"
        }
        
        st.dataframe(
            df_sonuc.style.format(format_dict), 
            use_container_width=True
        )
