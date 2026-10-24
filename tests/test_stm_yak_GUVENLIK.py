# -*- coding: utf-8 -*-
"""STM32 YAKMA GÜVENLİK KAPILARI — `scripts/stm_yak.py` (plan Faz 2).

Yakma MCU'yu **resetler**: o an sürülen bobinler ANİDEN durur. Hasta üzerindeyken bu
kabul edilemez. Bu yüzden betiğin ön kontrolleri pazarlığa kapalıdır ve burada
**davranışsal** olarak sınanır — sahte bir backend'e karşı gerçek HTTP ile.

İDDİALAR
  1. Aktif seans varsa YAKMAZ
  2. Bobin sürülüyorsa YAKMAZ (seans yok olsa bile — manuel kipte tek bobin sürülebilir)
  3. Bobin durumu OKUNAMIYORSA yakmaz (**fail-closed**)
  4. Backend KAPALIYSA yakar (**fail-open, bilerek**): kimse bobin sürmüyor demektir;
     aksi hâlde betik backend çökükken hiç kullanılamazdı — asıl ihtiyaç anı orasıdır
  5. Yedek yakmadan ÖNCE alınır; alınamazsa hiç yakılmaz (geri dönüşsüz işlem YOK)
  6. Banner UYUMSUZ (`False`) → otomatik GERİ DÖN
  7. Banner TANINMADI (`None`) → geri DÖNÜLMEZ; backend'in uyum kapısıyla aynı üç-durumlu
     karar (banner biçimi ileride değişip UYUMLU bir firmware de tanınmayabilir)

⚠️ Yakıcı/UART GERÇEKTEN çağrılmaz: `_kos` ve banner okuma yamalanır. Ölçtüğümüz şey
   KARAR MANTIĞI ve SIRA; donanımın kendisi değil.
"""

from __future__ import annotations

import importlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)
BETIK_DIZINI = KOK / "scripts"
CEKIRDEK = KOK / "apps" / "backend" / "utils" / "stm_yakma.py"


@pytest.fixture(scope="module")
def yak_modulu():
    """Çekirdek: `utils.stm_yakma`.

    ⚠️ ÖNCEDEN `scripts/stm_yak.py`yi sınıyordu. Ölçüldü (2026-09-22): sevk edilen pakete
    `scripts/*.py` HİÇ girmiyor (`make_base_zip.ADD_SCRIPTS` yalnız altı `.ps1`). Sahip
    kararıyla firmware güncellemesi OTOMATİK olacak, yani akış KURULU CİHAZDA koşacak —
    mantık `scripts/` altında kalsaydı sahada hiç bulunmazdı ve kapı SEVK EDİLMEYEN kodu
    sınıyor olurdu. Çekirdek `apps/backend/utils/` altına taşındı; betik ince CLI yüzü.
    """
    return importlib.import_module("utils.stm_yakma")


class _SahteBackend:
    """Gerçek HTTP — `urllib` yolu da sınansın diye monkeypatch DEĞİL, sunucu."""

    def __init__(self, saglik: dict | None, anlik: dict | None):
        self._saglik, self._anlik = saglik, anlik
        disari = self

        class Ele(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                govde = disari._saglik if self.path.startswith("/api/health") else disari._anlik
                if govde is None:
                    self.send_response(500)
                    self.end_headers()
                    return
                ham = json.dumps(govde).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(ham)))
                self.end_headers()
                self.wfile.write(ham)

            def log_message(self, *a):  # sessiz
                return

        self._sunucu = HTTPServer(("127.0.0.1", 0), Ele)
        self._t = threading.Thread(target=self._sunucu.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self._t.start()
        return f"http://127.0.0.1:{self._sunucu.server_address[1]}"

    def __exit__(self, *a):
        self._sunucu.shutdown()
        self._sunucu.server_close()


# ──────────────────────────────────────────────────────────────────────────
# 1) ÖN KONTROLLER — davranışsal
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "saglik,anlik,guvenli,neden",
    [
        ({"sessionActive": True}, {"coils": []}, False, "aktif seans"),
        ({"sessionActive": False}, {"coils": [{"id": 3, "running": True}]}, False, "bobin sürülüyor"),
        ({"sessionActive": False}, {"coils": [{"id": 3, "active": True}]}, False, "bobin aktif (alternatif alan)"),
        ({"sessionActive": False}, None, False, "bobin durumu OKUNAMADI → fail-closed"),
        ({"sessionActive": False}, {"coils": [{"id": 1, "running": False}]}, True, "temiz"),
    ],
)
def test_KRITIK_on_kontrol_KARARI(yak_modulu, saglik, anlik, guvenli, neden):
    with _SahteBackend(saglik, anlik) as adres:
        sonuc, aciklama = yak_modulu.seans_ve_bobin_kontrolu(adres)
    assert sonuc is guvenli, f"{neden}: beklenen {guvenli}, bulunan {sonuc} — {aciklama}"


def test_KRITIK_backend_KAPALIYKEN_yakmaya_izin_VERIR(yak_modulu):
    """⚠️ BİLEREK fail-open: backend yoksa kimse bobin sürmüyordur.

    Aksi hâlde betik backend çökükken hiç kullanılamazdı — oysa asıl ihtiyaç anı orasıdır.
    (Bobin durumu OKUNAMIYORSA fail-CLOSED; ayrım: backend YOK ≠ backend VAR ama cevap vermiyor.)
    """
    guvenli, aciklama = yak_modulu.seans_ve_bobin_kontrolu("http://127.0.0.1:1")
    assert guvenli is True, aciklama
    assert "backend" in aciklama.lower()


# ──────────────────────────────────────────────────────────────────────────
# 2) SIRA + GERİ DÖNÜŞ — asıl güvenlik değişmezi
# ──────────────────────────────────────────────────────────────────────────


def _sahte_kur(monkeypatch, m, banner_sonucu, yedek_olsun=True, yak_olsun=True):
    """Yakıcıyı/UART'ı yamala; çağrı SIRASINI kaydet."""
    sira: list[str] = []

    monkeypatch.setattr(m, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(m, "seans_ve_bobin_kontrolu", lambda _b: (True, "test"))

    def _yedek(_cli, hedef: Path, _boyut):
        sira.append("yedek")
        if not yedek_olsun:
            return False, "yedek alinamadi"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(b"ESKI")
        return True, str(hedef)

    def _yak(_cli, ikili: Path):
        sira.append(f"yak:{'yedek' if ikili.read_bytes() == b'ESKI' else 'yeni'}")
        return yak_olsun, ""

    monkeypatch.setattr(m, "yedek_al", _yedek)
    monkeypatch.setattr(m, "yak", _yak)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    monkeypatch.setattr(m, "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    monkeypatch.setattr(m, "baslat", lambda _c: (True, ""))
    monkeypatch.setattr(m, "banner_dogrula", lambda _p: banner_sonucu)
    monkeypatch.setattr(m.time, "sleep", lambda _s: None)
    return sira


@pytest.fixture()
def yeni_bin(tmp_path):
    p = tmp_path / "pemf.bin"
    p.write_bytes(b"YENI")
    return p


def test_KRITIK_YEDEK_yakmadan_ONCE_alinir(monkeypatch, yak_modulu, yeni_bin, tmp_path):
    sira = _sahte_kur(monkeypatch, yak_modulu, (True, "uyumlu", "-> STM_READY: DDS v2.3 (7-ch ...)"))
    rc = yak_modulu.yakma_akisi(yeni_bin, yedek_dizin=tmp_path / "y").kod
    assert rc == 0, "temiz akışta 0 dönmeliydi"
    assert sira[0] == "yedek", f"YEDEK ÖNCE alınmalı, sıra: {sira}"
    assert sira[1] == "yak:yeni", f"sıra: {sira}"


def test_KRITIK_yedek_ALINAMAZSA_hic_yakmaz(monkeypatch, yak_modulu, yeni_bin, tmp_path):
    """Geri dönüşü olmayan işlem YAPILMAZ."""
    sira = _sahte_kur(monkeypatch, yak_modulu, (True, "", ""), yedek_olsun=False)
    rc = yak_modulu.yakma_akisi(yeni_bin, yedek_dizin=tmp_path / "y").kod
    assert rc == 6, f"yedek alınamadı → 6 beklenirdi, {rc} döndü"
    assert not any(s.startswith("yak:") for s in sira), f"YAKMAMALIYDI, sıra: {sira}"


def test_KRITIK_banner_UYUMSUZSA_geri_doner(monkeypatch, yak_modulu, yeni_bin, tmp_path):
    sira = _sahte_kur(
        monkeypatch,
        yak_modulu,
        (False, "kart 5 kanalli, uygulama 7 gonderiyor", "-> STM_READY: DDS v1.0 (5-ch ...)"),
    )
    rc = yak_modulu.yakma_akisi(yeni_bin, yedek_dizin=tmp_path / "y").kod
    assert rc == 8, f"uyumsuz banner → 8 beklenirdi, {rc} döndü"
    assert sira == ["yedek", "yak:yeni", "yak:yedek"], f"OTOMATİK GERİ DÖNÜŞ olmalıydı, sıra: {sira}"


def test_KRITIK_T_a_kart_DOGRULANAMADIYSA_GERI_DONER(monkeypatch, yak_modulu, yeni_bin, tmp_path):
    """⚠️ T-a (Tezgâh-2 #1, sahip Y195) — eski kural ("`None` geri dönüş sebebi DEĞİLDİR", banner biçimi değişen uyumlu firmware'i
    korumak için) TERSİNE çevrildi: tezgâhta uyumsuz 120 B imaj yakıldı, eski kart NACK'i düşürdüğü için karar `None` oldu ve imaj
    kartta KALDI (rc 9). Kanıtsız yeni firmware kartta bırakılmaz → önceki firmware'e dönülür (kod 15). Seans kapısı (`uyum_denetle`)
    DEĞİŞMEDİ: "bilinmiyor" orada seansı engellemez. Port meşgulken (PORT_MESGUL, D1.114) dönülmez — o kol ayrı kapıda.
    (Eski ad: test_KRITIK_banner_TANINMAZSA_geri_DONMEZ.)"""
    sonuclar = iter([(None, "banner tanınmadı", "-> STM_READY: ?"), (None, "banner tanınmadı", "-> STM_READY: ESKI")])
    sira = _sahte_kur(monkeypatch, yak_modulu, None)
    monkeypatch.setattr(yak_modulu, "banner_dogrula", lambda _p: next(sonuclar))
    rc = yak_modulu.yakma_akisi(yeni_bin, yedek_dizin=tmp_path / "y").kod
    assert rc == yak_modulu.DOGRULANAMADI_GERI_DONULDU == 15, f"doğrulanamayan firmware → 15 beklenirdi, {rc} döndü"
    assert sira == ["yedek", "yak:yeni", "yak:yedek"], f"OTOMATİK GERİ DÖNÜŞ olmalıydı, sıra: {sira}"


# ──────────────────────────────────────────────────────────────────────────
# 3) BÜTÜNLÜK + TEK KAYNAK
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_sha256_TUTMAZSA_yakmaz(yak_modulu, yeni_bin):
    s = yak_modulu.yakma_akisi(yeni_bin, beklenen_sha256="deadbeef", kuru=True)
    assert s.kod == yak_modulu.BUTUNLUK, f"bütünlük kapısı → BUTUNLUK beklenirdi, {s.kod}"


def test_banner_ayristirma_TEK_KAYNAKTAN(yak_modulu):
    """Betik kendi regex'ini YAZMAZ — backend'in uyum kapısıyla aynı şeyi görmeli.

    Bu depoda `_DB_ERROR` demetleri iki modülde sessizce ayrışmıştı; aynı sınıf.
    """
    from utils import stm32_kimlik

    assert yak_modulu.banner_ayristir is stm32_kimlik.banner_ayristir
    assert yak_modulu.uyum_denetle is stm32_kimlik.uyum_denetle
    kaynak = CEKIRDEK.read_text(encoding="utf-8")
    assert "STM_READY: DDS" not in kaynak.replace("STM_READY: DDS v2.3 (7-ch ...)", ""), (
        "betikte kendi banner deseni var — tek kaynak bozuldu"
    )


def test_yakici_yolu_SABIT_YAZILMAMIS(yak_modulu):
    """CubeIDE sürüm dizini değişir → glob ile aranmalı."""
    kaynak = CEKIRDEK.read_text(encoding="utf-8")
    assert "rglob" in kaynak, "yakıcı glob ile aranmıyor — sürüm dizini değişince bulunamaz"
    assert "STM32CubeIDE_1.17" not in kaynak, "sürüm dizini SABİT yazılmış"


def test_bootloader_alanina_DOKUNULMAZ(yak_modulu):
    """Yalnız uygulama alanı yazılır → yarıda kesilen yakma ST-Link ile kurtarılabilir."""
    assert yak_modulu.YAKMA_ADRESI == "0x08000000"


# ──────────────────────────────────────────────────────────────────────────
# 4) SEVK EDİLEBİLİRLİK — mantık pakete GİREN yerde mi
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_yakma_mantigi_SEVK_EDILEN_yerde():
    """🔴 `scripts/*.py` PAKETE GİRMİYOR — mantık orada kalırsa sahada HİÇ BULUNMAZ.

    Ölçüldü 2026-09-22: `build_tools/make_base_zip.ADD_SCRIPTS` yalnız ALTI `.ps1` taşıyor.
    Sahip kararıyla firmware güncellemesi otomatik; akış kurulu cihazda koşacak.
    Bu kapı, mantığın `utils/` altında (bundle'lanan yer) kalmasını sabitler.
    """
    import ast

    assert CEKIRDEK.is_file(), "çekirdek `utils/stm_yakma.py` YOK"

    # ADD_SCRIPTS gerçekten yalnız .ps1 mı — varsayım değil, ÖLÇÜM
    mbz = (KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")
    agac = ast.parse(mbz)
    listeler = [
        d.value
        for d in ast.walk(agac)
        if isinstance(d, ast.Assign) and any(getattr(h, "id", "") == "ADD_SCRIPTS" for h in d.targets)
    ]
    assert listeler, "ADD_SCRIPTS bulunamadı — çıpa bayat"
    adlar = [e.value for e in listeler[0].elts if isinstance(e, ast.Constant)]
    assert adlar and all(a.endswith(".ps1") for a in adlar), (
        f"ADD_SCRIPTS artık .py de taşıyor: {adlar} — bu kapının gerekçesi değişti, gözden geçirin"
    )

    # CLI İNCE olmalı: yakma/yedek/banner mantığı betikte DEĞİL
    cli = (BETIK_DIZINI / "stm_yak.py").read_text(encoding="utf-8")
    for yasak in ("STM32_Programmer_CLI.exe", "port=SWD", "rglob("):
        assert yasak not in cli, f"CLI betiğinde çekirdek mantık var ({yasak!r}) — sevk edilmeyen yere kod kaçmış"
    assert "from utils.stm_yakma import" in cli, "CLI çekirdeği import etmiyor"
