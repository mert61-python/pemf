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
    ⚠️ Y45 (sahip, 1-C inceleme i3-F-7'nin cevabı): STM kopması / firmware watchdog'u anında HERHANGİ bir bobin
    çalışıyorsa — seans olsun olmasın — mandal KURULUR (STOP'tan ÖNCE, kapısız; `api_server._y45_mandal_kur`). Aktif STM
    seansında kurulum `_emergency_stop_all`'dan gelir. Boştayken kartın çıkıp takılması mandal KURMAZ.
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

KAPANIŞ (D1.75 · B-1.22): backend kapanırken `kapanis_kur` aynı mandalı ikinci bir durumla (süreç sonuna dek START reddi)
kurar — ayrı bir "kapanış mandalı" YOK (plan: iki mandal yan yana doğarsa biri ötekini atlatabilir). Sıfırla kaldırmaz,
diske yazılmaz (bkz. `kapanis_kur`).

⚠️ Ö.4-Y8: Bu modül YALNIZ START'ı reddeder. STOP / acil durdurma hiçbir koşulda buradan geçmez; mandal ya da
nesil onları kapılayamaz. Durdurmalar yalnız nesli artırır (gönderim azalmaz).

NİYET BAĞLAMI (`surus_baglami`): sürüş çağrıları imza değiştirmeden nesli taşır — `contextvars` değişkeni
`asyncio.to_thread` iş parçacığına KOPYALANIR. Her HTTP isteği, isteğin VARIŞ anındaki nesille bağlam içinde koşar
(`api_server._SurusNiyetiVarisDamgasi`; gövde okunmadan önce) — tekil/batch/legacy de bu nesli taşır. İç bir
`surus_baglami` (seans mührü: `/frame`, AI Pro döngüsü) onu geçersiz kılar. Bağlam yoksa (istek dışı iş parçacığı)
yalnız mandal denetlenir.

KALICILIK (sahip kararı Y46, 1-C §9 S2): mandal DİSKE yazılır; çökme, launcher/servis yeniden başlatması ya da güncelleme
sonrasında "Sıfırla"ya basılana kadar kurulu kalır. Eskiden yalnız bellekteydi: süreç yeniden başlayınca mandal
Sıfırla'sız kalkıyordu. Kurallar:
  * Dosya STOP'lar gönderildikten SONRA, ARKA PLANDA yazılır (`diske_yaz_arka_planda`); yazma başarısız olursa yalnız
    günlüğe yazılır — ACİL DURDUR'u ASLA geciktirmez ya da engellemez (Ö.4-Y8). Yazıcı, YAZIM ANINDAKİ durumu yazar
    (kuyrukta gecikmiş bir "kurulu" yazımı, arkadan gelen Sıfırla'yı ezemez).
  * Açılışta (`kalicilik_kur`) dosya kuruluysa mandal KURULU başlar; neden "önceki oturumda ACİL DURDUR — sıfırlanmadı".
  * Dosya VAR ama okunamıyor/bozuksa mandal KURULU başlar (güvenli taraf: yanlış mandalın bedeli bir Sıfırla). Dosya
    YOKSA mandal yok (ilk kurulum / hiç E-stop olmamış).
  * Kalıcılık kurulmadıysa (testler, araçlar) davranış eskisi gibi bellekte.
  * Y59 (sahip, 1-E S-İ1): dosya YAZILAMAZSA operatöre SÖYLENİR (`yazim_durumu`, `yazim_hatasi_kancasi_bagla`): Sıfırla
    ve ACİL DURDUR yanıtı + ekran bildirimi "yeniden başlatmada mandal geri gelecek / KORUNMAYACAK". Davranış AYNEN:
    E-stop yazımı beklemez (yanıt SON BİLİNEN durumu taşır — açılış yoklaması ya da önceki yazım), Sıfırla mandalı her
    durumda kaldırır (Y56).
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import threading
import time
from pathlib import Path

MANDAL_MESAJI = (
    "ACİL DURDURMA MANDALLI — yeni başlatma reddedildi. Bobinleri kontrol edin, ekrandaki 'Sıfırla' ile "
    "mandalı kaldırın ve başlatmayı yeniden verin."
)
NESIL_MESAJI = "Komut bir durdurma ya da acil durdurmadan ÖNCEYE ait (bayat sürüş niyeti) — uygulanmadı. Gerekirse yeniden başlatın."

KAYIP_MESAJI = "Hedef gözlemi bir hedef-kaybı durdurmasından ÖNCEYE ait (bayat gözlem) — sürülmedi."

KAPANIS_MESAJI = "Backend KAPANIYOR — yeni başlatma reddedildi (bobinler durduruluyor)."

_kilit = threading.Lock()
_durum = {
    "aktif": False,
    "neden": "",
    "zaman": 0.0,
    "sifirlama_zamani": 0.0,
    "sifirlayan": "",
    "onceki_oturum": False,
    # D1.75 (B-1.22): KAPANIŞ — bu mandalın ikinci durumu (aşağıda `kapanis_kur`). Diske YAZILMAZ, Sıfırla KALDIRMAZ.
    "kapanis": False,
}
_nesil = 0
_baglam: contextvars.ContextVar = contextvars.ContextVar("pemf_surus_nesli", default=None)
# 1-C inceleme i7-F-1: HEDEF-KAYBI nesli (AI Pro) — sürüş neslinden AYRI (bkz. `kayip_nesli_artir`).
_kayip_nesli = 0
_kayip_baglam: contextvars.ContextVar = contextvars.ContextVar("pemf_kayip_damgasi", default=None)


def nesil() -> int:
    """Şu anki sürüş nesli (START niyeti bunu alır)."""
    with _kilit:
        return _nesil


def mandalli_mi() -> bool:
    """START mandalı kurulu mu: acil durdurma mandalı YA DA kapanış (D1.75). Bu işleve bakan her START savunması
    (ESP yayınının son savunması, telafi STOP'u, döngü teardown'ı) kapanışı da görür — yan yana ikinci bir mandal yok."""
    with _kilit:
        return bool(_durum["aktif"] or _durum["kapanis"])


def mandalla(neden: str = "") -> int:
    """Acil durdurma: mandalı KUR ve nesli artır. Kilit dışında hiçbir şey beklemez (STOP'u geciktirmez)."""
    global _nesil
    with _kilit:
        _durum["aktif"] = True
        _durum["neden"] = str(neden or "")[:80]
        _durum["zaman"] = time.time()
        _durum["onceki_oturum"] = False
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
        _durum["onceki_oturum"] = False
        if onceki:
            _durum["sifirlama_zamani"] = time.time()
            _durum["sifirlayan"] = str(kaynak or "")[:80]
            _nesil += 1
        return onceki


def kapanis_kur() -> int:
    """D1.75 (B-1.22): backend KAPANIYOR — süreç sonuna dek her START'ı reddet ve nesli artır (uçuştaki niyetler bayat).

    Bu mandalın ikinci durumudur, ayrı bir mandal DEĞİL: aynı kilit, aynı nesil, aynı kapı (`baslatma_engeli`,
    `mandalli_mi`) → mandala bakan her START yolu kapanışı da görür; biri ötekini atlatamaz. Farkları bilinçli:
      * Sıfırla KALDIRMAZ (operatörün E-stop sıfırlaması kapanan sürece START açmamalı).
      * Diske YAZILMAZ (`_diske_yaz` yalnız `aktif`i yazar): temiz kapanış bir acil durdurma değildir; yeniden
        başlatmada "önceki oturumda ACİL DURDUR" bandı ve Sıfırla'sız START reddi doğurmamalı.
      * Arayüz durumu (`durum()["aktif"]`) değişmez — kapanışta sunucu zaten yanıt vermez.
    ⚠️ Ö.4-Y8: YALNIZ START. STOP / acil durdurma / mutabakat STOP'u bu durumdan GEÇMEZ. @return yeni nesil."""
    global _nesil
    with _kilit:
        _durum["kapanis"] = True
        _nesil += 1
        return _nesil


def kapanis_kaldir() -> None:
    """YALNIZ test yalıtımı (süreç geneli durum testler arası sızmasın). Üründe çağıran YOK: kapanış süreçle biter."""
    with _kilit:
        _durum["kapanis"] = False


def durum() -> dict:
    """Arayüz/sağlık/WS için anlık görüntü (yalnız JSON türleri)."""
    with _kilit:
        return {
            "aktif": bool(_durum["aktif"]),
            "neden": _durum["neden"],
            "zaman": _durum["zaman"],
            "sifirlamaZamani": _durum["sifirlama_zamani"],
            "nesil": _nesil,
            # Y46: mandal önceki süreçten (diskten) geldi — arayüz "önceki oturumda ACİL DURDUR — sıfırlanmadı" der.
            "oncekiOturum": bool(_durum["onceki_oturum"]),
        }


# ── KALICILIK (Y46) ─────────────────────────────────────────────────────────────────────────────────────────────────
_log = logging.getLogger(__name__)
_kalici_yol: Path | None = None
_yazim_kilidi = threading.Lock()
ONCEKI_OTURUM_NEDENI = "onceki_oturum"
#: Y59: son bilinen yazım durumu. `disk_kurulu` = yeniden başlatmada diskten okunacak mandal (okunamayan dosya → kurulu,
#: `kalicilik_kur` kuralı); `yazilamadi` açılış yoklamasından (salt-okunur öznitelik / dosyanın yerinde dizin — HİÇBİR
#: ŞEY YAZILMADAN) ya da son yazım denemesinden gelir.
_yazim: dict = {"yazilamadi": False, "neden": "", "disk_kurulu": False}
_yazim_hatasi_kancasi = None


def yazim_hatasi_kancasi_bagla(fn) -> None:
    """Y59: yazım BAŞARISIZ olunca çağrılır (`fn(yazim_durumu(yol_dahil=True))`) — ekran bildirimi için. Asla fırlatmaz."""
    global _yazim_hatasi_kancasi
    _yazim_hatasi_kancasi = fn


def yazim_durumu(yol_dahil: bool = False) -> dict:
    """Y59: mandal dosyası yazılamıyorsa operatör metni + yeniden başlatmadaki sonuç. Yol yalnız `yol_dahil` ile (ACİL
    DURDUR ucu auth-muaf — yanıtında dosya yolu olmaz; kimlikli bildirim ve Sıfırla yanıtı yolu verir)."""
    yol = _kalici_yol
    if yol is None or not _yazim["yazilamadi"]:
        return {"yazilamadi": False}
    with _kilit:
        hedef = bool(_durum["aktif"])
    disk = bool(_yazim["disk_kurulu"])
    if disk and not hedef:
        sonuc = "geri gelecek"
    elif hedef and not disk:
        sonuc = "KORUNMAYACAK"
    elif hedef:
        sonuc = "kurulu gelecek (dosya güncellenemedi)"
    else:
        sonuc = "gelmeyecek (dosya güncellenemedi)"
    yer = f" ({yol})" if yol_dahil else ""
    return {
        "yazilamadi": True,
        "yenidenBaslatmada": sonuc,
        "mesaj": f"Mandal dosyası yazılamadı{yer} — yeniden başlatmada mandal {sonuc}; dosya iznini düzeltin.",
    }


def _yazim_yoklamasi(yol: Path) -> str:
    """Açılışta, HİÇBİR ŞEY YAZMADAN: dosya değiştirilemez görünüyor mu ("" = engel görülmedi). ACL reddi burada
    görülmez — ilk yazım denemesinde ortaya çıkar."""
    try:
        if yol.is_dir():
            return "dosyanın yerinde dizin var"
        if yol.exists() and not os.access(yol, os.W_OK):
            return "dosya salt-okunur"
    except OSError:
        return "dosya denetlenemedi"
    return ""


def kalicilik_kur(yol) -> dict:
    """Açılışta BİR KEZ: mandal dosyasının yolunu bağla ve diskteki mandalı yükle. @return `durum()`.

    Dosya kuruluysa ya da okunamıyorsa mandal KURULU başlar (bkz. modül başlığı); yoksa dokunulmaz."""
    global _kalici_yol, _nesil
    yol = Path(yol)
    _kalici_yol = yol
    kurulu, onceki_neden = False, ""
    if yol.exists():
        try:
            veri = json.loads(yol.read_text(encoding="utf-8"))
            kurulu = bool(veri.get("aktif"))
            onceki_neden = str(veri.get("neden") or "")
            if onceki_neden.startswith(ONCEKI_OTURUM_NEDENI + ":"):  # birden çok yeniden başlatma: iç neden korunur
                onceki_neden = onceki_neden.split(":", 1)[1]
            onceki_neden = onceki_neden[:60]
        except Exception:
            _log.error(
                "ACIL DURDUR mandal dosyasi okunamadi (%s) -> mandal KURULU kabul edildi (guvenli taraf)",
                yol,
                exc_info=True,
            )
            kurulu, onceki_neden = True, "dosya_okunamadi"
    _yazim.update(yazilamadi=False, neden="", disk_kurulu=kurulu)
    _engel = _yazim_yoklamasi(yol)
    if _engel:
        _yazim.update(yazilamadi=True, neden=_engel)
        _log.error("ACIL DURDUR mandal dosyasi YAZILAMAZ gorunuyor (%s): %s", yol, _engel)
    if kurulu:
        with _kilit:
            _durum["aktif"] = True
            _durum["neden"] = f"{ONCEKI_OTURUM_NEDENI}:{onceki_neden}"[:80]
            _durum["zaman"] = time.time()
            _durum["onceki_oturum"] = True
            _nesil += 1
        _log.warning("ACIL DURDUR mandali onceki oturumdan KURULU (sifirlanmadi): %s", onceki_neden)
    return durum()


def kalicilik_kapat() -> None:
    """Kalıcılığı çöz (testler arası yalıtım). Bellekteki durum değişmez."""
    global _kalici_yol
    _kalici_yol = None
    _yazim.update(yazilamadi=False, neden="", disk_kurulu=False)


def diske_yaz() -> bool:
    """Y59: Sıfırla'nın EŞZAMANLI yazımı (sonucu yanıtta söylenir). ACİL DURDUR bunu KULLANMAZ (arka planda yazar)."""
    return _diske_yaz()


def _diske_yaz() -> bool:
    """Güncel durumu (YAZIM ANINDA okunur) atomik yaz: geçici dosya + `os.replace`. Asla fırlatmaz."""
    yol = _kalici_yol
    if yol is None:
        return False
    try:
        with _yazim_kilidi:
            with _kilit:
                veri = {
                    "aktif": bool(_durum["aktif"]),
                    "neden": _durum["neden"],
                    "zaman": _durum["zaman"],
                    "nesil": _nesil,
                }
            yol.parent.mkdir(parents=True, exist_ok=True)
            gecici = yol.with_name(yol.name + ".tmp")
            gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
            os.replace(gecici, yol)
            _yazim.update(yazilamadi=False, neden="", disk_kurulu=bool(veri["aktif"]))
        return True
    except Exception as exc:
        _log.error(
            "ACIL DURDUR mandali diske YAZILAMADI (%s) — mandal bellekte kurulu; durdurma etkilenmedi",
            yol,
            exc_info=True,
        )
        _yazim.update(yazilamadi=True, neden=type(exc).__name__)
        _kanca = _yazim_hatasi_kancasi
        if _kanca is not None:
            try:
                _kanca(yazim_durumu(yol_dahil=True))
            except Exception:
                _log.warning("mandal yazim hatasi bildirimi yapilamadi", exc_info=True)
        return False


def diske_yaz_arka_planda() -> None:
    """STOP'lar gönderildikten SONRA çağrılır: yazım ayrı bir iş parçacığında — ACİL DURDUR'u ve yanıtını bekletmez.
    İş parçacığı açılamazsa satır içi denenir (yine fırlatmaz)."""
    if _kalici_yol is None:
        return
    try:
        threading.Thread(target=_diske_yaz, name="estop-mandal-disk", daemon=True).start()
    except Exception:
        _diske_yaz()


def baslatma_engeli(niyet_nesli=None) -> str:
    """START'ı engelleyen durum; "" = engel yok. `niyet_nesli` verilmişse ve bayatsa reddedilir.

    ⚠️ YALNIZ START için çağrılır. STOP yolları bunu ÇAĞIRMAZ (Ö.4-Y8)."""
    with _kilit:
        if _durum["kapanis"]:
            return KAPANIS_MESAJI
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


def niyet_nesli() -> int:
    """Bir START niyetinin nesli: bağlamdaki nesil (HTTP isteklerinde isteğin VARIŞ anında damgalanır —
    `api_server._SurusNiyetiVarisDamgasi`), bağlam yoksa şimdiki nesil."""
    n = _baglam.get()
    return nesil() if n is None else n


# ── HEDEF-KAYBI NESLİ (1-C inceleme i7-F-1) ─────────────────────────────────────────────────────────────────────────
# ÖLÇÜLDÜ (i7 Kol A 30/30, gerçek döngüyle Kol C 30/30, doğal zamanlamada ~%16): AI Pro'da hedef kaybı STOP'u sürüş
# yetkisini BİLEREK kesmez (sahip: hedef yeniden bulununca sürüş sürer) → bulunmuş ama TAHMİNDE bekleyen (uçuştaki) bir
# kare, kayıp STOP'undan SONRA geçerli nesille sürüyor ve bobini yeniden enerjiliyordu; STOP yalnız N. kayıpta gittiği
# için hedef kayıp kaldıkça bir daha STOP gelmiyordu — bobinler seans son tarihine dek enerjili.
# Her kayıp STOP'u bu nesli artırır; "bulundu" gözlemi LOKALİZASYON BAŞINDA damgalanır ve sürüş, damga ≠ güncel ise
# `HardwareController`da DURUM KİLİDİ ALTINDA reddedilir (sürüş nesliyle aynı kritik bölge — denetle-sonra-yap yok).
# Mandala ve sürüş nesline DOKUNMAZ: yeni (kayıptan sonraki) gözlem sürer. Bağlam yoksa (AI Pro dışı) denetim yok.


def kayip_nesli() -> int:
    """Şu anki hedef-kaybı nesli ("bulundu" gözlemi lokalizasyon başında bunu alır)."""
    with _kilit:
        return _kayip_nesli


def kayip_nesli_artir() -> int:
    """Hedef-kaybı STOP'u: uçuştaki "bulundu" gözlemlerini geçersiz kıl. STOP'tan ÖNCE çağrılır; mandala ve sürüş
    nesline dokunmaz; STOP'u kapılamaz (Ö.4-Y8)."""
    global _kayip_nesli
    with _kilit:
        _kayip_nesli += 1
        return _kayip_nesli


@contextlib.contextmanager
def gozlem_baglami(kayip_damgasi):
    """Blok içindeki (ve `asyncio.to_thread` ile açılan) sürüş çağrıları bu hedef gözleminin kayıp damgasını taşır."""
    jeton = _kayip_baglam.set(kayip_damgasi)
    try:
        yield
    finally:
        _kayip_baglam.reset(jeton)


def gozlem_engeli(kayip_damgasi=None) -> str:
    """Hedef gözlemi bir kayıp STOP'undan ESKİYSE engel; "" = engel yok. Damga verilmezse bağlamdaki; ikisi de yoksa
    denetim yok (AI Pro dışı sürüşler). ⚠️ YALNIZ START için çağrılır. STOP yolları bunu ÇAĞIRMAZ (Ö.4-Y8)."""
    d = _kayip_baglam.get() if kayip_damgasi is None else kayip_damgasi
    if d is None:
        return ""
    with _kilit:
        return "" if d == _kayip_nesli else KAYIP_MESAJI
