import streamlit as st
import pandas as pd
import yfinance as yf
import evds
from datetime import datetime

# --- API ANAHTARI (Sisteme Gömüldü) ---
MY_API_KEY = "Uol1kIOQos"

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement", layout="wide", page_icon="📱")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    /* Genel Tasarım */
    .logo-text { font-size: 22px !important; font-weight: 900 !important; color: #D91E18 !important; font-family: sans-serif; margin-bottom: 20px; }
    
    .kutu, .kutu-enerji { 
        padding: 15px; border-radius: 10px; margin-bottom: 12px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
    }
    
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; }
    
    /* Yazı Renkleri (Dark Mode Fix) */
    .kutu *, .kutu-enerji *, .kutu b, .kutu-enerji b { color: #1E3D59 !important; }
    .pozitif { color: #27AE60 !important; font-weight: bold; font-size: 18px; }
    .negatif { color: #C0392B !important; font-weight: bold; font-size: 18px; }
    
    /* Etiketler */
    .prediction-tag { font-size: 11px; background-color: #e8f5e9 !important; color: #2e7d32 !important; padding: 3px 6px; border-radius: 4px; font-weight: bold; display: inline-block; margin-bottom: 4px; }
    .date-info { font-size: 11px; color: #666 !important; font-style: italic; }
    
    .stLinkButton a { color: #1E3D59 !important; font-weight: bold !important; text-decoration: none; }
    div[data-testid="stNumberInput"] label { font-size: 13px !important; color: #333 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def tr_fmt(deger):
    if isinstance(deger, (int, float)):
        s = "{:,.2f}".format(deger)
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return "0,00"

# --- TCMB VERİ MOTORU ---
@st.cache_data(ttl=3600)
def get_tcmb_data_safe(donem_tipi):
    # Boş Şablon
    result = {
        "TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, 
        "Status": False, 
        "Msg": "Veri Çekiliyor...",
        "DateRange": ""
    }
    
    try:
        api = evds.evdsAPI(MY_API_KEY)
        
        # Son 4 yılın verisini çek (Geniş Aralık - Hata Önleyici)
        end = datetime.now().strftime("%d-%m-%Y")
        start = (datetime.now() - pd.DateOffset(months=48)).strftime("%d-%m-%Y")
        
        # Kodlar: TÜFE, Yİ-ÜFE, H-ÜFE
        df = api.get_data(['TP.FG.J0', 'TP.TUFE1YI.K1', 'TP.HKFE01.I1'], startdate=start, enddate=end)
        
        if df is None or df.empty:
            result["Msg"] = "TCMB Yanıt Vermedi"
            return result
            
        # Boş satırları temizle
        df.dropna(subset=['TP_FG_J0', 'TP_TUFE1YI_K1'], inplace=True)
        
        if len(df) < 2:
            result["Msg"] = "Yetersiz Geçmiş Veri"
            return result
            
        # --- DÖNEM HESABI ---
        son_row = df.iloc[-1]
        
        # Kaç ay geriye gideceğiz?
        lookback = 1
        if donem_tipi == "3 Ay": lookback = 3
        elif donem_tipi == "6 Ay": lookback = 6
        elif donem_tipi == "1 Yıl": lookback = 12
        elif donem_tipi == "Yılbaşından Bugüne (YTD)":
            bugun_ay = datetime.now().month
            # Yılbaşından beri geçen ay sayısı
            lookback = bugun_ay if len(df) >= bugun_ay else len(df)-1
            
        idx = -(lookback + 1)
        # Liste sınırını aşarsa en başı al
        if abs(idx) > len(df): idx = 0 
        
        ilk_row = df.iloc[idx]
        
        def safe_calc(now, old):
            try: return ((float(now) - float(old)) / float(old)) * 100
            except: return 0.0

        result["TUFE"] = round(safe_calc(son_row['TP_FG_J0'], ilk_row['TP_FG_J0']), 2)
        result["UFE"] = round(safe_calc(son_row['TP_TUFE1YI_K1'], ilk_row['TP_TUFE1YI_K1']), 2)
        
        try:
            if 'TP_HKFE01.I1' in df.columns:
                h_now = df['TP_HKFE01.I1'].iloc[-1]
                h_old = df['TP_HKFE01.I1'].iloc[idx]
                result["HUFE"] = round(safe_calc(h_now, h_old), 2)
        except: pass
            
        result["Status"] = True
        result["Msg"] = "TCMB Güncel"
        result["DateRange"] = f"{ilk_row['Tarih']} ➡️ {son_row['Tarih']}"
        
    except Exception as e:
        result["Msg"] = "Bağlantı Hatası"
        
    return result

# ============================================================================
# 1. SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("⚙️ Ayarlar")
    
    donem_secimi = st.selectbox("Analiz Dönemi:", ["1 Ay", "3 Ay", "6 Ay", "Yılbaşından Bugüne (YTD)", "1 Yıl"], index=0)
    
    y_map = {"1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "Yılbaşından Bugüne (YTD)": "ytd", "1 Yıl": "1y"}
    selected_period = y_map[donem_secimi]
    
    # TCMB VERİSİNİ ÇEK
    # Spinner sadece ilk yüklemede veya dönem değişiminde görünür
    tcmb_data = get_tcmb_data_safe(donem_secimi)

    st.markdown("---")
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    try:
        sozlesme_tutari = float(tutar_giris.replace(".", "").replace(",", "."))
    except:
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
        if df.empty: hata = True
        else:
            for key, symbol in tickers.items():
                try:
                    c_name = [c for c in df.columns if symbol in str(c)]
                    if not c_name: continue
                    seri = df[c_name[0]].dropna()
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
    for d in ["USDTRY", "EURTRY", "EURUSD", "ONS_ALTIN", "BRENT_PETROL", "GRAM_ALTIN_TL"]:
        if d not in piyasa: piyasa[d] = {"ilk": 0, "son": 0, "degisim": 0}

# ============================================================================
# 3. GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans Kokpiti")
st.caption(f"Seçilen Dönem: {donem_secimi}")

def kutu(col, baslik, key, ikon):
    val = piyasa.get(key, {"ilk":0, "son":0, "degisim":0})
    ilk, son, deg = val["ilk"], val["son"], val["degisim"]
    
    # KEY EKLENDİ: Her dönem değiştiğinde widget yenilenir
    widget_key = f"{key}_{donem_secimi}"
    
    with col:
        st.markdown(f"<div class='kutu'><div style='display:flex; align-items:center; margin-bottom:5px;'><span style='font-size:20px; margin-right:8px;'>{ikon}</span><b>{baslik}</b></div>", unsafe_allow_html=True)
        
        # Yahoo verisi 0 gelirse manuel giriş, yoksa göster
        if son == 0: 
            deg = st.number_input(f"{baslik} %", value=0.0, step=0.1, key=widget_key)
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
e1, e2, e3, e4 = st.columns(4)
d_brent = kutu(e1, "Brent ($)", "BRENT_PETROL", "🛢️")
ref_tahmin = d_brent + d_usd

with e2:
    st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    # KEY EKLENDİ
    b_eski = st.number_input("Eski", value=42.0, key=f"b_o_{donem_secimi}")
    b_yeni = st.number_input("Yeni", value=44.0, key=f"b_n_{donem_secimi}")
    d_benzin = ((b_yeni-b_eski)/b_eski)*100 if b_eski>0 else 0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    # KEY EKLENDİ
    m_eski = st.number_input("Eski", value=43.0, key=f"m_o_{donem_secimi}")
    m_yeni = st.number_input("Yeni", value=45.0, key=f"m_n_{donem_secimi}")
    d_dizel = ((m_yeni-m_eski)/m_eski)*100 if m_eski>0 else 0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON (DİNAMİK GÜNCELLEME EKLENDİ)
# ============================================================================
st.markdown("---")
c_inf_title, c_inf_status = st.columns([2, 2])
with c_inf_title: st.markdown("### 📈 Enflasyon & İşçilik")
with c_inf_status:
    if tcmb_data["Status"]: 
        st.success(f"✅ {tcmb_data['Msg']}")
        st.markdown(f"<div class='date-info'>Kapsam: {tcmb_data['DateRange']}</div>", unsafe_allow_html=True)
    else: 
        st.warning(f"⚠️ {tcmb_data['Msg']}")

ec1, ec2, ec3, ec4, ec5 = st.columns(5)

# KEY EKLEMESİ ÇOK ÖNEMLİ: f"tufe_{donem_secimi}"
# Bu sayede dönem değişince widget sıfırlanır ve yeni gelen veriyi kabul eder.
tufe = ec1.number_input("TÜFE %", value=tcmb_data["TUFE"], key=f"tufe_{donem_secimi}")
ufe = ec2.number_input("ÜFE %", value=tcmb_data["UFE"], key=f"ufe_{donem_secimi}")
h_ufe = ec3.number_input("H-ÜFE %", value=tcmb_data["HUFE"], key=f"hufe_{donem_secimi}")
iscilik = ec4.number_input("İşçilik %", value=0.0, help="Asgari Ücret", key=f"iscilik_{donem_secimi}")
abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"abd_{donem_secimi}")

ozel_oran = (tufe + ufe) / 2

# ============================================================================
# 6. SEPET
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
    etkiler = [
        ("Karma", ozel_oran, w_ozel), ("TÜFE", tufe, w_tufe), ("ÜFE", ufe, w_ufe), ("H-ÜFE", h_ufe, w_hufe),
        ("İşçilik", iscilik, w_iscilik), ("USD", d_usd, w_usd), ("EUR", d_eur, w_eur), ("Altın", d_gram, w_altin),
        ("Benzin", d_benzin, w_benzin), ("Motorin", d_dizel, w_dizel), ("Brent", d_brent, w_brent), ("ABD Enf", abd_enf, w_abd)
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
