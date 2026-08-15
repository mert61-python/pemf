# Author: mertaygn, cglrgrkn
"""Ses kaydı kalite kapısı — kedi sesi sınıflandırmasından ÖNCE çalışır.

SAHA BİLDİRİMİ (2026-08-15, sahip): "ses kaydında kedi sesi olmamasına rağmen analiz yapıp
sonuç veriyor" (ev sahibi modu, canlı kayıt).

KÖK NEDEN MİMARİ: `inference_cat_sound` modelinin 10 sınıfının HEPSİ kedi duygusudur
(Angry..Warning); "kedi değil" sınıfı YOKTUR. Softmax her zaman 1'e toplandığı için model
sessizliğe de, oda gürültüsüne de, insan konuşmasına da MUTLAKA bir duygu atar. Yani "kedi
sesi yok" cevabını model veremez — bu karar model DIŞINDA verilmek zorundadır.

ÖLÇÜM (depodaki GERÇEK kedi kayıtları ai_hub/PEMF_AI_Test_Girdileri/10*.mp3 ile kalibre
edildi; kedi-olmayan girdiler sentetik üretildi):

    girdi                     RMS dBFS   top-1 olasılık   normalize entropi
    ─────────────────────────────────────────────────────────────────────
    🐱 mutlu   (gerçek)         -12.7        0.910             0.213
    🐱 kızgın  (gerçek)         -17.2        0.898             0.239
    🐱 ağrı    (gerçek)         -26.3        0.563             0.672
    ✗ tam sessizlik              -inf        0.167             0.933
    ✗ sessiz oda                -60.0        0.585             0.640
    ✗ oda gürültüsü             -35.0        0.595             0.637
    ✗ şebeke uğultusu 50Hz      -23.0        0.350             0.805
    ✗ yüksek beyaz gürültü      -14.0        0.425             0.772
    ✗ konuşma benzeri           -23.8        0.557             0.692

İKİ SONUÇ:

1) SESSİZLİK KESİN AYRILIR. Gerçek kayıtların en sessizi -26,3 dBFS; sessizlik -inf..-60.
   `SESSIZLIK_ESIGI_DBFS = -45` ikisinin ARASINDA ve gerçek kayıtlara ~19 dB pay bırakır.
   Sessiz kayıtta analiz yapmak zaten anlamsızdır: model orada %16,7 (şans %10) veriyor.

2) ⚠️ "KEDİ SESİ VAR MI" SORUSU BU MODELLE GÜVENİLİR CEVAPLANAMAZ — aralıklar ÖRTÜŞÜYOR
   (kedi 0,563..0,913 · kedi-değil 0,167..0,595). Bu yüzden düşük güven REDDEDİLMEZ, yalnız
   İŞARETLENİR. Sert bir 0,60 eşiği koysaydık yukarıdaki GERÇEK AĞRI KAYDI (0,563) da
   reddedilirdi → ev sahibi, kedisi gerçekten ağrıdayken "kedi sesi algılanamadı" görürdü.
   Bu, düzeltmeye çalıştığımız hatadan daha kötü olurdu (pet_owner modunun tek amacı ağrıyı
   fark ettirmektir). Sahip kararı (2026-08-15): sessizliği REDDET, zayıfı UYAR.

Entropi eşiği neden 0,60: net iki kedi kaydı 0,21-0,24; kedi-olmayan hiçbir girdi 0,637'nin
altına inmiyor. 0,60, gürültünün TAMAMINI "güvenilir değil" işaretler ve net kedi kayıtlarına
dokunmaz. Arada kalan gerçek ağrı kaydı (0,672) da işaretlenir — bu DOĞRUDUR: model orada
gerçekten emin değildi ve sınıfı da yanlış bildi ("Fighting", oysa kayıt ağrı).
"""

from __future__ import annotations

import math
import wave
from typing import Iterable

# Gerçek kayıtların en sessizi -26,3 dBFS; sessizlik/çok-zayıf -45'in altında kalır.
SESSIZLIK_ESIGI_DBFS: float = -45.0

# Normalize entropi (0 = kesin, 1 = 10 sınıfa tam eşit dağılım). Üstü "güvenilir değil".
BELIRSIZLIK_ESIGI: float = 0.60


def rms_dbfs(ornekler: Iterable[float]) -> float:
    """Örneklerin RMS'i, dBFS cinsinden. Tam sessizlikte `-inf`.

    Girdi [-1, 1] aralığında normalize float örnekler.
    """
    toplam = 0.0
    n = 0
    for x in ornekler:
        toplam += float(x) * float(x)
        n += 1
    if n == 0:
        return float("-inf")
    r = math.sqrt(toplam / n)
    if r <= 0.0:
        return float("-inf")
    return 20.0 * math.log10(r)


def wav_rms_dbfs(yol: str) -> float:
    """16-bit PCM WAV dosyasının RMS'i (dBFS).

    Yalnız ffmpeg'in ÜRETTİĞİ WAV'ı okur (22050 Hz mono 16-bit), yani format sabittir.
    numpy varsa onu kullanır (hızlı); yoksa saf-Python'a düşer — kapı, isteğe bağlı bir
    bağımlılık yüzünden SESSİZCE devre dışı kalmamalı.
    """
    with wave.open(yol, "rb") as w:
        if w.getsampwidth() != 2:
            # Beklenmeyen format: kapıyı zorlamak yerine "ölçemedim" de (çağıran karar verir).
            raise ValueError(f"beklenen 16-bit PCM, gelen {w.getsampwidth() * 8}-bit")
        cerceve = w.readframes(w.getnframes())
    if not cerceve:
        return float("-inf")
    try:
        import numpy as np

        x = np.frombuffer(cerceve, dtype="<i2").astype("float64") / 32768.0
        r = float(np.sqrt(np.mean(x * x)))
        return float("-inf") if r <= 0.0 else 20.0 * math.log10(r)
    except ImportError:
        import array

        a = array.array("h")
        a.frombytes(cerceve)
        return rms_dbfs(v / 32768.0 for v in a)


def sessiz_mi(rms: float, esik: float = SESSIZLIK_ESIGI_DBFS) -> bool:
    """Kayıt analiz edilemeyecek kadar sessiz mi?"""
    return rms < esik


def normalize_entropi(olasiliklar: Iterable[float]) -> float:
    """Softmax dağılımının normalize Shannon entropisi: 0 = kesin, 1 = tam belirsiz.

    Tek bir `top_1_prob` yerine TÜM dağılımı kullanır: model ikinci ve üçüncü sınıfa da
    yakın olasılık veriyorsa bu, tek başına top-1'e bakınca görünmez.
    """
    p = [float(v) for v in olasiliklar if float(v) > 0.0]
    if len(p) < 2:
        return 0.0
    toplam = sum(p)
    if toplam <= 0.0:
        return 1.0
    p = [v / toplam for v in p]
    h = -sum(v * math.log(v) for v in p)
    return h / math.log(len(p))


def guvenilir_mi(olasiliklar: Iterable[float], esik: float = BELIRSIZLIK_ESIGI) -> bool:
    """Sonuç kesin bir bulgu gibi sunulabilir mi?

    ⚠️ `False` "kedi sesi yok" DEMEK DEĞİLDİR — bu model bunu söyleyemez (bkz. modül
    başlığı). Yalnızca "model emin değil, kullanıcıya kesinmiş gibi gösterme" demektir.
    """
    return normalize_entropi(olasiliklar) <= esik
