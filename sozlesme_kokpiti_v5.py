import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import urllib3
from datetime import datetime

# SSL Hatalarını ve Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SİZİN API ANAHTARINIZ ---
MY_API_KEY = "Uol1kIOQos"

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement", layout="wide", page_icon="🚀")

# --- CSS Tasarım ---
st.markdown("""
    <style>
    .logo-text { font-size: 22px !important; font-weight: 900 !important; color: #D91E18 !important; font-family: sans-serif; margin-bottom: 20px; }
    .kutu { background-color: #f8f9fa !important; border-left: 6px solid #1E3D59 !important; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .kutu-enerji { background-color: #fffcf5 !important; border-left: 6px solid #F39C12 !important; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .kutu *, .kutu-enerji * { color: #1E3D59 !important; }
    .big-metric { font-size: 24px !important; font-weight: bold; }
    .pozitif { color: #27AE60 !important; font-weight: bold; }
    .negatif { color: #C0392B !important; font-weight: bold; }
    div[data-testid="stNumberInput"] label { font-size: 13px !important; color: #333 !important; }
    .stLinkButton a { text-decoration: none !important; font-weight: bold !important; color: #1E3D59 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYON ---
def tr_fmt(deger):
    if isinstance(deger, (int, float)):
        s = "{:,.2f}".format(deger)
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return "0,00"

# --- TCMB EXCEL (CSV) MODU ---
@st.cache_data(ttl=3600)
def get_tcmb_excel_mode(donem_tipi):
    # Başlangıçta boş değerler
    result = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Bekleniyor"}
    
    try:
        # 1. URL OLUŞTURMA (Excel/CSV Mantığı)
        # 2020'den bugüne tüm veriyi iste (Geniş Havuz)
        start_date = "01-01-2020"
        end_date = datetime.now().strftime("%d-%m-%Y")
        
        # Kodlar: TÜFE, Yİ-ÜFE, H-ÜFE
        series = "TP.FG.J0-TP.TUFE1YI.K1-TP.HKFE01.I1"
        
        # type=csv parametresi kritik!
        url = f"https://evds2.tcmb.gov.tr/service/evds/series={series}&startDate={start_date}&endDate={end_date}&type=csv&key={MY_API_KEY}"
        
        # 2. İSTEK (Tarayıcı gibi)
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, verify=False, timeout=20)
        
        if r.status_code == 200:
            # Gelen veriyi (CSV metni) Pandas ile tabloya çevir
            csv_data = io.StringIO(r.text)
            df = pd.read_csv(csv_data)
            
            # 3. VERİ TEMİZLİĞİ
            # TCMB sütun isimleri bazen "TP_FG_J0" bazen "TP.FG.J0" gelir. Standartlaştıralım.
            # Sütunları bulmak için 'contains' kullanacağız.
            
            # Tarih sütunu haricindeki tüm sütunları sayıya çevir (Hata varsa NaN yap)
            for col in df.columns:
                if "Tarih" not in col:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Kritik sütunları bul (TÜFE ve ÜFE)
            col_tufe = next((c for c in df.columns if "TP_FG_J0" in c or "TP.FG.J0" in c), None)
            col_ufe = next((c for c in df.columns if "TP_TUFE1YI_K1" in c or "TP.TUFE1YI.K1" in c), None)
            col_hufe = next((c for c in df.columns if "TP_HKFE01_I1" in c or "TP.HKFE01.I1" in c), None)
            
            if not col_tufe or not col_ufe:
                result["Msg"] = "Sütunlar Bulunamadı"
                return result
                
            # Boş satırları at
            df.dropna(subset=[col_tufe, col_ufe], inplace=True)
            
            if len(df) < 2:
                result["Msg"] = "Yetersiz Satır"
                return result
                
            # --- DÖNEM HESAPLAMA ---
            son_veri = df.iloc[-1]
            
            lookback = 1
            if donem_tipi == "3 Ay": lookback = 3
            elif donem_tipi == "6 Ay": lookback = 6
            elif donem_tipi == "1 Yıl": lookback = 12
            elif "YTD" in donem_tipi:
                # Yılbaşından bugüne (Basitçe: veri tarihindeki ay sayısı kadar geri git)
                try:
                    tarih_str = str(son_veri['Tarih']) # "2025-1" gibi
                    ay = int(tarih_str.split('-')[1])
                    lookback = ay if len(df) > ay else len(df)-1
                except: lookback = 12 # Hata olursa 1 yıl al
            
            # İndeks belirle
            idx = -(lookback + 1)
            if abs(idx) > len(df): idx = 0
            
            ilk_veri = df.iloc[idx]
            
            # ORAN HESAPLA
            def calc(new, old):
                if old == 0: return 0.0
                return ((new - old) / old) * 100

            result["TUFE"] = round(calc(son_veri[col_tufe], ilk_veri[col_tufe]), 2)
            result["UFE"] = round(calc(son_veri[col_ufe], ilk_veri[col_ufe]), 2)
            
            if col_hufe and pd.notna(son_veri[col_hufe]):
                result["HUFE"] = round(calc(son_veri[col_hufe], ilk_veri[col_hufe]), 2)
            
            result["Status"] = True
            result["Msg"] = f"Dönem: {ilk_veri['Tarih']} ➡️ {son_veri['Tarih']}"
            
        else:
            result["Msg"] = f"Sunucu Hatası: {r.status_code}"
            
    except Exception as e:
        result["Msg"] = f"Bağlantı Hatası: {str(e)}"
        
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
    
    # TCMB ÇEK (Excel Modu)
    with st.spinner("TCMB Verisi İndiriliyor..."):
        tcmb_data = get_tcmb_excel_mode(donem_secimi)

    st.markdown("---")
    tutar_giris = st.text_input("Sözleşme Tutarı (TL):", value="100.000,00")
    try: sozlesme_tutari = float(tutar_giris.replace(".", "").replace(",", "."))
    except: sozlesme_tutari = 0.0

# ============================================================================
# 2. YAHOO VERİ
# ============================================================================
@st.cache_data(ttl=600)
def piyasa_verisi_al(periyot):
    tickers = { "USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "EURUSD": "EURUSD=X", "ONS_ALTIN": "GC=F", "BRENT_PETROL": "BZ=F", "ABD_TAHVIL": "^TNX" }
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
st.caption(f"Veri Dönemi: {donem_secimi}")

def kutu(col, baslik, key, ikon):
    val = piyasa.get(key, {"ilk":0, "son":0, "degisim":0})
    ilk, son, deg = val["ilk"], val["son"], val["degisim"]
    w_key = f"{key}_{donem_secimi}"
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
    b_eski = st.number_input("Eski", value=42.0, key=f"bo_{donem_secimi}")
    b_yeni = st.number_input("Yeni", value=44.0, key=f"bn_{donem_secimi}")
    d_benzin = ((b_yeni-b_eski)/b_eski)*100 if b_eski>0 else 0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    m_eski = st.number_input("Eski", value=43.0, key=f"mo_{donem_secimi}")
    m_yeni = st.number_input("Yeni", value=45.0, key=f"mn_{donem_secimi}")
    d_dizel = ((m_yeni-m_eski)/m_eski)*100 if m_eski>0 else 0
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON & İŞÇİLİK
# ============================================================================
st.markdown("---")
c_inf_title, c_inf_status = st.columns([2, 2])
with c_inf_title: st.markdown("### 📈 Enflasyon & İşçilik")
with c_inf_status:
    if tcmb_data["Status"]: st.success(f"✅ {tcmb_data['Msg']}")
    else: st.error(f"⚠️ {tcmb_data['Msg']}")

ec1, ec2, ec3, ec4, ec5 = st.columns(5)
tufe = ec1.number_input("TÜFE %", value=tcmb_data["TUFE"], key=f"t_{donem_secimi}")
ufe = ec2.number_input("ÜFE %", value=tcmb_data["UFE"], key=f"u_{donem_secimi}")
h_ufe = ec3.number_input("H-ÜFE %", value=tcmb_data["HUFE"], key=f"h_{donem_secimi}")
iscilik = ec4.number_input("İşçilik %", value=0.0, help="Asgari Ücret", key=f"i_{donem_secimi}")
abd_enf = ec5.number_input("ABD Enf.%", value=0.4, key=f"a_{donem_secimi}")
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
    
    # GÜVENLİ TABLO (Hata Vermeyen)
    data = {"Kalem": [], "Değişim %": [], "Ağırlık %": [], "Etki %": []}
    for ad, deg, agr in etkiler:
        if agr > 0:
            data["Kalem"].append(ad)
            data["Değişim %"].append(deg)
            data["Ağırlık %"].append(agr)
            data["Etki %"].append((deg*agr)/100)
            
    df = pd.DataFrame(data)
    # Sadece sayısal formatlama
    st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
