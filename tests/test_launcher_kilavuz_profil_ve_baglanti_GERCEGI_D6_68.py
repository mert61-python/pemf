# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.68 (B-7.24 · B-7.25 · Y37) — başlatıcı kılavuzu profil içeriğini ve cihaz bağlantısını KODUN bugünkü hâliyle söyler.

Kusur 1 (B-7.24): kılavuz "Veteriner profili Ev Sahibi teşhis modellerini de içerir (bu yüzden boyutu daha büyüktür)" diyordu; profiller
arası bağ 2026-08-10'da kaldırıldı (`index.html` `PROFILE_DEPS = { home: [], vet: [], research: [] }`) ve manifestte vet paketi home'dan
KÜÇÜK (152 MB < 333 MB). Yalnız Veteriner'i seçen hekim teşhis modellerinin kurulduğunu sanıyordu.

Kusur 2 (B-7.25): kılavuz "PEMF donanımı bilgisayarınızla AYNI Wi-Fi ağında olmalıdır … cihazın IP adresini elle girin" diyordu; varsayılan
kurulumda bobinler USB / STM32 kartından sürülür (`live_state.STM_COIL_IDS`), ESP kapalıdır (`PEMF_ESP_ENABLED` varsayılanı "0"). Y37:
metin HEAD'i esas alır; ESP'li karma kip AYRI notla anılır — kapı iki kipi de ölçer: Wi-Fi cümlesi YALNIZ ESP koşuluyla ve ESP bobin
numarasıyla (`live_state.ESP_COIL_IDS`) durur, USB cümlesi STM bobin aralığını söyler.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from i18n_yardimci import launcher_ui as ui

KOK = Path(__file__).resolve().parent.parent
UI = KOK / "launcher" / "app" / "ui" / "index.html"
MANIFEST = KOK / "pemf-app-packages" / "manifest.json"
LIVE_STATE = KOK / "apps" / "backend" / "servers" / "live_state.py"

ICERIR = {"tr": r"(?i)\biçerir\b|\bkapsar\b|\bdahil", "en": r"(?i)\binclud(?:es|ing)\b|\bcontains?\b"}
BUYUK = {"tr": r"(?i)daha büyük", "en": r"(?i)\blarger\b|\bbigger\b"}
WIFI = r"(?i)wi-?fi|aynı ağ|ağdaki|same network|on your network"
BOBIN = {"tr": "bobin", "en": "coil"}
ESP_KOSUL = {"tr": r"ESP etkin", "en": r"(?i)ESP enabled"}


def _cumleler(metin: str) -> list[str]:
    return [c for c in re.split(r"(?<=[.!?;])\s+", metin) if c.strip()]


def _profil_bagimliliklari() -> dict[str, list[str]]:
    m = re.search(r"const PROFILE_DEPS = (\{[^;]*\});", UI.read_text(encoding="utf-8"))
    assert m, "index.html'de PROFILE_DEPS bulunamadı — profiller arası bağ ölçülemez"
    return json.loads(re.sub(r"(\w+)\s*:", r'"\1":', m.group(1)).replace("'", '"'))


def _aralik(ids) -> str:
    s = sorted(int(i) for i in ids)
    assert s, "bobin kümesi BOŞ"
    if len(s) == 1:
        return str(s[0])
    return f"{s[0]}-{s[-1]}" if s == list(range(s[0], s[-1] + 1)) else ", ".join(map(str, s))


def _esp_varsayilan_acik() -> bool:
    m = re.search(
        r'os\.environ\.get\(\s*"PEMF_ESP_ENABLED"\s*,\s*"([01])"\s*\)\s*==\s*"1"',
        LIVE_STATE.read_text(encoding="utf-8"),
    )
    assert m, "live_state.esp_etkin() varsayılanı bulunamadı"
    return m.group(1) == "1"


def test_KRITIK_kilavuz_profil_BASKA_profilin_modellerini_icerir_DEMEZ_bag_yoksa_D6_68():
    bag = _profil_bagimliliklari()
    boyut = {k: v["size"] for k, v in json.loads(MANIFEST.read_text(encoding="utf-8"))["profiles"].items()}
    kotu = []
    for dil in ("tr", "en"):
        u = ui(dil)
        adlar = {k: v["ad"] for k, v in u["profilMeta"].items()}
        for p in u["kilavuz"]["profiles"].values():
            x = p["key"]
            for cumle in _cumleler(" ".join([p["does"], *p["use"].values()])):
                for y, ad in adlar.items():
                    if y == x or ad not in cumle:
                        continue
                    if re.search(ICERIR[dil], cumle) and y not in bag.get(x, []):
                        kotu.append(
                            f"[{dil}] {x}: '{ad}' modellerini İÇERDİĞİNİ söylüyor ama PROFILE_DEPS[{x}]={bag.get(x)}: {cumle!r}"
                        )
                    if re.search(BUYUK[dil], cumle) and not boyut[x] > boyut[y]:
                        kotu.append(
                            f"[{dil}] {x}: '{ad}'dan BÜYÜK diyor ama manifest {x}={boyut[x]} ≤ {y}={boyut[y]}: {cumle!r}"
                        )
    assert not kotu, "kılavuz profil içeriği / boyutu kodla çelişiyor:\n" + "\n".join(kotu)


def test_KRITIK_cihaz_baglantisi_metni_KIPE_gore_dogru_USB_ve_ESP_notu_D6_68():
    from servers import live_state

    stm, esp = _aralik(live_state.STM_COIL_IDS), _aralik(live_state.ESP_COIL_IDS)
    esp_acik = _esp_varsayilan_acik()
    kotu = []
    for dil in ("tr", "en"):
        u = ui(dil)
        baglanti = u["kilavuz"]["connect"]
        b = BOBIN[dil]
        if not re.search(rf"\b{b}s? {re.escape(stm)}\b", baglanti) or "USB" not in baglanti:
            kotu.append(
                f"[{dil}] kilavuz.connect STM bobinlerinin ({b} {stm}) USB ile bağlandığını söylemiyor: {baglanti!r}"
            )
        wifi = [c for c in _cumleler(baglanti) if re.search(WIFI, c)]
        if not wifi:
            kotu.append(f"[{dil}] kilavuz.connect ESP'li karma kip notu YOK (Y37: ayrı notla anılır): {baglanti!r}")
        for c in wifi:
            if not re.search(rf"\b{b}s? {re.escape(esp)}\b", c) or "ESP" not in c:
                kotu.append(f"[{dil}] Wi-Fi cümlesi ESP bobinini ({b} {esp}) ve ESP'yi anmıyor: {c!r}")
            if not esp_acik and not re.search(ESP_KOSUL[dil], c):
                kotu.append(f"[{dil}] ESP varsayılanı KAPALI ama Wi-Fi şartı koşulsuz: {c!r}")
        for anahtar in ("aboutBody", "aboutTitle"):
            for c in _cumleler(u.get(anahtar, "")):
                if re.search(WIFI, c) and not (esp_acik or re.search(ESP_KOSUL[dil], c)):
                    kotu.append(f"[{dil}] {anahtar} cihaza AĞ üzerinden bağlandığını koşulsuz söylüyor: {c!r}")
    assert not kotu, "cihaz bağlantı metni kodla çelişiyor:\n" + "\n".join(kotu)


def test_KARSIT_D6_68_kapinin_olcum_kaynaklari_GERCEK():
    """Aparat kendi kendine yeşil olmasın: bağlar bugün BOŞ, manifestte vet < home, ESP varsayılanı KAPALI, STM 1-7 / ESP 8."""
    from servers import live_state

    assert _profil_bagimliliklari() == {"home": [], "vet": [], "research": []}
    boyut = {k: v["size"] for k, v in json.loads(MANIFEST.read_text(encoding="utf-8"))["profiles"].items()}
    assert boyut["vet"] < boyut["home"], boyut
    assert _esp_varsayilan_acik() is False
    assert (_aralik(live_state.STM_COIL_IDS), _aralik(live_state.ESP_COIL_IDS)) == ("1-7", "8")
