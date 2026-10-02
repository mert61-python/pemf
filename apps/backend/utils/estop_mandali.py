# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ACİL DURDURMA MANDALI + SÜRÜŞ NESLİ — D1.81 · B-5.3 · sahip kararı Y4. Yaprak modül (yalnız stdlib).

SAHİP KARARI (SAHIP-CEVAPLARI.md Y4): "E-stop MANDALLANIR; operatörün ayrı ve bilinçli 'sıfırla' eylemi olmadan
hiçbir START kabul edilmez." Kapsam: elle başlatma, AI (Auto), AI Pro `/frame` ve döngüsü, mobil yol, legacy
`/api/hardware/command` — HEPSİ. Sıfırlama kendi başına BAŞLATMAZ; ardından ayrıca yeni bir START gerekir.

İKİ MEKANİZMA:
  * MANDAL — her acil durdurma (`api_server._emergency_stop_all`, bütün kaynakları: düğme, STM kopması, STM reddi,
    STM watchdog'u, ESP alarmı) kurar; YALNIZ `sifirla()` (operatörün `POST /api/hardware/estop_mandali/sifirla`
    eylemi) kaldırır. Mandal kuruluyken her START reddedilir.
  * SÜRÜŞ NESLİ — her durdurma (acil durdurma, `stop_all_coils`, seans / AI Pro durdurma, STM kopması) ve mandal
    kuruluyken yapılan Sıfırla nesli bir artırır. Bir START niyeti nesli NİYET ANINDA alır (istek girişi ya da seans
    mührü); sürüş anında nesil değişmişse START REDDEDİLİR. Böylece tahmin/lokalizasyon sırasında (0,3–2,2 sn) gelen
    durdurma ve "durdur → sıfırla → yeni seans" (ABA) sırası uçuştaki ESKİ niyeti diriltemez — "seans aktif mi"
    yeniden denetimi bunu yakalayamaz (yeni seans aktiftir), mandal da yakalayamaz (sıfırlandı). Mandal KURULUYKEN
    alınmış niyet de Sıfırla'dan sonra bayattır (Sıfırla'nın kendi artırımı).

⚠️ DENETİM YERİ: kontrol `HardwareController.update_coil` / `start_all_coils` içinde DURUM KİLİDİ ALTINDA yapılır.
"Tahmin sonrası yeniden denetim" denetle-sonra-yap aralığı bırakır (İG-5.3: yama F 30'da 1 kaçırdı). ESP yayınında
kilit tutulamaz (yayın saniyeler sürer; STOP'u bekletemez) → ESP START'ı yayından ÖNCE denetlenir, yayın SIRASINDA
durdurma geldiyse ardından TELAFİ STOP'u gönderilir (`api_server._esp_start_yayinla`).

⚠️ Ö.4-Y8: Bu modül YALNIZ START'ı reddeder. STOP / acil durdurma hiçbir koşulda buradan geçmez; mandal ya da
nesil onları kapılayamaz. Durdurmalar yalnız nesli artırır (gönderim azalmaz).

NİYET BAĞLAMI (`surus_baglami`): sürüş çağrıları imza değiştirmeden nesli taşır — `contextvars` değişkeni
`asyncio.to_thread` iş parçacığına KOPYALANIR. Bağlam yoksa yalnız mandal denetlenir (elle tekil/batch: niyet ile
sürüş arasında await yok).

BELLEKTE tutulur: süreç yeniden başlarsa mandal kalkar. Yeniden başlatma uçuştaki her niyeti ve döngüyü zaten
öldürür; çekirdek bütün bobinleri durmuş başlatır, firmware ölü-adam devresi de keser.
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
import time

MANDAL_MESAJI = (
    "ACİL DURDURMA MANDALLI — yeni başlatma reddedildi. Bobinleri kontrol edin, ekrandaki 'Sıfırla' ile "
    "mandalı kaldırın ve başlatmayı yeniden verin."
)
NESIL_MESAJI = "Komut bir durdurma ya da acil durdurmadan ÖNCEYE ait (bayat sürüş niyeti) — uygulanmadı. Gerekirse yeniden başlatın."

_kilit = threading.Lock()
_durum = {"aktif": False, "neden": "", "zaman": 0.0, "sifirlama_zamani": 0.0, "sifirlayan": ""}
_nesil = 0
_baglam: contextvars.ContextVar = contextvars.ContextVar("pemf_surus_nesli", default=None)


def nesil() -> int:
    """Şu anki sürüş nesli (START niyeti bunu alır)."""
    with _kilit:
        return _nesil


def mandalli_mi() -> bool:
    with _kilit:
        return bool(_durum["aktif"])


def mandalla(neden: str = "") -> int:
    """Acil durdurma: mandalı KUR ve nesli artır. Kilit dışında hiçbir şey beklemez (STOP'u geciktirmez)."""
    global _nesil
    with _kilit:
        _durum["aktif"] = True
        _durum["neden"] = str(neden or "")[:80]
        _durum["zaman"] = time.time()
        _nesil += 1
        return _nesil


def nesil_artir() -> int:
    """Durdurma: uçuştaki START niyetlerini geçersiz kıl (mandala dokunmaz)."""
    global _nesil
    with _kilit:
        _nesil += 1
        return _nesil


def sifirla(kaynak: str = "") -> bool:
    """Operatörün bilinçli eylemi: mandalı KALDIR. HİÇBİR ŞEYİ BAŞLATMAZ. @return mandal kurulu muydu.

    ⚠️ Mandal kuruluyken NESLİ DE ARTIRIR (1-C inceleme i1-F1): E-stop ÖNCESİ alınmış niyetler E-stop'un artırdığı
    nesille zaten bayattır; ama mandal KURULUYKEN alınmış bir niyetin nesli E-stop SONRASI nesildir — artırılmasa
    Sıfırla'dan sonra "taze" görünür ve yeni bir START olmadan sürerdi (ölçüldü: çıkarım sürerken basılan Sıfırla ile
    AI (Auto) 30/30 sürdü; Y4: "sıfırlama kendi başına yeniden başlatmaz"). Mandal yokken Sıfırla nesle DOKUNMAZ
    (boş Sıfırla uçuştaki geçerli niyetleri öldürmesin). STOP göndermez, STOP'u kapılamaz (Ö.4-Y8)."""
    global _nesil
    with _kilit:
        onceki = bool(_durum["aktif"])
        _durum["aktif"] = False
        if onceki:
            _durum["sifirlama_zamani"] = time.time()
            _durum["sifirlayan"] = str(kaynak or "")[:80]
            _nesil += 1
        return onceki


def durum() -> dict:
    """Arayüz/sağlık/WS için anlık görüntü (yalnız JSON türleri)."""
    with _kilit:
        return {
            "aktif": bool(_durum["aktif"]),
            "neden": _durum["neden"],
            "zaman": _durum["zaman"],
            "sifirlamaZamani": _durum["sifirlama_zamani"],
            "nesil": _nesil,
        }


def baslatma_engeli(niyet_nesli=None) -> str:
    """START'ı engelleyen durum; "" = engel yok. `niyet_nesli` verilmişse ve bayatsa reddedilir.

    ⚠️ YALNIZ START için çağrılır. STOP yolları bunu ÇAĞIRMAZ (Ö.4-Y8)."""
    with _kilit:
        if _durum["aktif"]:
            return MANDAL_MESAJI
        if niyet_nesli is not None and niyet_nesli != _nesil:
            return NESIL_MESAJI
    return ""


@contextlib.contextmanager
def surus_baglami(niyet_nesli):
    """Blok içindeki (ve `asyncio.to_thread` ile açılan) sürüş çağrıları bu niyetin neslini taşır."""
    jeton = _baglam.set(niyet_nesli)
    try:
        yield
    finally:
        _baglam.reset(jeton)


def baglam_nesli():
    """Geçerli bağlamdaki niyet nesli (yoksa None → yalnız mandal denetlenir)."""
    return _baglam.get()
