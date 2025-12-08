import streamlit as st
import pandas as pd
import yfinance as yf
import evds
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import urllib3

# SSL ve Uyarıları Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SİZİN API ANAHTARINIZ ---
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

# --- YARDIMCI FONKSİYON ---
def tr_fmt(deger):
    if isinstance(deger, (int, float)):
        s = "{:,.2f}".format(deger)
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return "0,00"

# --- TCMB VERİ MOTORU (SİZİN MANTIĞINIZLA ENTEGRE) ---
@st.cache_data(ttl=3600)
def get_tcmb_data_user_logic(api_key, donem_etiketi):
    result = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Bekleniyor"}
    
    if not api_key: return result

    try:
        evds_api = evds.evdsAPI(api_key)
        
        # 1. REFERANS TARİHLERİ BELİRLE (Dateutil ile)
        today = date.today()
        # Enflasyon verisi bir önceki ayın 3'ünde açıklanır. Garanti olsun diye geçen ayı baz alalım.
        target_date = today.replace(day=1) - relativedelta(months=1)
        
        # Geçmiş Tarihi Hesapla
        if donem_etiketi == "1 Ay": past_date = target_date - relativedelta(months=1)
        elif donem_etiketi == "3 Ay": past_date = target_date - relativedelta(months=3)
        elif donem_etiketi == "6 Ay": past_date = target_date - relativedelta(months=6)
        elif donem_etiketi == "1 Yıl": past_date = target_date - relativedelta(months=12)
        elif "YTD" in donem_etiketi: past_date = date(target_date.year - 1, 12, 1)
        else: past_date = target_date - relativedelta(months=1)

        # 2. VERİYİ ÇEK (Geniş Aralık)
        # Sadece ihtiyacımız olan aralığı değil, biraz öncesini ve sonrasını da çekelim ki period eşleşsin
        start_q = (past_date - relativedelta(months=2)).strftime("%d-%m-%Y")
        end_q = datetime.now().strftime("%d-%m-%Y")
        
        # Kodlar: TÜFE, Yİ-ÜFE (K1), H-ÜFE
        series = ["TP.FG.J0", "TP.TUFE1YI.K1", "TP.HKFE01.I1"]
        
        df = evds_api.get_data(series, startdate=start_q, enddate=end_q)
        
        if df is None or df.empty:
            result["Msg"] = "API Boş Döndü"
            return result
            
        # 3. TARİH EŞLEŞTİRME (SİZİN YÖNTEMİNİZ)
        df['Tarih_Dt'] = pd.to_datetime(df['Tarih'], format='%Y-%m')
        
        # Hedef ve Geçmiş Periyotlar
        target_p = pd.Period(target_date, freq='M')
        past_p = pd.Period(past_date, freq='M')
        
        # Satırları Bul
        row_now = df[df['Tarih_Dt'].dt.to_period('M') == target_p]
        row_old = df[df['Tarih_Dt'].dt.to_period('M') == past_p]
        
        # Eğer tam o ay yoksa (henüz açıklanmadıysa), bir önceki ayı dene
        if row_now.empty:
            target_p = target_p - 1
            row_now = df[df['Tarih_Dt'].dt.to_period('M') == target_p]
            
        if row_now.empty or row_old.empty:
            result["Msg"] = f"Tarih Eşleşmedi ({past_p} - {target_p})"
            return result
            
        # 4. HESAPLAMA
        def extract_val(row, col_name):
            val = row[col_name].values[0]
            return float(val) if pd.notna(val) else 0.0

        # Sütun isimleri bazen nokta bazen alt tire gelir, kontrol edelim
        cols = df.columns
        c_tufe = "TP_FG_J0" if "TP_FG_J0" in cols else "TP.FG.J0"
        c_ufe = "TP_TUFE1YI_K1" if "TP_TUFE1YI_K1" in cols else "TP.TUFE1YI.K1"
        c_hufe = "TP_HKFE01_I1" if "TP_HKFE01_I1" in cols else "TP.HKFE01.I1"

        tufe_now = extract_val(row_now, c_tufe)
        tufe_old = extract_val(row_old, c_tufe)
        
        ufe_now = extract_val(row_now, c_ufe)
        ufe_old = extract_val(row_old, c_ufe)
        
        h_now = extract_val(row_now, c_hufe) if c_hufe in cols else 0
        h_old = extract_val(row_old, c_hufe) if c_hufe in cols else 0
        
        def calc(n, o):
            if o == 0: return 0.0
            return ((n - o) / o) * 100

        result["TUFE"] = round(calc(tufe_now, tufe_old), 2)
        result["UFE"] = round(calc(ufe_now, ufe_old), 2)
        result["HUFE"] = round(calc(h_now, h_old), 2)
        
        result["Status"] = True
        result["Msg"] = f"Dönem: {past_p} ➡️ {target_p}"
        
    except Exception as e:
        result["Msg"] = f"Hata: {str(e)}"
        
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
    
    # TCMB ÇEK
    tcmb_data = get_tcmb_data_user_logic(MY_API_KEY, donem_secimi)

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
    else: st.warning(f"⚠️ {tcmb_data['Msg']}")

ec1, ec2, ec3, ec4, ec5 = st.columns(5)
# DİNAMİK VERİ: API'den gelen veriyi default value olarak ata
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
    
    data = {"Kalem": [], "Değişim %": [], "Ağırlık %": [], "Etki %": []}
    for ad, deg, agr in etkiler:
        if agr > 0:
            data["Kalem"].append(ad)
            data["Değişim %"].append(deg)
            data["Ağırlık %"].append(agr)
            data["Etki %"].append((deg*agr)/100)
            
    df = pd.DataFrame(data)
    st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
