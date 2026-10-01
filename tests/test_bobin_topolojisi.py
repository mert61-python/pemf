# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN TOPOLOJİSİ KAPISI — hangi bobin hangi yoldan sürülüyor?

FAZ 4 (sahip kararı 2026-09-10): bobin 6-7 ESP8266'dan STM32'ye taşındı →
`STM_COIL_IDS = {1..7}`, `ESP_COIL_IDS = {8}` (slot 8 kalıyor, cihazı yok, yol uykuda).

⚠️ NEDEN KAPI: bu iki küme `/api/coil/{id}/control` ve batch yollarında YÖNLENDİRMEYİ belirler.
Bir bobin yanlış kümede olursa komut ona HİÇ ULAŞMAZ ve arayüz bunu göstermez — 2026-09-10'a
kadar bobin 6-7 tam bu durumdaydı: kablo STM'e çekilmişti, komut MQTT'ye gidiyordu.
Dahası kümeler DÖRT AYRI yerde tekrarlanıyor (`live_state`, `hardware_controller`,
`headless_core`, `stm32_transport`); biri ayrışırsa arıza sessizdir.

Sabitler `tests/topoloji.py` içinde (yardımcı modül; literal bobin numarası yazma kuralı).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))

from servers.live_state import ESP_COIL_IDS, STM_COIL_IDS  # noqa: E402

#: ESP kapsamının geçtiği üretim dosyaları (D1.40: kök düzeyindeki eski yol F4'ten beri YOK).
_ESP_KAPSAM_HEDEFLERI = (
    "apps/backend/backend_service.py",
    "apps/backend/servers/ai_router.py",
    "apps/backend/servers/api_server.py",
)


def test_KRITIK_topoloji_CAKISMIYOR_ve_BOS_DEGIL():
    """Bir bobin İKİ yoldan sürülemez; kümelerin ikisi de anlamlı kalmalı.

    ⚠️ Çakışma olursa `/api/coil/{id}/control` hem seri porta hem MQTT'ye yazar: bobin iki
    farklı parametre setiyle sürülür ve hangisinin kazandığı zamanlamaya kalır.
    """
    assert not (set(STM_COIL_IDS) & set(ESP_COIL_IDS)), (
        f"bobin AYNI ANDA iki yolda: {sorted(set(STM_COIL_IDS) & set(ESP_COIL_IDS))}"
    )
    assert STM_COIL_IDS, "STM_COIL_IDS bos — hicbir bobin seri yoldan surulemez"
    assert set(STM_COIL_IDS) == set(range(1, 8)), (
        f"STM kapsami {sorted(STM_COIL_IDS)}; faz 4 karari 1-7 (bobin 6-7 ESP'den tasindi)"
    )
    assert set(ESP_COIL_IDS) == {8}, (
        f"ESP kapsami {sorted(ESP_COIL_IDS)}; faz 4'te yalniz slot 8 kaldi (cihazi YOK, "
        "yol SILINMEDI — sahip karari 'ESP kodu uykuda kalsin')"
    )


def test_KRITIK_kapsamlar_8_SLOTU_asmaz():
    """`_live_state["coils"]` 8 slotlu; kümeler onun dışına çıkarsa IndexError üretir."""
    hepsi = set(STM_COIL_IDS) | set(ESP_COIL_IDS)
    assert hepsi == set(range(1, 9)), f"1-8 disinda/eksik bobin: {sorted(hepsi)}"


def test_KRITIK_hardware_controller_kapsami_live_state_ile_AYNI():
    """`STM_BOBIN_SAYISI` ile `STM_COIL_IDS` ayrışırsa komut sessizce reddedilir."""
    from controllers.hardware_controller import STM_BOBIN_SAYISI

    assert STM_BOBIN_SAYISI == len(STM_COIL_IDS), (
        f"hardware_controller {STM_BOBIN_SAYISI} bobin sanıyor, live_state "
        f"{len(STM_COIL_IDS)} — update_coil buyuk kimligi REDDEDER, arayuz sebebi gostermez"
    )


def test_KRITIK_ACK_kapsami_da_AYNI():
    """`STM_COIL_COUNT` küçük kalırsa bobin 6-7'nin ACK değerleri SESSİZCE atılır."""
    from headless_core import HeadlessCore

    assert HeadlessCore.STM_COIL_COUNT == len(STM_COIL_IDS), (
        f"STM_COIL_COUNT={HeadlessCore.STM_COIL_COUNT}, STM kapsami {len(STM_COIL_IDS)} — "
        "kirpma siniri kucuk kalirsa canli durum bayat kalir"
    )


def test_KRITIK_paket_genisligi_topolojiden_KUCUK_OLAMAZ():
    """Protokol daha geniş olabilir (fazla alan sıfır gider) ama DAHA DAR olamaz."""
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    assert STM_PAKET_BOBIN_SAYISI >= len(STM_COIL_IDS), (
        f"paket {STM_PAKET_BOBIN_SAYISI} bobin tasiyor ama topoloji {len(STM_COIL_IDS)} — "
        "son bobin(ler)e komut HIC gitmez"
    )


# ── ÜRETİM KODUNDA ELLE SAYILMIŞ KİMLİK YASAĞI ───────────────────────────────


def test_KRITIK_uretim_kodu_ESP_kimliklerini_ELLE_SAYMAZ():
    """`(6, 7, 8)` / `range(6, 9)` gibi ELLE yazılmış ESP kapsamı YASAK.

    ⚠️ FAZ 4'TE ÜÇ YERDE BULUNDU ve hiçbiri hata vermiyordu:
      * `apps/backend/backend_service.py`  → kapanış STOP döngüsü `range(6, 9)`
      * `apps/backend/servers/ai_router.py` × 2 → AI start/stop yolları `for _cid in (6, 7, 8)`

    Bobin 6-7 STM'e taşındıktan sonra bu üç yer hâlâ MQTT'ye STOP/START basıyordu
    (dinleyen yok → boşa yayın) ve `ESP_COIL_IDS` ile AYRIŞMIŞ ikinci bir topoloji
    kaynağı oluşturuyordu. Ayrışmanın tersi daha tehlikeli: kapsam elle yazılı kalırsa
    yeni bir ESP bobini eklendiğinde kapanış/AI yolları onu ATLAR → bobin enerjili kalır.

    MUTASYON: `apps/backend/backend_service.py`de `sorted(_ESP_COIL_IDS)` → `range(6, 9)` yaz → KIRMIZI.
    """
    import re as _re

    # ⚠️ D1.40 (B-10.108): ilk hedef eskiden kök düzeyindeki "backend_service.py" idi — dosya F4'te
    # `apps/backend/`a taşındı ve `if not p.exists(): continue` onu SESSİZCE atlıyordu: kapanış STOP
    # döngüsüne `range(6, 9)` yazılsa YEŞİL (vakum). Artık doğru yol + yoksa KIRMIZI.
    HEDEFLER = _ESP_KAPSAM_HEDEFLERI
    # `(6, 7, 8)` · `[6, 7, 8]` · `range(6, 9)` — ESP kapsamını elle sayan kalıplar
    DESEN = _re.compile(r"range\(\s*6\s*,\s*9\s*\)|[(\[]\s*6\s*,\s*7\s*,\s*8\s*[)\]]")
    ihlal: list[str] = []
    for rel in HEDEFLER:
        p = KOK / rel
        assert p.exists(), f"hedef dosya YOK: {rel} — kapı onu sessizce atlamamalı (taşındıysa listeyi güncelle)"
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            kod = satir.split("#", 1)[0]  # yorumdaki örnek/açıklama ihlal DEĞİL
            if DESEN.search(kod):
                ihlal.append(f"{rel}:{no} {satir.strip()[:80]}")
    assert not ihlal, (
        "ESP bobin kapsami ELLE sayilmis — tek kaynak `servers.live_state.ESP_COIL_IDS`. "
        "Bulunanlar: " + " | ".join(ihlal)
    )


def test_KARSIT_KANIT_elle_sayma_kapisi_GERCEKTEN_yakalar():
    """Öz-test: desen hem yakalamalı hem yorumdaki örneği/alakasız aralığı ATLAMALI."""
    import re as _re

    DESEN = _re.compile(r"range\(\s*6\s*,\s*9\s*\)|[(\[]\s*6\s*,\s*7\s*,\s*8\s*[)\]]")
    assert DESEN.search("for c in range(6, 9):"), "range(6, 9) yakalanmadi"
    assert DESEN.search("for _cid in (6, 7, 8):"), "(6, 7, 8) yakalanmadi"
    assert DESEN.search("ids = [6, 7, 8]"), "[6, 7, 8] yakalanmadi"
    assert not DESEN.search("for c in range(1, 9):"), "ALAKASIZ aralik ihlal sayildi"
    assert not DESEN.search("x = (6, 7)"), "iki elemanli demet ihlal sayildi"
    # Yorum ayiklama testin KENDI dongusunde; burada desenin kodu gordugunu pinliyoruz.
    assert DESEN.search("y = range(6, 9)  # aciklama"), "yorumlu KOD satiri atlanmamali"


# ── D1.40 · B-10.108: ESP kapsam noktaları AST ile — literal demet/liste/`range` YAKALANIR ───────────
#
# Regex kapısı yalnız `(6, 7, 8)` / `[6, 7, 8]` / `range(6, 9)` biçimlerini görüyordu: `sorted(ESP_COIL_IDS)`
# yerine `(8,)`, `[8]`, `(6, 7)` yazılsa (ESP kapsamı daralır ya da yanlış bobine gider) YEŞİL kalıyordu.


def _esp_adi_mi(d) -> bool:
    import ast

    return (isinstance(d, ast.Name) and d.id.lstrip("_") == "ESP_COIL_IDS") or (
        isinstance(d, ast.Attribute) and d.attr == "ESP_COIL_IDS"
    )


def _esp_turevli_mi(ifade) -> bool:
    """İZİN LİSTESİ: yalnız `ESP_COIL_IDS` adı ya da `sorted/list/tuple/set(<o ad>)`. 1-B bağımsız inceleme (i4):
    eskiden `"ESP_COIL_IDS" in ast.unparse(...)` alt-dize denetimiydi — `sorted(ESP_COIL_IDS | {6, 7})` (AI Auto STM
    bobinlerine MQTT START, FAZ-4 hatası) YEŞİLDİ; birleşim, dilim ve kavrama artık reddedilir."""
    import ast

    if _esp_adi_mi(ifade):
        return True
    return (
        isinstance(ifade, ast.Call)
        and getattr(ifade.func, "id", "") in ("sorted", "list", "tuple", "set")
        and len(ifade.args) == 1
        and not ifade.keywords
        and _esp_adi_mi(ifade.args[0])
    )


def _literal_tamsayi_kumesi(ifade) -> bool:
    import ast

    if (
        isinstance(ifade, ast.Call)
        and getattr(ifade.func, "id", "") in ("sorted", "list", "tuple", "set")
        and ifade.args
    ):
        return _literal_tamsayi_kumesi(ifade.args[0])
    if isinstance(ifade, (ast.Tuple, ast.List, ast.Set)):
        return bool(ifade.elts) and all(
            isinstance(e, ast.Constant) and isinstance(e.value, int) and not isinstance(e.value, bool)
            for e in ifade.elts
        )
    if isinstance(ifade, ast.Call) and getattr(ifade.func, "id", "") == "range":
        return all(isinstance(a, ast.Constant) for a in ifade.args)
    return False


def esp_kapsam_noktalari(kaynak: str) -> list[tuple[str, object]]:
    """ESP kapsamını süren üç pinli nokta → (ad, yinelenebilir ifade). Bulunamayan nokta AssertionError."""
    import ast

    agac = ast.parse(kaynak)
    sonuc = []
    for n in ast.walk(agac):
        # kapanış: [threading.Thread(target=_stop_esp, …) for c in <X>]
        if isinstance(n, ast.ListComp) and "_stop_esp" in ast.unparse(n.elt):
            sonuc.append(("kapanis_esp_stop", n.generators[0].iter))
        # AI (Auto) başlatma / AI Pro teardown: for _cid in <X>: _mqtt_publish(f"pemf/coil/{_cid}/control", {... aiauto_ / ai_stop_ ...})
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name):
            govde = ast.unparse(ast.Module(body=n.body, type_ignores=[]))
            if "pemf/coil/{" + n.target.id + "}/control" in govde:
                if "aiauto_" in govde:
                    sonuc.append(("ai_auto_esp_start", n.iter))
                elif "ai_stop_" in govde:
                    sonuc.append(("ai_teardown_esp_stop", n.iter))
    return sonuc


def _esp_nokta_ihlalleri() -> list[str]:
    noktalar = []
    for rel in _ESP_KAPSAM_HEDEFLERI:
        noktalar += [(rel, ad, it) for ad, it in esp_kapsam_noktalari((KOK / rel).read_text(encoding="utf-8"))]
    adlar = sorted(ad for _r, ad, _i in noktalar)
    assert adlar == ["ai_auto_esp_start", "ai_teardown_esp_stop", "kapanis_esp_stop"], (
        f"ESP kapsam noktaları bulunamadı: {adlar}"
    )
    import ast

    return [f"{rel} {ad}: {ast.unparse(it)}" for rel, ad, it in noktalar if not _esp_turevli_mi(it)]


def test_KRITIK_D140_ESP_kapsam_noktalari_ESP_COIL_IDS_ten_TURER():
    assert _esp_nokta_ihlalleri() == []


def test_KRITIK_D140_coil_konusu_yayinlayan_dongu_LITERAL_kumeyle_donmez():
    """Genel tarama: döngü değişkeni `pemf/coil/{v}/` konusunda kullanılan HER for/kavrama yinelenebiri
    literal tamsayı kümesi ya da sabit `range` OLAMAZ. Bilinçli istisnalar gerekçeli ve TAM (dosya, ifade)."""
    import ast

    izinli = {
        # Açılış mutabakatı: 1..8 TÜM slotlara STOP — güvenli yön (Ö.4-Y8: STOP genişler, daralmaz).
        ("apps/backend/backend_service.py", "range(1, 9)"),
    }
    ihlal = []
    for rel in _ESP_KAPSAM_HEDEFLERI:
        for n in ast.walk(ast.parse((KOK / rel).read_text(encoding="utf-8"))):
            if not isinstance(n, ast.For) or not isinstance(n.target, ast.Name):
                continue
            konu = any(
                isinstance(j, ast.JoinedStr)
                and "pemf/coil/"
                in "".join(x.value for x in j.values if isinstance(x, ast.Constant) and isinstance(x.value, str))
                and any(
                    isinstance(x, ast.FormattedValue)
                    and "cid" in ast.unparse(x.value)
                    or (
                        isinstance(x, ast.FormattedValue)
                        and isinstance(x.value, ast.Name)
                        and x.value.id == n.target.id
                    )
                    for x in j.values
                )
                for j in ast.walk(ast.Module(body=n.body, type_ignores=[]))
            )
            if konu and _literal_tamsayi_kumesi(n.iter) and (rel, ast.unparse(n.iter)) not in izinli:
                ihlal.append(f"{rel}:{n.iter.lineno} for {n.target.id} in {ast.unparse(n.iter)}")
    bilinen = [i for i in ihlal if i.startswith("apps/backend/servers/ai_router.py") and "(5, 6)" in i]
    assert [i for i in ihlal if i not in bilinen] == [], ihlal


@pytest.mark.xfail(
    strict=True,
    reason="AÇIK (S-1.1/B-5.2 → D1.83/D1.84, Y25): AI Pro bobin 6-7'yi hâlâ MQTT'ye `for idx in (5, 6)` ile "
    "sürüyor; 6-7 STM'e yönlendirilince bu kol GEÇER ve strict xfail KIRMIZI olur → işareti kaldırın.",
)
def test_ACIK_D184_AI_Pro_6_7_MQTT_indeks_bicimi_KALDIRILDI():
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    assert "for idx in (5, 6):" not in src


@pytest.mark.parametrize(
    ("dosya", "eski", "yeni"),
    [
        ("apps/backend/servers/ai_router.py", "for _cid in sorted(_api_esp.ESP_COIL_IDS):", "for _cid in (8,):"),
        ("apps/backend/servers/ai_router.py", "for _cid in sorted(_api2.ESP_COIL_IDS):", "for _cid in (6, 7):"),
        ("apps/backend/backend_service.py", "for c in sorted(_ESP_COIL_IDS)", "for c in [8]"),
        (
            "apps/backend/servers/ai_router.py",
            "for _cid in sorted(_api_esp.ESP_COIL_IDS):",
            "for _cid in sorted(_api_esp.ESP_COIL_IDS | {6, 7}):",
        ),
        (
            "apps/backend/servers/ai_router.py",
            "for _cid in sorted(_api2.ESP_COIL_IDS):",
            "for _cid in sorted(_api2.ESP_COIL_IDS)[:1]:",
        ),
    ],
    ids=[
        "ai_auto_TEK_ELEMANLI_demet",
        "ai_teardown_IKI_bobin",
        "kapanis_LISTE",
        "ai_auto_BIRLESIM_6_7",
        "teardown_DILIM",
    ],
)
def test_ARAC_D140_AST_kolu_mutantta_KIRMIZI(dosya, eski, yeni):
    """Öz-denetim: regex kapısının KÖR kaldığı biçimler AST kolunda yakalanır (bellek içi mutant)."""
    import ast

    kaynak = (KOK / dosya).read_text(encoding="utf-8")
    assert kaynak.count(eski) == 1, f"ÇAPA ÇÜRÜDÜ (aparat, kapı değil): {eski!r} {kaynak.count(eski)} kez"
    noktalar = esp_kapsam_noktalari(kaynak.replace(eski, yeni))
    assert [ad for ad, it in noktalar if not _esp_turevli_mi(it)], (
        f"mutant yakalanmadı: {[(a, ast.unparse(i)) for a, i in noktalar]}"
    )
