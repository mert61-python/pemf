# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN KAMERASI — seçim (cihaz düzeyi) ve açılış. T2D-2 · Tezgâh-2 #3. AI Pro hazırlık önizlemesi ve seans döngüsü
kamerayı YALNIZ buradan açar.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23): `ai_router` sabit `cv2.VideoCapture(0)` açıyordu → dahili kameralı dizüstünde kabin
kamerası (Pusat, Windows'ta "FHD Camera") DEĞİL dahili kamera açıldı; çözünürlük istenmediği için kare 640×480 geldi
(1080p kalibrasyonu geçersiz, 640×480 ↔ 1080p görüş alanı farklı).

SÖZLEŞME:
  * Kamera cihaz düzeyinde SEÇİLİR (T3 · Y190: petri / fantom analiz panelinde ve AI Pro panelinde "Kabin kamerası" bölümü;
    Ayarlar'dan kaldırıldı) ve `<veri kökü>/kabin_kamerasi.json`'da hatırlanır — hesaptan / profilden bağımsız (dil seçimi gibi, Y161).
  * Seçim yoksa kamera AÇILMAZ: `KameraSecilmedi` (çağıran eylem söyleyen iletiyi verir). 0 numaralı (çoğu dizüstünde dahili)
    kameraya SESSİZ düşüş YOK.
  * Açılır açılmaz, İLK okumadan ÖNCE çözünürlük istenir (KD madde 0: sabit düzlem kalibrasyonu varsa ONUN boyutu, yoksa kameranın
    EN YÜKSEK kendi modu — `istenen_cozunurluk`; eskiden sabit 1920×1080) — MSMF'de akış başladıktan sonra çözünürlük değiştirmek `(-215)
    _step >= minstep` hatası verir (Tezgâh-2 ölçümü). Kamera başka boyut verirse kare o boyutta gelir; K ölçeklemesi kenar
    oranı farklıysa reddedilir (`cv_ortak.coord_transform.olcekli_intrinsics`).
  * CANLI oturum (T3 · Y190, petri / fantom canlı önizleme + otomatik analiz): seçili kamera arka planda AÇIK tutulur, son kare
    bellekte (`canli_baslat` / `canli_kare` / `canli_durdur`). Her karede kamerayı açıp kapamak saniyeler sürerdi. Oturum
    `CANLI_ZAMAN_ASIMI_SN` boyunca kare istenmezse kendiliğinden kapanır (sekme kapandı → kamera bırakılır). `kamera_ac` (AI Pro
    hazırlık / seans, tek kare) açık canlı oturumu ÖNCE kapatır — AI Pro önceliklidir, iki `VideoCapture` çakışmaz.
  * KİMLİK (KD-2, sahip kararı): seçim indeksle BİRLİKTE kameranın Windows ADI + VID/PID + AYGIT YOLU ile saklanır
    (`kamera_kimligi`). Açılışta MSMF sırası yeniden okunur: önce aygıt yolu, yol değişmişse (başka USB girişi) ad + VID/PID'i TEK
    olan aygıt; bulunamazsa kamera AÇILMAZ (`KameraBulunamadi`) — MSMF sırası değişince (KD-1: Pusat 1 → 0) yanlış kameraya düşülmez.
    Aygıt listesi okunamıyorsa (Windows dışı / MF hatası) saklı indeks kullanılır ve günlüğe yazılır.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

KAMERA_DOSYASI = "kabin_kamerasi.json"
ORTAM_DEGISKENI = "PEMF_KABIN_KAMERASI"
#: OpenCV `CAP_PROP_FRAME_WIDTH` / `HEIGHT` (kararlı sayılar; cv2 sabiti yoksa).
_CAP_GENISLIK, _CAP_YUKSEKLIK = 3, 4
#: Ayarlar'daki taramada denenecek indeksler (0..N-1). OpenCV kamera ADI vermez; kullanıcı küçük önizlemeden tanır.
TARAMA_INDEKS_SAYISI = 4
_AZAMI_INDEKS = 63
_ONIZLEME_GENISLIK = 240


class KameraSecilmedi(RuntimeError):
    """Kabin kamerası seçilmemiş — kamera açılmadı (dahili kameraya sessiz düşüş yok)."""


class KameraBulunamadi(KameraSecilmedi):
    """KD-2: seçili kameranın KİMLİĞİ (ad + VID/PID + aygıt yolu) bağlı aygıtlarda yok — kamera AÇILMADI (başka kameraya düşüş yok).
    `KameraSecilmedi` alt sınıfı: her yakalayıcı kamerayı açmadan durur; ileti `secim_hatasi_metni` ile kimliği söyler."""

    def __init__(self, secim: dict):
        super().__init__(secim)
        self.secim = dict(secim or {})


def secim_hatasi_metni(e: Exception) -> str:
    """`KameraSecilmedi` / `KameraBulunamadi` → istek dilinde EYLEM metni."""
    from utils import ceviri

    if isinstance(e, KameraBulunamadi):
        k = e.secim.get("kimlik") or {}
        p = {"ad": str(k.get("ad") or "?"), "vidpid": str(k.get("vidpid") or "?")}
        return ceviri.t("ayarlar.kabinKamerasi.kimlikBulunamadi", **p)
    return ceviri.t("ai.pro.hazirlik.kameraSecilmedi")


class KameraMesgul(RuntimeError):
    """D3I-A3.2: canlı oturum başlatılırken kamerayı AI Pro (hazırlık / seans) devraldı — canlı AÇILMADI (AI Pro önceliği)."""


def _veri_koku() -> Path:
    from utils.path_utils import get_app_data_directory

    return Path(get_app_data_directory())


def _gecerli_indeks(deger) -> int | None:
    if isinstance(deger, bool) or not isinstance(deger, int):
        return None
    return deger if 0 <= deger <= _AZAMI_INDEKS else None


def _ortam_indeksi() -> int | None:
    ham = (os.environ.get(ORTAM_DEGISKENI) or "").strip()
    try:
        return _gecerli_indeks(int(ham)) if ham else None
    except ValueError:
        return None


def secili_kamera() -> dict | None:
    """Seçili kabin kamerası `{"indeks": int, "kaynak": "ortam" | "ayar", "kimlik": {"ad", "vidpid", "aygit_yolu"} | None}`; hiç
    seçilmemiş / dosya bozuk → None. `PEMF_KABIN_KAMERASI` (tezgâh / kiosk) ayarın ÖNÜNDEdir (kimliksiz); sahada tanımlı değildir."""
    i = _ortam_indeksi()
    if i is not None:
        return {"indeks": i, "kaynak": "ortam"}
    try:
        veri = json.loads((_veri_koku() / KAMERA_DOSYASI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    indeks = _gecerli_indeks(veri.get("indeks")) if isinstance(veri, dict) else None
    if indeks is None:
        return None
    k = veri.get("kimlik")
    kimlik = (
        {"ad": k.get("ad"), "vidpid": k.get("vidpid"), "aygit_yolu": k.get("aygit_yolu")}
        if isinstance(k, dict) and k.get("vidpid")
        else None
    )
    # Kimlik YALNIZ biliniyorsa alan olarak eklenir (KD-2 öncesi seçim / ortam değişkeni: sözlük biçimi değişmez).
    return {"indeks": indeks, "kaynak": "ayar", **({"kimlik": kimlik} if kimlik else {})}


def kamera_sec(indeks) -> dict:
    """Seçimi atomik yazar (geçici dosya + os.replace). Geçersiz indeks → ValueError; disk hatası → OSError. KD-2: o anki MSMF
    listesinden bu indeksin KİMLİĞİ de yazılır (okunamazsa kimliksiz — açılış indekse düşer)."""
    from utils import kamera_kimligi

    i = _gecerli_indeks(indeks)
    if i is None:
        raise ValueError(indeks)
    kimlik = next(
        (
            {k: a.get(k) for k in ("ad", "vidpid", "aygit_yolu")}
            for a in kamera_kimligi.msmf_kameralar()
            if a.get("indeks") == i
        ),
        None,
    )
    kok = _veri_koku()
    kok.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=str(kok), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"indeks": i, **({"kimlik": kimlik} if kimlik else {})}, f, ensure_ascii=False)
        os.replace(gecici, kok / KAMERA_DOSYASI)
    except Exception:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise
    return {"indeks": i, "kaynak": "ayar", **({"kimlik": kimlik} if kimlik else {})}


#: KD madde 0 (2026-11-10): kalibrasyon YOKSA kameranın EN YÜKSEK kendi modu — büyük değer istenir, sürücü desteklediği en büyük
#: modu verir (ölçüldü: Pusat ve dahili HP, 9999×9999 → 1920×1080; yükseltme / ölçekleme YOK). Gelen kare boyutu kullanılır.
AZAMI_ISTEK = (9999, 9999)


def istenen_cozunurluk() -> tuple[int, int] | None:
    """SABİT DÜZLEM kalibrasyonu (veri kökü) varsa ONUN çözünürlüğü — kalibrasyon yalnız o boyutta geçerlidir; yoksa / okunamazsa None
    (= kameranın en yüksek kendi modu). Bozuk kalibrasyon çözünürlük SEÇMEZ (hat onu zaten "bozuk" diye reddeder)."""
    try:
        from ai_hub.cv_ortak import sabit_duzlem as sd

        kal, hata = sd.yukle(_veri_koku())
    except Exception:
        logging.getLogger(__name__).debug("kabin kamerasi: kalibrasyon cozunurlugu okunamadi", exc_info=True)
        return None
    if kal is None or hata:
        return None
    try:
        return int(kal["kamera"]["genislik"]), int(kal["kamera"]["yukseklik"])
    except (KeyError, TypeError, ValueError):
        return None


def _cozunurluk_iste(cap, cv2) -> None:
    """Çözünürlük isteği (ilk okumadan ÖNCE — sonra değiştirmek MSMF `_step >= minstep`): kalibrasyon varsa onun boyutu, yoksa
    `AZAMI_ISTEK` (kameranın en yüksek modu). Kamera desteklemezse OpenCV yok sayar; istek hatası kamerayı DÜŞÜRMEZ (günlük)."""
    w, h = istenen_cozunurluk() or AZAMI_ISTEK
    try:
        cap.set(getattr(cv2, "CAP_PROP_FRAME_WIDTH", _CAP_GENISLIK), float(w))
        cap.set(getattr(cv2, "CAP_PROP_FRAME_HEIGHT", _CAP_YUKSEKLIK), float(h))
    except Exception:
        logging.getLogger(__name__).warning("kabin kamerasi: %sx%s istegi uygulanamadi", w, h, exc_info=True)


def acilacak_indeks(secim: dict) -> int:
    """KD-2: saklı KİMLİĞİ bugünkü MSMF listesinde bul → açılacak indeks. Kimlik yoksa (eski seçim / ortam değişkeni) ya da liste
    okunamıyorsa saklı indeks. Liste okunup kimlik BULUNAMAZSA `KameraBulunamadi` (kamera açılmaz)."""
    from utils import kamera_kimligi

    k = secim.get("kimlik")
    if not k:
        return int(secim["indeks"])
    aygitlar = kamera_kimligi.msmf_kameralar()
    if not aygitlar:
        logging.getLogger(__name__).warning(
            "kabin kamerasi: aygit listesi okunamadi — sakli indeks %s kullaniliyor", secim["indeks"]
        )
        return int(secim["indeks"])
    indeks, yol = kamera_kimligi.esle(k, aygitlar)
    if indeks is None:
        logging.getLogger(__name__).error(
            "kabin kamerasi: secili kamera (%s %s) bagli aygitlarda yok — ACILMADI. Aygitlar: %s",
            k.get("ad"),
            k.get("vidpid"),
            [(a.get("indeks"), a.get("ad"), a.get("vidpid")) for a in aygitlar],
        )
        raise KameraBulunamadi(secim)
    if yol == "ad_vidpid":
        logging.getLogger(__name__).info(
            "kabin kamerasi: aygit yolu degismis (baska USB girisi) — ad + VID/PID ile indeks %s", indeks
        )
    if indeks != int(secim["indeks"]):
        logging.getLogger(__name__).info(
            "kabin kamerasi: MSMF sirasi degismis — indeks %s → %s", secim["indeks"], indeks
        )
    return int(indeks)


def secim_baglanti(secim: dict | None) -> dict:
    """AP-23: seçili kameranın BUGÜN bağlı olup olmadığı — kamera AÇILMAZ (yalnız MSMF aygıt listesi; `acilacak_indeks`le aynı eşleme).
    `bagli`: True / False (liste okundu, kimlik yok) / None (kimliksiz eski seçim, ortam değişkeni ya da liste okunamadı → bilinmiyor);
    `guncelIndeks`: kimliğin bugünkü MSMF indeksi (sıra değiştiyse saklı indeksten farklı) ya da None."""
    from utils import kamera_kimligi

    k = (secim or {}).get("kimlik")
    aygitlar = kamera_kimligi.msmf_kameralar() if k else []
    if not aygitlar:
        return {"bagli": None, "guncelIndeks": None}
    indeks, _yol = kamera_kimligi.esle(k, aygitlar)
    return {"bagli": indeks is not None, "guncelIndeks": None if indeks is None else int(indeks)}


def kamera_ac(cv2=None, *, canliyi_kapat: bool = True):
    """Seçili kabin kamerasını açar ve (açıldıysa) ilk okumadan ÖNCE çözünürlük ister (`_cozunurluk_iste`). @return (cap, indeks) — açılıp
    açılmadığını çağıran `cap.isOpened()` ile denetler. Seçim yoksa `KameraSecilmedi` (kamera hiç açılmaz).
    Y190: açık CANLI oturum önce kapatılır (AI Pro / tek kare kamerayı devralır); canlı oturumun kendisi `canliyi_kapat=False`."""
    secim = secili_kamera()
    if secim is None:
        raise KameraSecilmedi()
    indeks = acilacak_indeks(secim)
    if canliyi_kapat:
        # D3I-A3.2: açılışı SÜREN canlı başlatma önce kaydolsun (kilit), sonra kapatılsın — yoksa ikisi de kamerayı tutar.
        # Bekleme SINIRLI (`KAMERA_DEVIR_BEKLE_SN`): canlının açılışı asılırsa (sürücü) AI Pro hazırlık / seans döngüsü süresiz
        # beklemez — süre dolunca eski davranışla (kilitsiz denetim) sürer.
        alindi = _canli_baslat_kilit.acquire(timeout=KAMERA_DEVIR_BEKLE_SN)
        if not alindi:
            logging.getLogger(__name__).warning(
                "kabin kamerasi: canli baslatma %.1f sn'de bitmedi — kamera kilitsiz devraliniyor",
                KAMERA_DEVIR_BEKLE_SN,
            )
        try:
            if canli_acik():
                logging.getLogger(__name__).info("kabin kamerasi: canli oturum kapatiliyor (kamera devralindi)")
                canli_durdur()
        finally:
            if alindi:
                _canli_baslat_kilit.release()
    if cv2 is None:
        import cv2
    cap = cv2.VideoCapture(indeks)
    if cap.isOpened():
        _cozunurluk_iste(cap, cv2)
    return cap, indeks


#: T3 · Y189: tek karede otomatik pozlama / beyaz dengesi oturana dek atılan ilk kare sayısı.
KARE_ISINMA = 5


def kare_al(cv2=None, adet: int = 1) -> dict | None:
    """T3 · Y189 / Y190 (petri / fantom analizi "Fotoğraf Çek", bu makinede): SEÇİLİ kabin kamerasından TAM çözünürlüklü tek kare (JPEG,
    base64). `kamera_ac` ile açılır (çözünürlük ilk okumadan ÖNCE), ilk `KARE_ISINMA` kare atılır, son kare kodlanır, kamera
    HER durumda bırakılır. Seçim yok → `KameraSecilmedi`; açılamaz / okunamaz → None.
    D3I-A3.2: eşzamanlı çağrılar (çift dokunuş, iki istemci) SIRAYLA — aynı kameraya iki `VideoCapture` açılmaz.
    KD-2: `adet` > 1 → aynı açılışta son `adet` kare (`ek_kareler`, kalibrasyon ortalaması; canlı oturumdan yalnız son kare).
    Sonuçta seçimin `kimlik`i (ad + VID/PID + aygıt yolu) da döner."""
    with _kisa_acilis_kilit:
        k = _kare_al(cv2, max(1, int(adet)))
    kimlik = (secili_kamera() or {}).get("kimlik") if k is not None else None
    if kimlik:
        k["kimlik"] = kimlik
    return k


def _kare_al(cv2=None, adet: int = 1) -> dict | None:
    if cv2 is None:
        import cv2
    if canli_acik():
        # Y190: canlı oturum kamerayı tutuyor → son tam kare oradan (ikinci `VideoCapture` açılmaz). Y192: kare henüz yoksa
        # canlıyı KAPATMADAN None (kare alınamadı); oturum bu arada kapandıysa normal yoldan açılır.
        k = canli_kare(tam=True, cv2=cv2, bekle_sn=CANLI_ILK_KARE_BEKLE_SN)
        if k is not None:
            return k if k.get("hazir") else None
    cap, indeks = kamera_ac(cv2)
    try:
        if not cap.isOpened():
            return None
        kareler = []
        for _ in range(KARE_ISINMA + adet):
            ok, k = cap.read()
            if ok and k is not None:
                kareler.append(k)
        if not kareler:
            return None
        kodlu = []
        for k in kareler[-adet:]:
            basarili, tampon = cv2.imencode(".jpg", k, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if basarili:
                kodlu.append(base64.b64encode(tampon).decode("ascii"))
        if not kodlu:
            return None
        kh, kw = kareler[-1].shape[:2]
        sonuc = {
            "indeks": indeks,
            "genislik": int(kw),
            "yukseklik": int(kh),
            "image_base64": kodlu[-1],
        }
        if adet > 1:
            sonuc["ek_kareler"] = kodlu[:-1]
        return sonuc
    finally:
        cap.release()


# ── CANLI OTURUM (T3 · Y190) ──────────────────────────────────────────────────────────────────────────────────────────
#: Bu kadar saniye kare istenmezse canlı oturum kendiliğinden kapanır (sekme kapandı / ağ koptu → kamera bırakılır).
CANLI_ZAMAN_ASIMI_SN = 10.0
#: Önizleme karesinin genişliği (tam kare analizde; önizleme yalnız göstermek için küçük ve hızlı).
CANLI_ONIZLEME_GENISLIK = 960
#: T3 · Y192: oturum açık ama okuyucunun İLK karesi henüz yoksa uç / tek kare bu kadar saniye bekler (ölçülen HP kamerası: başlatma
#: 0,28 sn, ilk kare ~0,5 sn sonra). Beklemeden "kapalı" demek arayüzün canlıyı durdurmasına yol açıyordu.
CANLI_ILK_KARE_BEKLE_SN = 2.0
_canli_kilit = threading.Lock()
_canli_baslat_kilit = threading.Lock()
#: D3I-A3.2: `kamera_ac` (AI Pro / tek kare) açılışı süren bir canlı başlatmayı en çok bu kadar bekler (sonra kilitsiz devralır).
KAMERA_DEVIR_BEKLE_SN = 3.0
#: D3I-A3.2: kısa açılışlar (tek kare, tarama) sırayla — aynı kameraya eşzamanlı ikinci `VideoCapture` yok.
_kisa_acilis_kilit = threading.Lock()
_canli: dict | None = None


def canli_acik() -> bool:
    d = _canli
    return d is not None and d["is"].is_alive() and not d["dur"].is_set()


def _canli_okuyucu(d: dict, cap) -> None:
    try:
        while not d["dur"].is_set():
            if time.monotonic() - d["son_erisim"] > CANLI_ZAMAN_ASIMI_SN:
                logging.getLogger(__name__).info("kabin kamerasi: canli oturum zaman asimi — kamera birakiliyor")
                break
            ok, k = cap.read()
            if ok and k is not None:
                with _canli_kilit:
                    d["kare"], d["zaman"] = k, time.monotonic()
            time.sleep(0.03)
    except Exception:
        logging.getLogger(__name__).warning("kabin kamerasi: canli okuyucu durdu", exc_info=True)
    finally:
        d["dur"].set()
        try:
            cap.release()
        except Exception:
            pass


def canli_baslat(cv2=None, mesgul=None) -> dict | None:
    """Seçili kamerayı AÇIK tutan okuyucuyu başlatır (açıksa aynısı). Seçim yok → `KameraSecilmedi`; açılamaz → None.
    Eşzamanlı iki başlatma (çift dokunuş, iki sekme) İKİ `VideoCapture` açmaz (`_canli_baslat_kilit`).
    D3I-A3.2: `mesgul` (çağıranın AI Pro denetimi) KİLİT ALTINDA yeniden sorulur — istek girişte geçip AI Pro kamerayı bu arada
    devraldıysa canlı AÇILMAZ (`KameraMesgul`)."""
    global _canli
    if cv2 is None:
        import cv2
    with _canli_baslat_kilit:
        if mesgul is not None and mesgul():
            raise KameraMesgul()
        with _canli_kilit:
            if canli_acik():
                _canli["son_erisim"] = time.monotonic()
                return {"indeks": _canli["indeks"], "acik": True}
        cap, indeks = kamera_ac(cv2, canliyi_kapat=False)
        if not cap.isOpened():
            cap.release()
            return None
        d = {
            "dur": threading.Event(),
            "kare": None,
            "zaman": 0.0,
            "son_erisim": time.monotonic(),
            "indeks": indeks,
            "cv2": cv2,
        }
        d["is"] = threading.Thread(target=_canli_okuyucu, args=(d, cap), name="kabin-canli", daemon=True)
        with _canli_kilit:
            _canli = d
        d["is"].start()
        return {"indeks": indeks, "acik": True}


def canli_kare(tam: bool = False, cv2=None, bekle_sn: float = 0.0) -> dict | None:
    """Canlı oturumun SON karesi (JPEG, base64): `tam` = kalibrasyon boyutunda (analiz), değilse küçük önizleme. Oturum YOKSA None;
    oturum açık ama ilk kare henüz gelmediyse (`bekle_sn` kadar beklendikten sonra) `{"indeks", "hazir": False}` — T3 · Y192: bu
    durum "kapalı" DEĞİLDİR. Her çağrı oturumu canlı tutar (zaman aşımı sayacı sıfırlanır)."""
    d = _canli
    if d is None or not canli_acik():
        return None
    d["son_erisim"] = time.monotonic()
    son = time.monotonic() + max(0.0, float(bekle_sn))
    while True:
        with _canli_kilit:
            kare = d["kare"]
            zaman = d["zaman"]
        if kare is not None or time.monotonic() >= son or not canli_acik():
            break
        time.sleep(0.02)
    if kare is None:
        return {"indeks": d["indeks"], "hazir": False} if canli_acik() else None
    if cv2 is None:
        cv2 = d.get("cv2")
        if cv2 is None:
            import cv2
    kh, kw = kare.shape[:2]
    if not tam and kw > CANLI_ONIZLEME_GENISLIK:
        olcek = CANLI_ONIZLEME_GENISLIK / float(kw)
        kare = cv2.resize(kare, (CANLI_ONIZLEME_GENISLIK, max(1, int(kh * olcek))))
    basarili, tampon = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, 92 if tam else 70])
    if not basarili:
        return {"indeks": d["indeks"], "hazir": False}
    oh, ow = kare.shape[:2]
    return {
        "indeks": d["indeks"],
        "hazir": True,
        "genislik": int(ow),
        "yukseklik": int(oh),
        "yas_ms": int(max(0.0, time.monotonic() - zaman) * 1000),
        "image_base64": base64.b64encode(tampon).decode("ascii"),
    }


def canli_durdur(bekle_sn: float = 3.0) -> None:
    """Canlı oturumu kapatır ve okuyucunun kamerayı bırakmasını bekler (açık değilse hiçbir şey yapmaz)."""
    global _canli
    with _canli_kilit:
        d, _canli = _canli, None
    if d is None:
        return
    d["dur"].set()
    if d["is"].is_alive() and d["is"] is not threading.current_thread():
        d["is"].join(timeout=bekle_sn)


def kameralari_tara(cv2=None, sayi: int = TARAMA_INDEKS_SAYISI) -> list[dict]:
    """Analiz / AI Pro paneli ▸ Kabin kamerası ▸ "Kameraları tara": 0..sayi-1 indekslerini KISA açar, çözünürlük ister (`_cozunurluk_iste`), bir kare okur, bırakır.
    @return açılanların listesi `[{"indeks", "genislik", "yukseklik", "onizleme"}]` (önizleme: küçük JPEG, base64; kare
    okunamazsa None). Yalnız kullanıcı eylemiyle çağrılır (açılış / arka plan taraması YOK). D3I-A3.2: tek kare ile sırayla."""
    with _kisa_acilis_kilit:
        return _kameralari_tara(cv2, sayi)


def _kameralari_tara(cv2=None, sayi: int = TARAMA_INDEKS_SAYISI) -> list[dict]:
    if cv2 is None:
        import cv2
    from utils import kamera_kimligi

    adlar = {a["indeks"]: a for a in kamera_kimligi.msmf_kameralar()}
    sonuc: list[dict] = []
    for i in range(max(0, int(sayi))):
        cap = cv2.VideoCapture(i)
        try:
            if not cap.isOpened():
                continue
            _cozunurluk_iste(cap, cv2)
            ok, kare = cap.read()
            oge = {
                "indeks": i,
                "genislik": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
                "yukseklik": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
                "onizleme": None,
                "ad": (adlar.get(i) or {}).get("ad"),
                "vidpid": (adlar.get(i) or {}).get("vidpid"),
            }
            if ok and kare is not None:
                kh, kw = kare.shape[:2]
                oge["genislik"], oge["yukseklik"] = int(kw), int(kh)
                olcek = min(1.0, _ONIZLEME_GENISLIK / float(max(1, kw)))
                kucuk = cv2.resize(kare, (max(1, int(kw * olcek)), max(1, int(kh * olcek))))
                basarili, tampon = cv2.imencode(".jpg", kucuk, [cv2.IMWRITE_JPEG_QUALITY, 60])
                if basarili:
                    oge["onizleme"] = base64.b64encode(tampon).decode("ascii")
            sonuc.append(oge)
        finally:
            cap.release()
    return sonuc
