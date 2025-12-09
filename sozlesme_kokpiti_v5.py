import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Sayfa Ayarları
st.set_page_config(page_title="TAV Sözleşme Yönetimi - Jarvis", layout="wide")

st.title("📋 Sözleşme Eskalasyon ve Bütçe Analizi")
st.markdown("---")

# --- 1. BÖLÜM: VERİ GİRİŞLERİ (ÇERÇEVELİ) ---
col1, col2 = st.columns(2)

with col1:
    with st.container(border=True): # Çerçeve eklendi
        st.subheader("📝 Sözleşme Parametreleri")
        sozlesme_tutari = st.number_input("Mevcut Sözleşme Tutarı (TL)", value=75000.0, step=1000.0)
        vade = st.slider("Vade (Ay)", min_value=1, max_value=24, value=12)
        
        # Yeni Seçenek Eklendi: Serzan'ın Klasiği
        yontem = st.selectbox(
            "Eskalasyon Yöntemi",
            ["TÜFE", "ÜFE", "TÜFE+ÜFE Ortalaması", "Döviz Endeksli (EUR)", "Sabit Oran", "Serzan'ın Klasiği"]
        )

with col2:
    with st.container(border=True): # Çerçeve eklendi
        st.subheader("📈 Piyasa Beklentileri (Tahmini)")
        tufe_beklenti = st.number_input("Aylık Ortalama TÜFE Artışı (%)", value=3.5)
        ufe_beklenti = st.number_input("Aylık Ortalama ÜFE Artışı (%)", value=4.0)
        eur_beklenti = st.number_input("Aylık EUR Artışı (%)", value=2.5)
        sabit_artis = st.number_input("Sabit Artış Oranı (Opsiyonel %)", value=5.0)

# --- 2. BÖLÜM: HESAPLAMA MOTORU ---
# Gelecek ayları oluştur
aylar = [f"{i}. Ay" for i in range(1, vade + 1)]
tutarlar = []
tufe_trendi = [] # Grafik için veri
eur_trendi = [] # Grafik için veri

guncel_tutar = sozlesme_tutari
guncel_tufe_endeksi = 100.0 # Baz puan
guncel_eur_kuru = 38.0 # Baz kur (Örnek)

for i in range(vade):
    # Piyasa verilerini simüle et (Grafik çizgileri için)
    guncel_tufe_endeksi *= (1 + tufe_beklenti / 100)
    guncel_eur_kuru *= (1 + eur_beklenti / 100)
    
    tufe_trendi.append(guncel_tufe_endeksi)
    eur_trendi.append(guncel_eur_kuru)

    # Hesaplama Mantığı
    artis_orani = 0
    if yontem == "TÜFE":
        artis_orani = tufe_beklenti
    elif yontem == "ÜFE":
        artis_orani = ufe_beklenti
    elif yontem == "TÜFE+ÜFE Ortalaması":
        artis_orani = (tufe_beklenti + ufe_beklenti) / 2
    elif yontem == "Döviz Endeksli (EUR)":
        artis_orani = eur_beklenti
    elif yontem == "Sabit Oran":
        artis_orani = sabit_artis
    elif yontem == "Serzan'ın Klasiği":
        # Serzan'ın Klasiği: (TÜFE + ÜFE) / 2 (Ağırlıklı ortalama mantığı)
        artis_orani = (tufe_beklenti + ufe_beklenti) / 2

    # Tutarı güncelle
    guncel_tutar *= (1 + artis_orani / 100)
    tutarlar.append(guncel_tutar)

# Dataframe oluşturma
df = pd.DataFrame({
    "Ay": aylar,
    "Tahmini Tutar (TL)": tutarlar,
    "TÜFE Endeksi (Baz 100)": tufe_trendi,
    "EUR Kuru (Tahmini)": eur_trendi
})

# --- 3. BÖLÜM: GRAFİK (ÇİFT EKSENLİ) ---
st.markdown("### 📊 Finansal Projeksiyon ve Piyasa Göstergeleri")

# Plotly ile Gelişmiş Grafik (Secondary Y-Axis)
fig = make_subplots(specs=[[{"secondary_y": True}]])

# 1. Çizgi: Sözleşme Tutarı (Sol Eksen - Bar veya Area)
fig.add_trace(
    go.Scatter(x=df["Ay"], y=df["Tahmini Tutar (TL)"], name="Sözleşme Tutarı", mode='lines+markers', line=dict(color='#1f77b4', width=4)),
    secondary_y=False,
)

# 2. Çizgi: TÜFE Trendi (Sağ Eksen - Kesikli Çizgi)
fig.add_trace(
    go.Scatter(x=df["Ay"], y=df["TÜFE Endeksi (Baz 100)"], name="TÜFE Endeksi Trendi", mode='lines', line=dict(color='red', dash='dot')),
    secondary_y=True,
)

# 3. Çizgi: EUR Trendi (Sağ Eksen - Kesikli Çizgi)
fig.add_trace(
    go.Scatter(x=df["Ay"], y=df["EUR Kuru (Tahmini)"], name="EUR Kur Trendi", mode='lines', line=dict(color='green', dash='dot')),
    secondary_y=True,
)

# Eksen İsimlendirmeleri
fig.update_layout(
    title_text="Sözleşme Tutarı vs Piyasa İndikatörleri",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
fig.update_yaxes(title_text="Sözleşme Tutarı (TL)", secondary_y=False)
fig.update_yaxes(title_text="Endeks / Kur Değeri", secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

# --- 4. BÖLÜM: JARVIS YORUMU ---
st.markdown("---")
with st.container(border=True):
    st.markdown("### 🤖 Jarvis Yorumu")
    
    toplam_artis_yuzdesi = ((tutarlar[-1] - sozlesme_tutari) / sozlesme_tutari) * 100
    fark = tutarlar[-1] - sozlesme_tutari
    
    col_j1, col_j2 = st.columns([1, 3])
    
    with col_j1:
        st.metric(label="Dönem Sonu Tahmini Tutar", value=f"{tutarlar[-1]:,.2f} TL", delta=f"%{toplam_artis_yuzdesi:.2f} Artış")
    
    with col_j2:
        if yontem == "Serzan'ın Klasiği":
            yorum = f"""
            **Seçiminiz: Serzan'ın Klasiği.** Sir, bu yöntem (TÜFE+ÜFE)/2 formülü ile hem üretici maliyetlerini hem de tüketici fiyatlarını dengeler. 
            Tedarikçi ile yapılan pazarlıklarda en adil ("Fair") yöntem olarak kabul edilir. 
            Yıl sonunda bütçenize ek **{fark:,.2f} TL** yük geleceğini öngörüyorum. 
            Enflasyonist ortamda bu yöntem, tek başına ÜFE'ye göre şirketinizi korurken, tedarikçiyi de mağdur etmez.
            """
            st.info(yorum)
        elif yontem == "Döviz Endeksli (EUR)":
            yorum = f"""
            **Seçiminiz: Döviz Endeksli (EUR).**
            Sir, kur riskini tamamen üstlenmiş durumdasınız. Eğer yerel enflasyon dövizden hızlı artarsa kârlısınız, 
            ancak kur şoku yaşanırsa bütçe sapması (variance) yönetilemeyebilir. 
            Grafikteki yeşil kesikli çizgiyi takip etmenizi öneririm; o çizgi yukarı ivmelenirse revize gerekebilir.
            """
            st.warning(yorum)
        else:
            yorum = f"""
            **Seçiminiz: {yontem}.**
            Dönem sonunda toplam maliyetiniz **{tutarlar[-1]:,.2f} TL** seviyesine ulaşacak. 
            Satınalma stratejiniz gereği, nakit akış tablolarını bu projeksiyona göre güncellemenizi öneririm.
            """
            st.success(yorum)
