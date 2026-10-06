# -*- coding: utf-8 -*-
"""CLIENT ↔ FIRMWARE SÜRÜM UYUMU — hangi ikili birlikte çalışır, uyumsuzsa NE YAPILIR.

SAHİP KARARI (2026-09-22): *"sürüm koruması da gerekiyor donanım ve client arasında;
ikisinin aynı anda uyumlu çalıştığı sürümleri kullanmalı. client güncellenip stm
güncellenmezse uyumsuzluğu korumak için client geri eski sürümüne otomatik dönebilmeli,
aynısı tam tersi için de geçerli."*

Bu modül **yalnız KARAR verir**; indirme/yakma/kurma yapmaz. Sebebi: karar mantığı
donanımsız, ağsız, tek başına sınanabilsin. Yan etkiler `firmware_manager` ve
`scripts/stm_yak.py` tarafında.

═══════════════════════════════════════════════════════════════════════════════
ÜÇ DURUMLU KARAR — bu depoda ZORUNLU kalıp
═══════════════════════════════════════════════════════════════════════════════
`True` uyumlu · `False` KESİN uyumsuz · `None` **bilinmiyor**.

⚠️ `None` bir eylem sebebi DEĞİLDİR. Sürüm ayrıştırılamıyorsa, kural listesi boşsa ya da
firmware banner'ı tanınmadıysa **hiçbir şey yapılmaz**. Gerekçe bu depoda iki kez ölçüldü:
  · `utils/stm32_kimlik.uyum_denetle`: banner tanınmazsa seans ENGELLENMEZ — banner biçimi
    ileride değişip UYUMLU bir firmware de tanınmayabilir; çalışan kliniği durdurmak
    çözdüğümüz sorundan büyük zarardır.
  · `update_manager._is_newer`: sürüm ayrıştırılamazsa güncelleme ÖNERİLMEZ (sonsuz-reinstall).

⚠️ **ACİL DURDURMA ASLA KAPILANMAZ.** Bu modülün çıktısı seansı/E-stop'u engellemek için
KULLANILMAZ; yalnız güncelleme planı üretir. (Kayıtlı ilke: *"bir tıbbi cihazın uzaktan
ACİL DURDURMASINI sürüm eşleşmesine bağlamak kabul edilemez"* — `SurumFarkiBanner`.)

═══════════════════════════════════════════════════════════════════════════════
KURAL BİÇİMİ (manifest'ten gelir)
═══════════════════════════════════════════════════════════════════════════════
    "uyumluluk": [
      {"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.3", "firmwareMax": ""},
      ...
    ]

Boş/eksik sınır = **sınırsız o yönde**. Bir çift, kurallardan EN AZ BİRİNE uyuyorsa uyumludur.
⚠️ Liste boşsa karar `None`'dır — "kural yok" **"her şey uyumlu" DEMEK DEĞİLDİR**. Aksi hâlde
bozuk/eksik bir manifest sessizce "hepsi uyumlu" der ve koruma kendiliğinden kalkardı.
"""

from __future__ import annotations

from dataclasses import dataclass


def surum_demeti(s: str) -> tuple[int, ...] | None:
    """'v2.3.1-rc' → (2,3,1). Hiçbir sayısal parça yoksa None ('bilinmiyor').

    ⚠️ `update_manager._vtuple` ile AYNI semantik (etiketli sürümlerin sayısal ön-eki
    alınır). Orası backend'in güncelleme yolunda, burası uyum kararında; ikisinin aynı
    şeyi görmesi ŞART. Kapı: `tests/test_surum_uyumu.py::test_semantik_update_manager_ILE_AYNI`
    """
    parcalar = str(s).strip().lstrip("vV").split(".")
    sayilar: list[int] = []
    for p in parcalar[:3]:
        rakam = ""
        for ch in p:
            if ch.isdigit():
                rakam += ch
            else:
                break
        if rakam == "":
            break
        sayilar.append(int(rakam))
    return tuple(sayilar) if sayilar else None


def _karsilastir(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _aralikta(surum: str, alt: str, ust: str) -> bool | None:
    """alt ≤ surum ≤ ust. Boş sınır = sınırsız. Ayrıştırılamayan → None."""
    s = surum_demeti(surum)
    if s is None:
        return None
    if alt:
        a = surum_demeti(alt)
        if a is None or _karsilastir(s, a) < 0:
            return False if a is not None else None
    if ust:
        u = surum_demeti(ust)
        if u is None or _karsilastir(s, u) > 0:
            return False if u is not None else None
    return True


def uyumlu_mu(client: str, firmware: str, kurallar: list[dict]) -> tuple[bool | None, str]:
    """(uyumlu, gerekçe). ⚠️ Kural listesi boşsa `None` — "kural yok" ≠ "uyumlu"."""
    if not kurallar:
        return None, "uyumluluk kuralı YOK (manifest eksik) — karar verilmiyor"
    if surum_demeti(client) is None:
        return None, f"client sürümü ayrıştırılamadı: {client!r}"
    if surum_demeti(firmware) is None:
        return None, f"firmware sürümü ayrıştırılamadı: {firmware!r}"

    belirsiz = False
    for k in kurallar:
        c = _aralikta(client, str(k.get("clientMin", "")), str(k.get("clientMax", "")))
        f = _aralikta(firmware, str(k.get("firmwareMin", "")), str(k.get("firmwareMax", "")))
        if c is None or f is None:
            belirsiz = True
            continue
        if c and f:
            return True, f"client {client} ↔ firmware {firmware} kuralla eşleşti"
    if belirsiz:
        return None, "kurallarda ayrıştırılamayan sınır var — karar verilmiyor"
    return False, (
        f"client {client} ile firmware {firmware} birlikte çalışmıyor ({len(kurallar)} kuralın hiçbirine uymuyor)"
    )


# ══════════════════════════════════════════════════════════════════════════════
# PLAN — uyumsuzsa NE YAPILACAK
# ══════════════════════════════════════════════════════════════════════════════
#: Eylem adları — çağıran taraf bunlara göre dallanır. Dize sabitleri TEK YERDE.
EYLEM_YOK = "yok"
FIRMWARE_GUNCELLE = "firmware_guncelle"
CLIENT_GERI_AL = "client_geri_al"
BEKLE = "bekle"


@dataclass(frozen=True)
class Plan:
    eylem: str
    hedef_surum: str
    gerekce: str


def plan_yap(
    client: str,
    firmware: str,
    kurallar: list[dict],
    *,
    yeni_firmware: str = "",
    onceki_client: str = "",
    internet: bool = True,
    stm_bagli: bool = True,
) -> Plan:
    """Uyumsuzluğu gidermenin EN AZ RİSKLİ yolunu seç.

    SIRA — ölçülebilir gerekçelerle:
      1. Zaten uyumluysa → hiçbir şey. (En sık durum; gereksiz yakma RİSKTİR.)
      2. Karar `None` → hiçbir şey. Bilinmeyene dayanarak firmware yakılmaz.
      3. STM bağlı değil ya da internet yok → **BEKLE**. Sessizce geçilmez; durum
         `/api/health`te görünür (fail-quiet ≠ fail-silent: kullanıcıyı rahatsız etmeyiz
         ama destek mühendisi ayırt edebilsin).
      4. İLERİ GİT: yeni firmware client'la uyumluysa **firmware'i güncelle**. İleri gitmek
         geri almaya tercih edilir — kullanıcı zaten yeni client'ı istemiştir.
      5. İleri gidilemiyorsa **client'ı geri al** (sahip: *"client güncellenip stm
         güncellenmezse client geri eski sürümüne otomatik dönebilmeli"*).
         ⚠️ Y16 (D1.119): geri almayı LAUNCHER yapar — backend (`firmware_manager.acilis_denetimi`)
         `onceki_client` VERMEZ, bu adım backend'de hiç üretilmez; backend `istemciGeriAlinmali`
         sinyalini yayınlar (docs/LAUNCHER_SPEC.md). Saf karar olarak (launcher/test için) kalır.
      6. Geri alınacak sürüm de yoksa → BEKLE. ⚠️ Hiçbir durumda "uyumsuz haliyle devam et"
         diye bir eylem ÜRETİLMEZ; ama bu modül seansı da ENGELLEMEZ — o kararı
         `utils/stm32_kimlik.uyum_denetle` verir ve E-stop her hâlükârda açıktır.
    """
    uyum, gerekce = uyumlu_mu(client, firmware, kurallar)
    if uyum is True:
        return Plan(EYLEM_YOK, "", gerekce)
    if uyum is None:
        return Plan(EYLEM_YOK, "", f"karar verilemedi → dokunulmuyor ({gerekce})")

    if not stm_bagli:
        return Plan(BEKLE, "", "STM bağlı değil — firmware güncellenemez, karar erteleniyor")
    if not internet:
        return Plan(BEKLE, "", "internet yok — firmware indirilemez, karar erteleniyor")

    if yeni_firmware:
        ileri, _ = uyumlu_mu(client, yeni_firmware, kurallar)
        if ileri is True:
            return Plan(
                FIRMWARE_GUNCELLE,
                yeni_firmware,
                f"firmware {firmware} → {yeni_firmware} ile client {client} uyumlu olacak",
            )

    if onceki_client:
        geri, _ = uyumlu_mu(onceki_client, firmware, kurallar)
        if geri is True:
            return Plan(
                CLIENT_GERI_AL,
                onceki_client,
                f"ileri gidilemedi; client {client} → {onceki_client} ile mevcut firmware {firmware} uyumlu olacak",
            )

    return Plan(
        BEKLE,
        "",
        f"uyumsuz ({gerekce}) ama ne ileri ne geri uyumlu bir sürüm var — elle müdahale gerekir",
    )
