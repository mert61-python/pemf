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

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))

from servers.live_state import ESP_COIL_IDS, STM_COIL_IDS  # noqa: E402


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
      * `backend_service.py`  → kapanış STOP döngüsü `range(6, 9)`
      * `servers/ai_router.py` × 2 → AI start/stop yolları `for _cid in (6, 7, 8)`

    Bobin 6-7 STM'e taşındıktan sonra bu üç yer hâlâ MQTT'ye STOP/START basıyordu
    (dinleyen yok → boşa yayın) ve `ESP_COIL_IDS` ile AYRIŞMIŞ ikinci bir topoloji
    kaynağı oluşturuyordu. Ayrışmanın tersi daha tehlikeli: kapsam elle yazılı kalırsa
    yeni bir ESP bobini eklendiğinde kapanış/AI yolları onu ATLAR → bobin enerjili kalır.

    MUTASYON: `backend_service.py`de `sorted(_ESP_COIL_IDS)` → `range(6, 9)` yaz → KIRMIZI.
    """
    import re as _re

    HEDEFLER = ("backend_service.py", "servers/ai_router.py", "servers/api_server.py")
    # `(6, 7, 8)` · `[6, 7, 8]` · `range(6, 9)` — ESP kapsamını elle sayan kalıplar
    DESEN = _re.compile(r"range\(\s*6\s*,\s*9\s*\)|[(\[]\s*6\s*,\s*7\s*,\s*8\s*[)\]]")
    ihlal: list[str] = []
    for rel in HEDEFLER:
        p = KOK / rel
        if not p.exists():
            continue
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
