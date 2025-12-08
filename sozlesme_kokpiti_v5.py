import streamlit as st
import pandas as pd
import yfinance as yf
from evds import evdsAPI
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import urllib3
import numpy as np
import io # Excel işlemi için gerekli

# SSL Hatalarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
# Hızlı çalıştırma için key'i buraya koyuyorum (Prod'da secrets kullanın)
try:
    MY_API_KEY = st.secrets["EVDS_KEY"]
except:
    # Eğer secrets yoksa buraya manuel key yazabilirsiniz
    MY_API_KEY = "Uol1kIOQos" 

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SK - Procurement v2.0", layout="wide", page_icon="🛡️")

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

# --- TCMB MOTORU ---
@st.cache_data(ttl=3600)
def get_tcmb_date_range(api_key, start_date, end_date):
    res = {"TUFE": 0.0, "UFE": 0.0, "HUFE": 0.0, "Status": False, "Msg": "Veri Yok"}
    
    if not api_key: return res

    try:
        evds_service = evdsAPI(api_key)
        start_q = (start_date - relativedelta(months=2)).strftime("%d-%m-%Y")
        end_q = (end_date + relativedelta(months=1)).strftime("%d-%m-%Y")
        series = ["TP.FG.J0", "TP.TUFE1YI.T1", "TP.HKFE01.I1"]
        
        raw_df = evds_service.get_data(series, startdate=start_q, enddate=end_q)
        
        if raw_df is None or raw_df.empty:
            res["Msg"] = "API Boş Döndü"
            return res
            
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
        
        p_start = pd.Period(start_date, freq='M')
        p_end = pd.Period(end_date, freq='M')
        max_date_in_df = raw_df['Tarih_Dt'].max()
        max_p = pd.Period(max_date_in_df, freq='M')
        
        if p_end > max_p: p_end = max_p 
            
        row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_start]
        row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == p_end]
        
        if row_start.empty:
            mask = raw_df['Tarih_Dt'] >= pd.to_datetime(start_date)
            if mask.any():
                row_start = raw_df.loc[mask].iloc[[0]]
                p_start = pd.Period(row_start['Tarih_Dt'].values[0], freq='M')
        
        if row_end.empty:
            row_end = raw_df.iloc[[-1]]
            p_end = pd.Period(row_end['Tarih_Dt'].values[0], freq='M')
        
        if row_start.empty or row_end.empty:
            res["Msg"] = "Tarih Aralığı Bulunamadı"
            return res

        cols = raw_df.columns
        c_t = "TP_FG_J0" if "TP_FG_J0" in cols else "TP.FG.J0"
        c_u = "TP_TUFE1YI_T1" if "TP_TUFE1YI_T1" in cols else "TP.TUFE1YI.T1"
        c_h = "TP_HKFE01_I1" if "TP_HKFE01_I1" in cols else "TP.HKFE01.I1"
        
        def get_val(row, c):
            if c in row.columns and pd.notna(row[c].values[0]): return float(row[c].values[0])
            return 0.0

        t_start, t_end = get_val(row_start, c_t), get_val(row_end, c_t)
        u_start, u_end = get_val(row_start, c_u), get_val(row_end, c_u)
        h_start, h_end = get_val(row_start, c_h), get_val(row_end, c_h)
        
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
# SOL MENÜ
# ============================================================================
with st.sidebar:
    st.markdown('<div class="logo-text">SK - Procurement<br>Specialist</div>', unsafe_allow_html=True)
    st.header("📅 Tarih Aralığı")
    
    today = date.today()
    default_start = today - relativedelta(years=1)
    
    start_date = st.date_input("Başlangıç Tarihi", value=default_start)
    end_date = st.date_input("Bitiş Tarihi (Güncel)", value=today)
    
    if start_date >= end_date:
        st.error("Hata: Başlangıç, Bitişten küçük olmalı!")
    
    with st.spinner("TCMB Verileri Hesaplanıyor..."):
        tcmb = get_tcmb_date_range(MY_API_KEY, start_date, end_date)

    st.markdown("---")
    sozlesme_tutari = st.number_input("Sözleşme Tutarı (TL):", value=100000.0, step=1000.0, format="%.2f")
    d_key = f"{start_date}_{end_date}"

# ============================================================================
# 2. YAHOO VERİ & GRAFİKLER
# ============================================================================
@st.cache_data(ttl=600)
def piyasa_verisi_al(d_start, d_end):
    tickers = { "USDTRY": "TRY=X", "EURTRY": "EURTRY=X", "EURUSD": "EURUSD=X", "ONS_ALTIN": "GC=F", "BRENT_PETROL": "BZ=F", "ABD_TAHVIL": "^TNX" }
    data_dict = {}
    chart_df = pd.DataFrame()
    
    for k in tickers: data_dict[k] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}

    try:
        raw_data = yf.download(list(tickers.values()), start=d_start, end=d_end + timedelta(days=1), progress=False)['Close']
        raw_data = raw_data.ffill().bfill()
        
        if not raw_data.empty:
            # Grafik için veri hazırlığı
            chart_cols = [c for c in raw_data.columns if "TRY=X" in str(c) or "EURTRY=X" in str(c)]
            if chart_cols:
                chart_df = raw_data[chart_cols].copy()
                chart_df.columns = ["EUR/TL", "USD/TL"] if len(chart_cols) == 2 else chart_cols

            for key, symbol in tickers.items():
                try:
                    c_name = [c for c in raw_data.columns if symbol in str(c)]
                    if not c_name: continue
                    seri = raw_data[c_name[0]]
                    if len(seri) > 0:
                        ilk, son = float(seri.iloc[0]), float(seri.iloc[-1])
                        if ilk > 0:
                            data_dict[key] = {"ilk": ilk, "son": son, "degisim": ((son - ilk) / ilk) * 100}
                except: pass
            
            # Altın
            if data_dict["ONS_ALTIN"]["son"] > 0 and data_dict["USDTRY"]["son"] > 0:
                g_son = (data_dict["ONS_ALTIN"]["son"] / 31.1035) * data_dict["USDTRY"]["son"]
                g_ilk = (data_dict["ONS_ALTIN"]["ilk"] / 31.1035) * data_dict["USDTRY"]["ilk"]
                g_deg = 0.0
                if g_ilk > 0: g_deg = ((g_son - g_ilk) / g_ilk) * 100
                data_dict["GRAM_ALTIN_TL"] = {"ilk": g_ilk, "son": g_son, "degisim": g_deg}
    except: pass
    return data_dict, chart_df

piyasa, kur_grafik = piyasa_verisi_al(start_date, end_date)
if "GRAM_ALTIN_TL" not in piyasa: piyasa["GRAM_ALTIN_TL"] = {"ilk": 0.0, "son": 0.0, "degisim": 0.0}

# ============================================================================
# 3. GÖSTERGE PANELİ
# ============================================================================
st.title("📱 Finans & Sözleşme Kokpiti v2.0")
st.caption(f"Analiz Dönemi: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")

# Trend Grafiği (Yeni Özellik)
if not kur_grafik.empty:
    with st.expander("📈 Kur Trend Grafiği (Dönemsel Dalgalanma)", expanded=False):
        st.line_chart(kur_grafik)

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

st.markdown("### 🛢️ Enerji & Emtia")
e1, e2, e3, e4 = st.columns(4)
d_brent = kutu(e1, "Brent ($)", "BRENT_PETROL", "🛢️")
ref_tahmin = d_brent + d_usd

with e2:
    st.markdown(f"<div class='kutu-enerji'><b>⛽ Benzin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    b_eski = st.number_input("Eski", value=42.0, key=f"bo_{d_key}")
    b_yeni = st.number_input("Yeni", value=44.0, key=f"bn_{d_key}")
    d_benzin = 0.0 if b_eski == 0 else ((b_yeni-b_eski)/b_eski)*100
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_benzin:.2f}</span></div></div>", unsafe_allow_html=True)

with e3:
    st.markdown(f"<div class='kutu-enerji'><b>🚛 Motorin</b><br><span class='prediction-tag'>Tahmin: %{ref_tahmin:.1f}</span>", unsafe_allow_html=True)
    m_eski = st.number_input("Eski", value=43.0, key=f"mo_{d_key}")
    m_yeni = st.number_input("Yeni", value=45.0, key=f"mn_{d_key}")
    d_dizel = 0.0 if m_eski == 0 else ((m_yeni-m_eski)/m_eski)*100
    st.markdown(f"<div style='text-align:right;'><span class='pozitif'>%{d_dizel:.2f}</span></div></div>", unsafe_allow_html=True)

kutu(e4, "ABD 10Y", "ABD_TAHVIL", "🇺🇸")

# ============================================================================
# 5. ENFLASYON GİRİŞİ
# ============================================================================
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

# ============================================================================
# 6. AKILLI ŞABLONLAR VE SEPET
# ============================================================================
st.markdown("---")
col_title_w, col_temp = st.columns([2, 2])
col_title_w.markdown("#### ⚖️ Sepet Ağırlıkları (Toplam 100 olmalı)")

# Şablon Tanımları
sablonlar = {
    "Manuel Giriş": {},
    "🏗️ İnşaat/Tadilat (MEP)": {"tufe": 10, "ufe": 40, "usd": 30, "eur": 20},
    "🧹 Temizlik/Personel": {"iscilik": 80, "tufe": 20},
    "💻 IT/Lisanslama": {"usd": 80, "eur": 20},
    "🚛 Lojistik/Nakliye": {"dizel": 40, "iscilik": 30, "tufe": 30}
}
secilen_sablon = col_temp.selectbox("⚡ Hızlı Şablon Seç:", list(sablonlar.keys()))

def get_def(k, default=0):
    if secilen_sablon == "Manuel Giriş": return default
    return sablonlar[secilen_sablon].get(k, 0)

w1, w2, w3, w4 = st.columns(4)
w_ozel = w1.number_input("Karma (Mix) %", value=get_def("mix", 0))
w_tufe = w2.number_input("Saf TÜFE %", value=get_def("tufe", 30))
w_ufe = w3.number_input("Saf ÜFE %", value=get_def("ufe", 0))
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
w_abd = w12.number_input("ABD Enf. %", value=get_def("abd", 0))

toplam = w_ozel+w_tufe+w_ufe+w_hufe+w_iscilik+w_usd+w_eur+w_altin+w_benzin+w_dizel+w_brent+w_abd

if toplam != 100:
    st.error(f"⚠️ Toplam Ağırlık: %{toplam} (100 olmalı)")
else:
    # Hesaplama Listesi
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
    
    # METRİKLER
    st.markdown("---")
    r1, r2, r3 = st.columns(3)
    r1.metric("Toplam Artış", f"%{zam:.2f}")
    r2.metric("Fiyat Farkı", f"{tr_fmt(fark)} TL")
    r3.metric("YENİ TUTAR", f"{tr_fmt(yeni)} TL", delta_color="normal")
    
    # --- JARVIS ANALİZİ (YENİ ÖZELLİK) ---
    df_temp = pd.DataFrame(etkiler, columns=["Kalem", "Degisim", "Agirlik"])
    df_temp["Etki"] = (df_temp["Degisim"] * df_temp["Agirlik"]) / 100
    df_sorted = df_temp.sort_values(by="Etki", ascending=False)
    
    if not df_sorted.empty and zam > 0:
        top_item = df_sorted.iloc[0]
        st.markdown(f"""
        <div class="jarvis-note">
        💡 <b>Jarvis Analizi:</b> Fiyat farkındaki en büyük etken <b>{top_item['Kalem']}</b> kalemidir. 
        Tek başına toplam zammın <b>%{top_item['Etki']:.2f}</b> puanlık kısmını oluşturmaktadır.
        </div>
        """, unsafe_allow_html=True)

    # --- TABLO VE EXCEL ÇIKTISI ---
    st.markdown("---")
    
    # DataFrame Hazırlığı
    data = {"Kalem": [], "Değişim %": [], "Ağırlık %": [], "Etki %": []}
    for ad, deg, agr in etkiler:
        if agr > 0:
            data["Kalem"].append(ad)
            data["Değişim %"].append(deg)
            data["Ağırlık %"].append(agr)
            data["Etki %"].append((deg*agr)/100)
            
    df = pd.DataFrame(data)
    
    t1, t2 = st.columns([3, 1])
    with t1:
        st.dataframe(df.style.format({"Değişim %": "{:.2f}", "Ağırlık %": "{:.0f}", "Etki %": "{:.2f}"}), use_container_width=True)
    
    with t2:
        st.write("") # Boşluk
        st.write("") 
        # Excel Oluşturma
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                # Sayfa 1: Detay
                df.to_excel(writer, sheet_name='Hesap Detayi', index=False)
                
                # Sayfa 2: Özet
                ozet_df = pd.DataFrame({
                    'Kalem': ['Dönem', 'Eski Tutar', 'Artış Oranı', 'Fiyat Farkı', 'Yeni Tutar'],
                    'Değer': [f"{start_date} - {end_date}", sozlesme_tutari, f"%{zam:.2f}", fark, yeni]
                })
                ozet_df.to_excel(writer, sheet_name='Ozet', index=False)
                
            st.download_button(
                label="📥 Excel İndir (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Fiyat_Farki_{start_date}_{end_date}.xlsx",
                mime="application/vnd.ms-excel",
                type="primary"
            )
        except Exception as e:
            st.error(f"Excel oluşturulamadı: {e}. 'pip install XlsxWriter' yaptınız mı?")
