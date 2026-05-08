import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# --- HTTP AYARLARI ---
try:
    from curl_cffi import requests as _http
    _HTTP_BACKEND = "curl_cffi"
except ImportError:
    import requests as _http
    _HTTP_BACKEND = "requests"

BASE_URL = "https://www.tefas.gov.tr"
_MIN_REQUEST_INTERVAL = 9.5  # Güvenli hız sınırı
_last_request_time = 0.0

def _wait():
    global _last_request_time
    delta = time.time() - _last_request_time
    if delta < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - delta)
    _last_request_time = time.time()

def _get_business_days() -> Tuple[str, str]:
    """Son iş gününü (T) ve ondan bir önceki iş gününü (T-1) döner."""
    def is_business_day(date):
        return date.weekday() < 5 # 0-4 arası hafta içi
    
    current = datetime.now()
    # Veriler genelde 11:00'den sonra güncellenir
    if current.hour < 11:
        current -= timedelta(days=1)
        
    while not is_business_day(current):
        current -= timedelta(days=1)
    t_day = current
    
    t_minus_1 = t_day - timedelta(days=1)
    while not is_business_day(t_minus_1):
        t_minus_1 -= timedelta(days=1)
        
    return t_minus_1.strftime("%Y%m%d"), t_day.strftime("%Y%m%d")

def fetch_tefas_data():
    t_minus_1, t_day = _get_business_days()
    print(f"Analiz Tarihleri: Başlangıç={t_minus_1}, Bitiş={t_day}")
    
    if _HTTP_BACKEND == "curl_cffi":
        session = _http.Session(impersonate="chrome131")
    else:
        session = _http.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    final_data = []
    
    # Üç ana fon grubu: Yatırım Fonları, Emeklilik Fonları, Borsa Yatırım Fonları
    fon_gruplari = {
        "YAT": "Yatırım Fonları",
        "EMK": "Emeklilik Fonları",
        "BYF": "Borsa Yatırım Fonları"
    }
    
    for fon_tipi, tip_adi in fon_gruplari.items():
        print(f"\n--- {tip_adi} ({fon_tipi}) çekiliyor ---")

        # 1. İstek: Fiyatları ve Genel Bilgileri Al
        print(f" > {fon_tipi} fiyat listesi alınıyor...")
        _wait()
        res_fiyat = session.post(f"{BASE_URL}/api/funds/fonGnlBlgSiraliGetir", json={
            "fonTipi": fon_tipi, "basTarih": t_day, "bitTarih": t_day,
            "basSira": 1, "bitSira": 3000, "dil": "TR"
        }).json()
        fiyat_listesi = res_fiyat.get("resultList", [])

        # 2. İstek: Değişim Yüzdelerini Al (T-1 ile T arası)
        print(f" > {fon_tipi} günlük değişim oranları alınıyor...")
        _wait()
        res_getiri = session.post(f"{BASE_URL}/api/funds/fonGetiriBazliBilgiGetir", json={
            "dil": "TR", "fonTipi": fon_tipi, "islem": 1,
            "basTarih": t_minus_1, "bitTarih": t_day,
            "calismaTipi": 1, "getiriOrani": "1"
        }).json()
        getiri_listesi = res_getiri.get("resultList", [])

        # Değişimleri kod bazlı eşleştir
        getiri_map = {item["fonKodu"]: item.get("getiriOrani", 0) for item in getiri_listesi}
        
        # Verileri birleştir
        for f in fiyat_listesi:
            kod = f["fonKodu"]
            final_data.append({
                "tarih": f["tarih"],
                "fon_kodu": kod,
                "fon_unvani": f["fonUnvan"],
                "tip": fon_tipi,
                "fiyat": f["fiyat"],
                "degisim": getiri_map.get(kod, 0),
                "portfoy_buyuklugu": f.get("portfoyBuyukluk"),
                "kisi_sayisi": f.get("kisiSayisi")
            })
            
    return final_data, t_day

if __name__ == "__main__":
    try:
        veriler, dosya_tarihi = fetch_tefas_data()
        
        dosya_adi = "funds.json"
        with open(dosya_adi, "w", encoding="utf-8") as f:
            json.dump(veriler, f, ensure_ascii=False, indent=4)
            
        print("\n" + "="*40)
        print(f"BAŞARIYLA TAMAMLANDI")
        print(f"Dosya: {dosya_adi}")
        print(f"Toplam Fon Sayısı: {len(veriler)}")
        if veriler:
            # Örnek olarak listenin ortasından veya sonundan bir BYF örneği de gelebilir
            print(f"Son çekilen kayıttan örnek:")
            print(f"  Kod: {veriler[-1]['fon_kodu']} ({veriler[-1]['tip']})")
            print(f"  Fiyat: {veriler[-1]['fiyat']} | Değişim: %{veriler[-1]['degisim']}")
        print("="*40)
            
    except Exception as e:
        print(f"\nİşlem sırasında bir hata oluştu: {e}")
