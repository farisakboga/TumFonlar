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
_MIN_REQUEST_INTERVAL = 9.0  # Güvenli hız sınırı
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
    
    # Bugünün verisi henüz çıkmamış olabilir (genelde 11:00'den sonra netleşir)
    current = datetime.now()
    if current.hour < 11:
        current -= timedelta(days=1)
        
    # Son iş gününü bul (T)
    while not is_business_day(current):
        current -= timedelta(days=1)
    t_day = current
    
    # Bir önceki iş gününü bul (T-1)
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

    # 1. İstek: Fiyatları Al (Bitiş Tarihi Odaklı)
    print("Fiyatlar çekiliyor...")
    _wait()
    res_fiyat = session.post(f"{BASE_URL}/api/funds/fonGnlBlgSiraliGetir", json={
        "fonTipi": "YAT", "basTarih": t_day, "bitTarih": t_day,
        "basSira": 1, "bitSira": 2000, "dil": "TR"
    }).json()
    fiyat_listesi = res_fiyat.get("resultList", [])

    # 2. İstek: Değişim Yüzdelerini Al (T-1 ile T arası)
    print("Günlük değişim oranları hesaplanıyor...")
    _wait()
    res_getiri = session.post(f"{BASE_URL}/api/funds/fonGetiriBazliBilgiGetir", json={
        "dil": "TR", "fonTipi": "YAT", "islem": 1,
        "basTarih": t_minus_1, "bitTarih": t_day,
        "calismaTipi": 1, "getiriOrani": "1"
    }).json()
    getiri_listesi = res_getiri.get("resultList", [])

    # Verileri birleştir
    getiri_map = {item["fonKodu"]: item.get("getiriOrani", 0) for item in getiri_listesi}
    
    final_data = []
    for f in fiyat_listesi:
        kod = f["fonKodu"]
        final_data.append({
            "tarih": f["tarih"],
            "fon_kodu": kod,
            "fon_unvani": f["fonUnvan"],
            "fiyat": f["fiyat"],
            "degisim": getiri_map.get(kod, 0), # T-1'den T'ye değişim
            "portfoy_buyuklugu": f.get("portfoyBuyukluk"),
            "kisi_sayisi": f.get("kisiSayisi")
        })
    
    return final_data, t_day

if __name__ == "__main__":
    try:
        veriler, dosya_tarihi = fetch_tefas_data()
        
        dosya_adi = f"funds.json"
        with open(dosya_adi, "w", encoding="utf-8") as f:
            json.dump(veriler, f, ensure_ascii=False, indent=4)
            
        print(f"\nBaşarıyla kaydedildi: {dosya_adi}")
        print(f"Toplam Fon: {len(veriler)}")
        if veriler:
            print(f"Örnek: {veriler[0]['fon_kodu']} -> Fiyat: {veriler[0]['fiyat']} | Değişim: %{veriler[0]['gunluk_degisim_yuzde']}")
            
    except Exception as e:
        print(f"Hata oluştu: {e}")