# Author: mertaygn, cglrgrkn
"""DÜZ-METİN GÜNLÜK BİÇİMLEYİCİSİ CR/LF İLE SAHTE SATIR ÜRETMEZ (Audit P2).

Güvenilmez metin (anonim broker'dan gelen MQTT topic'i, buluttan dönen hata gövdesi, istisna
mesajı) günlüğe yazılınca içindeki CR/LF kalıcı denetim günlüğüne SAHTE bir satır ekler:

    2026-10-01 03:00:00 ERROR [servers.sync_worker] [-] Sync sirasinda beklenmeyen hata: upsert reddedildi
    2026-10-01 03:00:00 CRITICAL [servers.api_server] [-] SAHTE SATIR      <-- kayıt sahteciliği

`backend_service._PlainLogFormatter` eskiden nötrlemeyi `getMessage()` ÖNCESİNDE yalnız `record.msg`'ye
ve *str* argümanlara uyguluyordu; istisna NESNESİ argümanda (`"…: %s", e`) nötrlenmeden geçiyordu.
Bağımsız inceleme (r4, 2026-10-01): D1.18/D1.19'un f-string → `"%s", e` dönüşümleri (sync_worker,
mdns_service, ai_router) bu boşluğu üç çağrıya daha yaydı. Nötrleme artık birleşmiş mesaja uygulanır.
Yığın izi (exc_text) bilinçli olarak dokunulmaz (doğası gereği çok satırlı).
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils.dongu_guvenligi import dongu_hatasini_bildir  # noqa: E402

SAHTE = "2026-10-01 03:00:00 CRITICAL [servers.api_server] [-] SAHTE SATIR"


class _MetinliNesne:
    """`str()`'ü CR/LF taşıyan, str OLMAYAN argüman (ör. üçüncü taraf hata nesnesi)."""

    def __str__(self) -> str:
        return f"nesne\r\n{SAHTE}"


def _bicimleyici() -> logging.Formatter:
    import backend_service as bs

    # Üretimdeki biçim dizesi (`_configure_logging`) — aşağıdaki kablolama kolu aynısını doğrular.
    return bs._PlainLogFormatter(
        "%(asctime)s %(levelname)s [%(name)s] [%(rid)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )


def _yaz(cagri) -> str:
    lg = logging.getLogger("test.gunluk.sahte_satir")
    eski = (lg.propagate, lg.level)
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(_bicimleyici())
    lg.addHandler(h)
    try:
        cagri(lg)
    finally:
        lg.removeHandler(h)
        lg.propagate, lg.level = eski
    return buf.getvalue()


def _istisna(metin: str) -> RuntimeError:
    return RuntimeError(metin)


_ESKI_FSTRING_HATASI = _istisna(f"x\n{SAHTE}")

_CAGRILAR = {
    # Eskiden de korunan biçimler (karşıt: düzeltme bunları BOZMAMALI)
    "str_arguman": lambda lg: lg.error("hata: %s", f"upsert reddedildi\n{SAHTE}"),
    "mesaj_icinde": lambda lg: lg.error(f"AI Loop iteration error: {_ESKI_FSTRING_HATASI}"),
    # Eskiden SIZAN biçimler
    "istisna_arguman": lambda lg: lg.error("Sync sirasinda beklenmeyen hata: %s", _istisna(f"upsert\n{SAHTE}")),
    "nesne_arguman": lambda lg: lg.warning("durum: %s", _MetinliNesne()),
    "yalniz_CR": lambda lg: lg.error("hata: %s", _istisna(f"a\r{SAHTE}")),
    # D1.18/D1.19'un dönüştürdüğü çağrı biçimi AYNEN (yardımcı üzerinden, yığın izi yok)
    "dongu_yardimcisi": lambda lg: dongu_hatasini_bildir(
        "mDNS arayüz-monitör hatası: %s", _istisna(f"y\n{SAHTE}"), logger=lg, exc_info=False
    ),
}


@pytest.mark.parametrize("bicim", list(_CAGRILAR))
def test_KRITIK_guvenilmez_metin_TEK_SATIR_kalir(bicim):
    cikti = _yaz(_CAGRILAR[bicim])
    assert cikti.count("\n") == 1 and "\r" not in cikti, f"{bicim}: günlüğe SAHTE SATIR yazıldı: {cikti!r}"
    # İçerik kaybolmaz, yalnız görünür kaçışa çevrilir.
    assert "SAHTE SATIR" in cikti and ("\\n" in cikti or "\\r" in cikti), cikti


def test_KRITIK_yigin_izli_cagrida_mesaj_TEK_SATIR_iz_KORUNUR():
    def cagri(lg):
        try:
            raise RuntimeError("iz")
        except RuntimeError:
            lg.exception("hata: %s", _istisna(f"satir1\n{SAHTE}"))

    satirlar = _yaz(cagri).splitlines()
    assert "SAHTE SATIR" in satirlar[0] and "\\n" in satirlar[0], satirlar
    assert not any(s.startswith("2026-10-01 03:00:00 CRITICAL") for s in satirlar), satirlar
    assert "Traceback (most recent call last):" in satirlar, f"yığın izi bozuldu: {satirlar}"


def test_KRITIK_uretim_yapilandirmasi_bu_bicimleyiciyi_KULLANIR(monkeypatch, tmp_path):
    """`_configure_logging`'in kurduğu GERÇEK dosya handler'ı → istisna argümanı tek satır."""
    import backend_service as bs

    yakalanan: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: yakalanan.update(k))
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("PEMF_LOG_JSON", raising=False)
    # Gerçek akışlar yeniden yapılandırılmasın / konsol handler'ı eklenmesin.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    bs._configure_logging(tmp_path, "INFO")
    handlers = yakalanan["handlers"]
    try:
        kayit = logging.LogRecord(
            "servers.sync_worker",
            logging.ERROR,
            __file__,
            1,
            "Sync sirasinda beklenmeyen hata: %s",
            (_istisna(f"upsert reddedildi\n{SAHTE}"),),
            None,
        )
        for h in handlers:
            h.handle(kayit)
    finally:
        for h in handlers:
            h.close()
    metin = (tmp_path / "backend_service.log").read_text(encoding="utf-8")
    assert metin.count("\n") == 1, f"üretim günlüğüne SAHTE SATIR yazıldı: {metin!r}"
    assert "SAHTE SATIR" in metin, metin
