# Author: mertaygn
"""ÇOK-PANELLİ AI YANITI — panel adı + kapak + kalite TEK KAYNAK (AI Hub planı, ADIM 3).

===============================================================================
NEDEN AYRI BİR MODÜL
===============================================================================
fantom ve petri boru hatları 7'şer panel üretiyor (`render_all_panels`) ama yanıt
yalnız `07_combined` mozaiğini taşıyordu; diğer 6'sı **aynı satırda üretilip çöpe
atılıyordu**. Panelleri yayına açmak dört yerde aynı kodu gerektirir:

    servers/ai_router.py   → em_fantom, em_petri
    ai_service/app.py      → em_fantom, em_petri   (GPU profili)

⚠️ Bugün o dört yer aynı kodlama satırını BAĞIMSIZ yazıyor ve bu deponun tekrar eden
sürüklenme sınıfı tam olarak budur (ACK biçim dizesi, simülatör dilimleri, banner kanal
sayısı hepsi böyle bayatladı). Panel adları/kapak/kalite buradan gelir; dört çağrı yeri
yalnız `panelleri_yayina_hazirla(...)` çağırır.

⚠️ NEDEN `servers/` DEĞİL `utils/`: GPU mikroservisi AYRI bir imajda koşar ve
`docker/Dockerfile.ai` **`servers/`i HİÇ kopyalamaz** — modül orada kalsaydı konteynerde
import edilemez, panel yayını GPU profilinde sessizce ölürdü (bu deponun beş kez ölçtüğü
"gömülü'de var, GPU'da yok" sınıfının ta kendisi). `utils/` iki dağıtımın ORTAK katmanıdır
(`image_domain`, `klinik_asgari`, `ses_kalitesi` aynı gerekçeyle burada).
⚠️ İmport `app.py`de ÜST DÜZEYDEDİR, `try/except` İÇİNDE DEĞİL — Dockerfile'ın COPY satırı
unutulursa servis ImportError ile AÇILMAZ. Sessiz kayıp yerine gürültülü arıza BİLİNÇLİ
tercihtir (Dockerfile.ai bu kuralı kendi yorumunda yazıyor).
Kapı: `test_ai_servis_8100_kapisi.py::test_DOCKERFILE_kapi_modullerini_KOPYALIYOR`.

===============================================================================
⚠️ SÖZLEŞME — GERİYE UYUMLULUK
===============================================================================
Kök `image_base64` (07_combined) **KALIR**. `paneller` YALNIZCA EK bir alandır:
eski istemci onu görmez ve bugünkü davranışı değişmez
(`test_ai_kare_boyutu.py::test_alan_yalniz_EK_oldugu_icin_geriye_uyumlu` bu kuralı
zaten kilitliyor).

⚠️ BAYRAK YOK — BİLEREK. Plan bayrak tuzağını ölçtü: `ai_client.py` `None` alanları
atar ve FastAPI tanımadığı form alanını **sessizce** düşürür; petri ayarlarında tam bu
yaşandı ve ayar hiç ulaşmadı. Yük zaten büyümediği için (kapak+kalite ile mozaik
1.646 → 364 KB) bayrağa gerek yok.
"""

from __future__ import annotations

import base64
from typing import Any

#: Yayına çıkan panel anahtarları ve gösterim adları — ARAYÜZ ÇİPLERİ BUNU OKUR.
#: ⚠️ SIRA ANLAMLIDIR: analiz akışını izler (girdi → tespit → maske → tümör → koordinat →
#: tahmin → birleşik). Arayüzdeki ok tuşları bu sırada gezer.
#: ⚠️ Anahtarlar `render_all_panels` çıktısıyla BİREBİR aynı olmalı; ayrışırsa panel
#: sessizce düşer. Kapı: `test_ai_panel_yayini.py`.
PANEL_ADLARI: dict[str, str] = {
    "01_input": "Girdi",
    "02_phantom_detect": "Tespit",
    "03_phantom_mask": "Maske",
    "04_tumors": "Tümörler",
    "05_local_coords": "Koordinat",
    "06_predictions": "Tahmin",
    "07_combined": "Birleşik",
}

#: Kök `image_base64` olarak dönen panel — istemcinin geriye-uyum yolu bunu okur.
KOK_PANEL = "07_combined"

#: Petri boru hattı aynı 7 yuvayı farklı adlarla doldurur — gösterim adı ona göre.
#: ⚠️ ANAHTARLAR KAYNAKTAN DOĞRULANDI (`petri_cv/render.py:344-350`) — tahmin EDİLMEDİ.
#: İlk yazımda `02_plate_detect`/`03_wells` varsayılmıştı; gerçek adlar farklı çıktı ve
#: yanlış anahtar paneli sessizce "bilinmeyen"e düşürürdü.
PETRI_PANEL_ADLARI: dict[str, str] = {
    "01_input": "Girdi",
    "02_yolo_dets": "Tespit",
    "03_yolo_masks": "Maske",
    "04_classify": "Sınıflama",
    "05_local_coords": "Koordinat",
    "06_predictions": "Tahmin",
    "07_combined": "Birleşik",
}


def panelleri_yayina_hazirla(
    panels: dict[str, Any] | None,
    kodlayici,
    adlar: dict[str, str] | None = None,
) -> list[dict]:
    """`render_all_panels` çıktısını yayın listesine çevirir.

    @param panels    {anahtar: BGR ndarray} — boru hattının ürettiği panel sözlüğü.
                     `None`/boş KABUL EDİLİR (tespit-yok dalı) → boş liste döner.
    @param kodlayici `(img) -> (jpeg_baytlari, {"image_w","image_h"})`
                     ⚠️ KAPAK VE KALİTEYİ ÇAĞIRAN SAĞLAR (gömülü `_kapakli_kodla`,
                     GPU `_kapakli_kodla_servis`) — böylece iki dağıtım AYNI kapağı
                     kullanır ama modül `cv2`ye bağımlı olmaz (test edilebilir kalır).
    @return [{"k", "ad", "image_base64", "image_w", "image_h"}, ...]

    ⚠️ BİLİNMEYEN ANAHTAR ATLANMAZ, YAYINLANIR: boru hattı yeni bir panel eklerse
    arayüzde görünsün (adı yoksa anahtarın kendisi ad olur). Sessizce düşürmek,
    "üretildi ama kimse görmedi" arızasının ta kendisidir.

    ⚠️ BİR PANEL KODLANAMAZSA ATLANIR, TÜM YANIT DÜŞMEZ: tek bozuk panel yüzünden
    analizi kaybetmek kabul edilemez.
    """
    if not panels:
        return []
    adlar = adlar or PANEL_ADLARI
    cikti: list[dict] = []
    # ⚠️ SIRA: önce bilinen anahtarlar TANIMLI SIRADA, sonra bilinmeyenler alfabetik.
    # `dict` sırasına güvenmek, boru hattı sırayı değiştirince arayüzdeki ok tuşlarının
    # sırasını sessizce değiştirirdi.
    sirali = [k for k in adlar if k in panels] + sorted(k for k in panels if k not in adlar)
    for k in sirali:
        img = panels.get(k)
        if img is None:
            continue
        try:
            bayt, boyut = kodlayici(img)
        except Exception:
            continue
        cikti.append(
            {
                "k": k,
                "ad": adlar.get(k, k),
                "image_base64": base64.b64encode(bayt).decode("utf-8"),
                **boyut,
            }
        )
    return cikti


def kok_gorseli_sec(paneller: list[dict], yedek_kodlayici, yedek_kare):
    """Kök `image_base64` + boyut — mümkünse ZATEN kodlanmış `07_combined` panelinden.

    @param yedek_kare ORİJİNAL girdi karesi (mozaik DEĞİL) — aşağıdaki uyarıya bakın.
    @return `(base64_str, {"image_w","image_h"})`

    ⚠️ NEDEN: uçlar mozaiği İKİ KEZ kodluyordu (bir kez kök görsel için, bir kez panel için).
    ÖLÇÜLDÜ: 6048×12256'lık dikey telefon mozaiğinde kodlama başına **38 ms** — yani istek
    başına 38 ms saf israf, üstelik iki dağıtımda da. Planın "ek CPU YOK" iddiası ancak bu
    yeniden kullanımla doğru olur.

    ⚠️ İKİNCİ FAYDA: kök görsel ile `07_combined` paneli artık BİT-BİT aynı. Ayrı kodlanırsa
    ileride biri kapak/kalite değiştirdiğinde sessizce ayrışırlardı — aynı kare, iki farklı
    çözünürlük (istemcinin oran kilidi hangisini okuduğuna göre işaretler kayardı).

    ⚠️ YEDEK KARE **ORİJİNAL GİRDİ OLMALI**, mozaiğin kendisi DEĞİL. İlk yazımda yedek yol
    `panels["07_combined"]`i yeniden kodluyordu; oysa panel listede yoksa sebebi zaten o karenin
    KODLANAMAMASIDIR — aynı kareyi yeniden kodlamak aynı hatayı verir ve analizin TAMAMI 500'e
    döner (testte bizzat ölçüldü). Orijinal girdi kodlanınca operatör en azından görüntüyü ve
    kalan 6 paneli görür; analiz kaybolmaz.
    """
    for p in paneller or ():
        if p.get("k") == KOK_PANEL:
            return p["image_base64"], {"image_w": p["image_w"], "image_h": p["image_h"]}
    bayt, boyut = yedek_kodlayici(yedek_kare)
    return base64.b64encode(bayt).decode("utf-8"), boyut
