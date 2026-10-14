# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""STM32 FIRMWARE KIMLIGI — banner ayristirma + UYUM DENETIMI (2026-09-18).

⚠️ COZDUGU ARIZA (olculdu, `docs/stm32-uzaktan-guncelleme-plani.md` §1):
Kart acilista KIM OLDUGUNU zaten soyluyor:

    -> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) Waiting for commands...

Backend ise `headless_core.py` icinde yalnizca su kontrolu yapiyordu:

    if "STM_READY" in decoded or "STM_OK:" in decoded:
        self._set_stm_connected(True)          # ⚠️ ICERIGE HIC BAKMIYOR

Sonucu SESSIZ bir ariza sinifi: eski firmware (5 bobin) 88 baytlik paket bekler, backend 120
bayt gonderir → eski firmware ilk 88 bayti paket sanar, CRC'yi YANLIS OFSETTEN okur,
`Coil_SendNack("CRC")` doner ve **PWM durumuna hic dokunmaz**. Ama `STM_READY` basildigi icin
uygulama STM'i **BAGLI** gosterir.

    Belirti: baglanti gostergesi YESIL, hata penceresi YOK, hicbir bobin baslamiyor
             (bobin 1-5 dahil). Bugun bunu ayirt etmenin tek yolu UART'i ELLE dinlemek.

Bu modul banner'i ayristirir ve kartin soyledigi kanal sayisini VE banner revizyonundan cikan
PAKET BOYUNU backend'in PAKETLEDIGI genislik/boyla (`utils.stm32_transport.STM_PAKET_BOBIN_SAYISI`,
`STM_PAKET_BOYU`) karsilastirir (D1.103 · B-1.20: yalniz kanal sayisina bakmak 7 kanalli ama 120 baytlik
firmware'i "uyumlu" sayiyordu — o firmware her paketi NACK'ler).

⚠️ TEK KAYNAK: desen eskiden `scripts/stm_firmware_kimligi.py` icindeydi. KOPYALANMADI —
o betik artik BURADAN import eder. (Bu depoda ayni deseni iki yere yazmanin bedeli olculdu:
`_DB_ERROR` demetleri iki DB modulunde sessizce AYRISMISTI.)

⚠️ GUVENLIK DEGISMEZI: bu modul bir KARAR uretir, bir KILIT degildir. Uyumsuzluk seans
baslatmayi reddeder ama ACIL DURDURMAYI **ASLA** engellemez — depo kurali: bobinler her
seyden once durur (bkz. bellek `pemf-device-safety-shutdown`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Firmware'in bastigi kip sozlugu (`firmware/stm32_pemf/Core/Src/main.c:1012`).
#: ⚠️ Kip dizesi MASKEDEN turer; elle yazilan etiket 2026-09-11 karma yapilandirmasinda
#: YALAN soylerdi. Buraya yeni bir kip eklenirse firmware'deki uclu ile birlikte guncellenir.
KIPLER = ("SYM-BIPOLAR", "UNIPOLAR tek-bacak", "KARMA")

#: `-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) ...`
#: ⚠️ `surum` tembel (`.+?`) ve parantez ONCESINDE biter; kip sozlukten secilir ki
#: "UNIPOLAR tek-bacak" gibi BOSLUKLU etiket ikiye bolunmesin.
#: ⚠️ D1.103 (B-1.20): kip ARTIK yalniz `+`/`)`'dan ONCE eksik olabilir — gercek v2.2 banner'i kipsizdi
#: (`DDS v2.2 (5-ch + HW_SYNC@PB1)`, a0487c3) ve "bilinmiyor"a dusuyordu. TANINMAYAN bir kip kelimesi (gelecekte
#: yeni bir kip) yine eslesmez → "bilinmiyor" (seans ENGELLENMEZ); kipsiz-sayip "eski firmware" diye REDDETMEZ.
BANNER_DESENI = re.compile(
    r"STM_READY:\s*(?P<surum>.+?)\s*\(\s*(?P<kanal>\d+)-ch"
    r"(?:\s+(?P<kip>" + "|".join(re.escape(k) for k in KIPLER) + r")"
    r"(?:\s+uni=0x(?P<maske>[0-9A-Fa-f]+))?"
    r"|(?=\s*[+)]))"
)


#: Y68 (TD1): banner / kimlik yanıtında parantezden SONRA gelen protokol alanları (`proto=3 pkt=121`). Noktasız tam sayı →
#: `firmware_surumu`nun ilk noktalı sayı kuralını bozmaz (O-1.3).
_PROTO_DESENI = re.compile(r"(?<![\w=])proto=(\d+)\b")
_PKT_DESENI = re.compile(r"(?<![\w=])pkt=(\d+)\b")


@dataclass(frozen=True)
class Stm32Kimlik:
    """Kartin banner'da BEYAN ETTIGI kimlik. `maske` yoksa None (eski banner); `kip` yoksa None (v2.2 banner'i).

    Y68 (TD1): `protokol` / `paket_boyu` yalniz kart BASIYORSA dolu (proto=… pkt=…; 2026-10-14 sonrasi firmware); eski
    banner'da None. `kaynak`: "banner" (STM_READY) ya da "sorgu" (kimlik sorgusunun yaniti, STM_ID)."""

    surum: str
    kanal: int
    kip: str | None
    maske: int | None
    ham: str
    protokol: int | None = None
    paket_boyu: int | None = None
    kaynak: str = "banner"


def firmware_paket_boyu(kimlik: Stm32Kimlik) -> int:
    """Banner REVIZYONUNDAN kartin bekledigi paket boyu (bayt; CRC dahil) — D1.103 · B-1.20.

    Git gecmisinden OLCULDU (`tests/test_D1103_firmware_UYUM_karari_REVIZYON_tablosu.py`, iki CubeIDE projesi):
      * 07c2d4c'den (2026-09-10 20:59) once: 5 kanal, kip bayti yok → 16·5 + 8 = 88
      * 07c2d4c … 8aace69 (09-10 20:59 … 09-11 03:04): 7 kanal, kip bayti YOK, banner'da `uni=` YOK → 120
      * e2b63a5 … a280fa4 (09-11 13:53 … 15:21): 7 kanal, kip bayti YOK ama banner `uni=` BASAR → 120.
        ⚠️ Banner'i f367f85+ (121 bayt) ile BAYT BAYT AYNI → banner'dan AYIRT EDILEMEZ (bilinen sinir: ayrim icin
        firmware banner'ina protokol revizyonu eklenip kart yeniden yakilmali — Oturum 13 / sahip Y1-Y2). Burada
        121 sayilir; o kartta tepkisel kapi (sistematik NACK → seans durur, B-1.1) devrededir.
      * f367f85 (09-11 17:38) → HEAD: kip bayti (`unipolar_maskesi`) VAR → 16·7 + 9 = 121
    Kural: duty/faz/frekans float + sure uint32 (bobin basina 16) + baslik 2 + ref_ms 2 + CRC 4; `uni=` alani
    (maske) VARSA sürüş kipi bayti var sayilir.

    ⚠️ Y68 (TD1): kart paket boyunu BEYAN ediyorsa (`pkt=`) beyan esastir — tahmin yapilmaz."""
    if kimlik.paket_boyu is not None:
        return int(kimlik.paket_boyu)
    return 16 * kimlik.kanal + 8 + (1 if kimlik.maske is not None else 0)


def banner_ayristir(satir: str) -> Stm32Kimlik | None:
    """`STM_READY` satirindan kimligi cikar; taninmazsa None. Y68: parantezden sonraki `proto=` / `pkt=` alanlari okunur."""
    if not satir:
        return None
    m = BANNER_DESENI.search(satir)
    if not m:
        return None
    ham_maske = m.group("maske")
    kalan = satir[m.end() :]
    m_proto = _PROTO_DESENI.search(kalan)
    m_pkt = _PKT_DESENI.search(kalan)
    return Stm32Kimlik(
        surum=m.group("surum").strip(),
        kanal=int(m.group("kanal")),
        kip=m.group("kip"),
        maske=int(ham_maske, 16) if ham_maske else None,
        ham=satir.strip(),
        protokol=int(m_proto.group(1)) if m_proto else None,
        paket_boyu=int(m_pkt.group(1)) if m_pkt else None,
    )


#: Y68: kimlik sorgusunun yanıt satırı — `-> STM_ID: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121`
#: (gövde firmware'de banner'dan TÜRER: `main.c` kimlik_govde).
KIMLIK_YANIT_ONEKI = "STM_ID:"


def kimlik_yaniti_ayristir(satir: str) -> Stm32Kimlik | None:
    """Y68 (TD1): `STM_ID:` satırını kimliğe çevir (banner ayrıştırıcısıyla AYNI kurallar — tek kaynak); değilse None."""
    if not satir or KIMLIK_YANIT_ONEKI not in satir:
        return None
    k = banner_ayristir(satir.replace(KIMLIK_YANIT_ONEKI, "STM_READY:", 1))
    if k is None:
        return None
    return Stm32Kimlik(
        surum=k.surum,
        kanal=k.kanal,
        kip=k.kip,
        maske=k.maske,
        ham=satir.strip(),
        protokol=k.protokol,
        paket_boyu=k.paket_boyu,
        kaynak="sorgu",
    )


# ── PAKET KABUL / RED KANITI (TD1, tezgâh 2026-10-14) ───────────────────────────────────────────────────────────────
# ⚠️ ÖLÇÜLDÜ: 120 baytlık saha imajı ile 121 baytlık imaj AYNI banner'ı basar; banner tek başına paket boyunu SÖYLEYEMEZ.
# Kartın paketimize verdiği YANIT söyler: 120 baytlık firmware 121 baytlık paketin CRC'sini YANLIŞ ofsetten okur → HER
# paket `STM_NACK: CRC` (2^-32 dışında); 121 baytlık firmware `STM_OK` (ya da CRC'yi geçmiş paketin içeriğine `RANGE` NACK'i)
# döner. Yani: STM_OK / RANGE NACK = paket boyu UYUMLU KANITI · ARADA KABUL OLMADAN ard arda ≥ eşik CRC NACK = UYUMSUZ kanıtı.
# Tek NACK hat gürültüsü olabilir → eşik. Kabul görülmüş bağlantıda sonraki CRC NACK'ler (gürültü) kararı ÇEVİRMEZ.
#: Arada kabul olmadan bu kadar CRC NACK → paket boyu uyumsuz (tepkisel kapının `STM_RED_ESIGI` ile aynı sayı, ayrı kavram).
PAKET_RED_CRC_ESIGI = 3
KANIT_KABUL = "kabul"
KANIT_RED = "red"


def paket_yaniti_siniflandir(satir: str) -> str | None:
    """Kart satırı paket boyu hakkında ne söylüyor? `KANIT_KABUL` (STM_OK · RANGE NACK) · "crc" (CRC NACK) · None (ilgisiz)."""
    s = str(satir or "")
    if "STM_OK:" in s:
        return KANIT_KABUL
    if "STM_NACK" in s:
        govde = s.split("STM_NACK", 1)[1].upper()
        if "CRC" in govde:
            return "crc"
        if "RANGE" in govde:  # CRC'yi GEÇMİŞ paketin içerik reddi → kart paketi doğru boyla çerçeveledi
            return KANIT_KABUL
    return None


# ── OPERATÖR METİNLERİ (K1 / K2 — tezgâh "Kullanıcı geri bildirimi", sahip: "o bir veteriner, yazılımcı değil") ─────
#: Kod → arayüz bandı / 409 metni. Teknik ayrıntı (`uyum_denetle` sebebi, python / CubeIDE talimatı) YALNIZ destek alanında.
UYUM_KODU_PAKET = "FW-PAKET"
UYUM_KODU_KIMLIK = "FW-KIMLIK"
OPERATOR_METNI = {
    UYUM_KODU_PAKET: (
        "Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz — bobinler çalışmaz. "
        "Teknik desteği arayın (kod: FW-PAKET)."
    ),
    UYUM_KODU_KIMLIK: (
        "Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH sıfırlama düğmesine bir kez basın (mavi değil)."
    ),
}


#: Kart komutları SİSTEMATİK reddederken (tepkisel kapı) operatör metni — api_server `STM_RED_MESAJI` ve HC başlatma engeli.
KOMUT_RED_METNI = (
    "Cihaz kartı komutları reddediyor — kartın yazılımı bu uygulama sürümüyle uyumsuz; bobinler çalışmaz. "
    "Teknik desteği arayın (kod: FW-PAKET)."
)


#: TD3: kart ACİL DURDUR'un STOP'una NACK döndü (kabul yok) — E-stop yanıtı `stmRedMesaji`, bildirim ve arayüz uyarısı. EYLEM
#: söyler (hafıza "Hata mesajı EYLEM"); arayüz kopyası `apps/ui/src/services/emergencyStop.ts` (eşlik testi TD3).
ESTOP_KART_RED_METNI = (
    "Cihaz kartı STOP komutunu reddetti — bobinler durmamış olabilir. Cihazın gücünü kesin ya da USB kablosunu çıkarın."
)


def operator_metni(kod: str | None) -> str:
    """Uyum kodunun operatör metni; kod yoksa ""."""
    return OPERATOR_METNI.get(str(kod or ""), "")


def uyum_karari(
    kimlik: Stm32Kimlik | None,
    kanit: str | None,
    crc: int = 0,
    *,
    okunamadi: bool = False,
    dogrulanamadi: bool = False,
    paket_kanal: int | None = None,
) -> tuple[bool | None, str, str | None]:
    """TD1 — TEK KARAR (backend çekirdeği, servis betiği, yakma akışı AYNI işlevi çağırır): (uyumlu, destek sebebi, kod).

    Öncelik: (1) RED kanıtı (arada kabul olmadan ≥ eşik CRC NACK — eski firmware'li kartta da, banner aynı olsa bile) →
    False + FW-PAKET · (2) kartın beyanı (Y68 kimlik yanıtı, yoksa banner) → `uyum_denetle`; beyan "bilinmiyor" ama KABUL
    kanıtı varsa → True · (3) kimlik yok: kabul → True; resetsiz / yanıtsız → None + FW-KIMLIK; kanıt da yoksa None (kod yok).
    ⚠️ KARAR, KİLİT DEĞİL: False yalnız seans BAŞLATMAYI reddettirir; ACİL DURDUR / STOP buna bağlı DEĞİL (Ö.4-Y8)."""
    if paket_kanal is None:
        from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI  # tembel: katman döngüsü yok

        paket_kanal = STM_PAKET_BOBIN_SAYISI
    from utils.stm32_transport import STM_PAKET_BOYU

    if kanit == KANIT_RED:
        return (
            False,
            f"Kart uygulamanin {STM_PAKET_BOYU} baytlik paketini SISTEMATIK reddediyor (arada STM_OK olmadan ard arda {crc} "
            f"STM_NACK: CRC)"
            + (f"; kartin kimligi: {kimlik.ham}" if kimlik is not None else "")
            + ". Karttaki firmware farkli paket boyu bekliyor (or. 120 baytlik eski saha imaji). HICBIR bobin calismaz. "
            "Yapilacak: kart bu surumun firmware'i ile yakilmali (docs/SAHA-ISLERI-REHBERI.md B-2; scripts/stm_yak.py — "
            "dogrulama: el sikismada STM_OK, CRC NACK yok).",
            UYUM_KODU_PAKET,
        )
    if kimlik is not None:
        uyumlu, sebep = uyum_denetle(kimlik, paket_kanal)
        if uyumlu is False:
            return False, sebep, UYUM_KODU_PAKET
        if uyumlu is None and kanit == KANIT_KABUL:
            return True, "", None  # kart paketimizi KABUL etti → paket boyu ölçüyle uyumlu
        if uyumlu is None and dogrulanamadi:
            return (
                None,
                sebep + " El sikisma dogrulamasina (kimlik sorgusu + sifir-duty yoklamasi) yanit YOK.",
                UYUM_KODU_KIMLIK,
            )
        return uyumlu, sebep, None
    if kanit == KANIT_KABUL:
        return True, "", None
    if okunamadi:
        return (
            None,
            "Kartin firmware kimligi OKUNAMADI: kart resetlenmeden baglandi (STM_READY gorulmedi; el sikisma sifir-duty "
            "yoklamasina STM_OK ile tamamlandi). Uyum DOGRULANAMADI — seans engellenmez; kart paketleri reddederse sistematik "
            "red seansi durdurur. Kimligi okutmak icin kartin RESET dugmesine basin ya da backend kapaliyken python "
            "scripts/stm_firmware_kimligi.py calistirin.",
            UYUM_KODU_KIMLIK,
        )
    if dogrulanamadi:
        return (
            None,
            "Kart el sikisma dogrulamasina yanit vermedi (kimlik sorgusu yaniti, STM_OK ya da NACK yok) — uyum DOGRULANAMADI. "
            "Kartin RESET dugmesine basin ya da backend kapaliyken python scripts/stm_firmware_kimligi.py calistirin.",
            UYUM_KODU_KIMLIK,
        )
    return None, "", None


def satirlardan_karar(
    satirlar: list[str], paket_kanal: int | None = None
) -> tuple[bool | None, str, Stm32Kimlik | None]:
    """TD1-d / TD1-e: bir dinleme / doğrulama oturumunda toplanan kart satırlarından karar (servis betiği ve yakma akışı).
    Çekirdeğin durum makinesinin tek seferlik karşılığı: son banner kimliği, Y68 kimlik yanıtı, paket kabul / red kanıtı →
    `uyum_karari`. Döner: (uyumlu, sebep, kimlik)."""
    banner_k: Stm32Kimlik | None = None
    sorgu_k: Stm32Kimlik | None = None
    kanit: str | None = None
    crc = 0
    for s in satirlar:
        if "STM_READY" in s:
            banner_k = banner_ayristir(s) or banner_k
        elif KIMLIK_YANIT_ONEKI in s:
            sorgu_k = kimlik_yaniti_ayristir(s) or sorgu_k
        sinif = paket_yaniti_siniflandir(s)
        if sinif == KANIT_KABUL:
            kanit, crc = KANIT_KABUL, 0
        elif sinif == "crc" and kanit != KANIT_KABUL:
            crc += 1
            if crc >= PAKET_RED_CRC_ESIGI:
                kanit = KANIT_RED
    kimlik = sorgu_k or banner_k
    uyumlu, sebep, _kod = uyum_karari(kimlik, kanit, crc, paket_kanal=paket_kanal)
    return uyumlu, sebep, kimlik


#: D1.120 (B-4.2): banner'in `surum` alani firmware ADINI da tasir (`DDS v2.3`, main.c banner bicimi); uyum karari
#: (`surum_uyumu.surum_demeti`) yalniz SAYIYI ayristirir. Sayi ad/ek icinde gomulu olabilir ("v2.3", "2.3-rc1").
_SURUM_SAYISI = re.compile(r"(?<![\w.])v?(\d+(?:\.\d+)+)(?![\w.])")


def firmware_surumu(surum: str | None) -> str:
    """D1.120: banner surum alanindan (`DDS v2.3`) karsilastirilabilir firmware surumu (`2.3`).

    ⚠️ Bulunamazsa "" — uyum karari "surum ayristirilamadi" der ve BEKLE'ye duser (fail-safe: bilinmeyen surume
    dayanarak YAKMA karari URETILMEZ). Eskiden ham `DDS v2.3` gecirildigi icin karar HER acilista "ayristirilamadi"ydi
    (1-H (a)0 olcumu) — oto-firmware zinciri bu yuzden olu kaliyordu; bu islev zinciri UYANDIRIR (Y1: yakma yalniz
    acik `PEMF_FW_AUTO_UPDATE=1` ile)."""
    m = _SURUM_SAYISI.search(str(surum or ""))
    return m.group(1) if m else ""


#: `uyum_denetle` sonucu: (uyumlu, sebep). `uyumlu` UC DURUMLU olabilir —
#: True = eslesti · False = KESIN uyumsuz · None = BILINMIYOR (banner taninmadi).
def uyum_denetle(
    kimlik: Stm32Kimlik | None, paket_kanal: int, paket_boyu: int | None = None
) -> tuple[bool | None, str]:
    """Kartin beyan ettigi kanal sayisi VE banner revizyonundan cikan paket boyu, BIZIM paketledigimiz genislik ve
    boyla (`paket_boyu`; verilmezse `utils.stm32_transport.STM_PAKET_BOYU`) uyusuyor mu?

    ⚠️ NEDEN "BILINMIYOR" DIYE UCUNCU BIR DURUM VAR — ve neden o seansi ENGELLEMEZ:
    Banner ayristirilamazsa iki ihtimal var: (a) gercekten eski/yabanci firmware,
    (b) ileride banner bicimi degismis AMA uyumlu bir firmware. (b)'de seansi reddetmek
    CALISAN bir klinigi durdurur. Tedaviyi durdurmak da bir zarardir; bu yuzden yalnizca
    KESIN uyumsuzlukta (banner okundu VE kanal ya da paket boyu farkli) reddediyoruz. "Bilinmiyor" hali
    log'da ve `/api/health`te GORUNUR — destek muhendisi ayirt edebilsin.

    ⚠️ D1.103 (B-1.20): eskiden YALNIZ kanal sayisi karsilastiriliyordu → 7 kanalli ama 120 baytlik (kip baytsiz)
    firmware revizyonlari "uyumlu" sayiliyordu (o kart 121 baytlik her paketi NACK'ler). Paket boyu
    `firmware_paket_boyu` ile banner revizyonundan turer.

    ⚠️ TD1 (tezgâh 2026-10-14, A1 ÖLÇÜLDÜ): sahadaki banner (`DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)`, Y7) 120
    BAYTLIK karttandir ve 121 baytlik firmware de AYNI banner'i basar → bu banner artik "bilinmiyor" (None) doner; kesin
    karar kartin beyanindan (Y68 `pkt=` / kimlik sorgusu) ya da paket kabul / red kanitindan gelir (HeadlessCore).

    ⚠️ Zaten uyumsuz firmware'de bobinler CALISMIYOR; kapinin kazandirdigi sey calisirlik
    degil, TEsHIS: "yesil ama hicbir sey olmuyor" yerine EYLEM soyleyen bir mesaj.
    """
    if kimlik is None:
        return None, (
            "Kartin firmware kimligi OKUNAMADI (STM_READY satiri taninmadi). Eski ya da "
            "yabanci bir firmware olabilir. Dogrulama: python scripts/stm_firmware_kimligi.py"
        )
    if paket_boyu is None:
        from utils.stm32_transport import STM_PAKET_BOYU  # tembel: katman dongusu yok, cagiran boyu verebilir

        paket_boyu = STM_PAKET_BOYU
    fw_boyu = firmware_paket_boyu(kimlik)
    if kimlik.kanal != paket_kanal:
        return False, (
            f"Kart {kimlik.kanal} kanalli firmware kosuyor ({kimlik.surum}), uygulama "
            f"{paket_kanal} kanalli paket gonderiyor. Paket genisligi birebir olmak ZORUNDA — "
            f"aksi halde firmware her paketi NACK'ler ve HICBIR bobin calismaz. "
            f"Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
        )
    if kimlik.paket_boyu is not None:
        # Y68 (TD1): kart paket boyunu BEYAN ETTI (banner `pkt=` ya da kimlik sorgusu) → kesin karar.
        if fw_boyu == paket_boyu:
            return True, ""
        return False, (
            f"Kart {fw_boyu} baytlik paket bekledigini bildiriyor ({kimlik.surum}, proto={kimlik.protokol}), uygulama "
            f"{paket_boyu} baytlik paket gonderiyor. Paket boyu birebir olmak ZORUNDA — aksi halde firmware her paketi "
            f"NACK'ler ve HICBIR bobin calismaz. Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
        )
    if fw_boyu != paket_boyu:
        return False, (
            f"Kart {kimlik.kanal} kanalli ama {fw_boyu} baytlik paket bekleyen ESKI bir firmware kosuyor "
            f"({kimlik.surum}; banner'da surus kipi alani 'uni=' YOK — 2026-09-10/11 surumu), uygulama {paket_boyu} "
            f"baytlik paket gonderiyor. Paket boyu birebir olmak ZORUNDA — aksi halde firmware her paketi NACK'ler ve "
            f"HICBIR bobin calismaz. Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
        )
    if kimlik.maske is not None:
        # ⚠️ TD1 (tezgâh 2026-10-14 ÖLÇTÜ, A1): `uni=` basan ama `pkt=` basmayan banner 120 baytlik (e2b63a5…a280fa4,
        # SAHA IMAJI) ve 121 baytlik (f367f85…TD1 oncesi) firmware'lerde BAYT BAYT AYNI. Eskiden 121 sayilip "uyumlu"
        # deniyordu → sahadaki 120 baytlik kart HEAD ile yesil gorunurken HER paketi NACK'liyordu. Banner'dan karar
        # VERILMEZ ("bilinmiyor" — seans engellenmez); kesin karar kartin paketimize yanitindan (paket_yaniti_siniflandir)
        # ya da kimlik sorgusundan gelir (HeadlessCore el sikisma dogrulamasi).
        return None, (
            f"Banner paket boyunu soylemiyor (120 ve 121 B ayni banner'i basar); uyum kartin {paket_boyu} B pakete "
            f"yanitiyla (STM_OK / CRC NACK) DOGRULANACAK."
        )
    return True, ""
