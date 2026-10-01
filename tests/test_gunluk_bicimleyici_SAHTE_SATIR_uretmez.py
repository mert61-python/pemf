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

Y41 (sahip, 2026-10-01 · 1-A açık madde 4): yığın izi doğası gereği çok satırlıdır, ama son satırı istisna
METNİNİ taşır — `RuntimeError("a\\n2026-10-01 … CRITICAL … SAHTE")` izde zaman damgasıyla başlayan SAHTE bir
kayıt satırı üretiyordu. Artık izin (ve `stack_info`'nun) HER satırı `  | ` önekiyle yazılır; iz okunur kalır.
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
    assert IZ_ONEKI + "Traceback (most recent call last):" in satirlar, f"yığın izi bozuldu: {satirlar}"


# ── Y41 · yığın izinin her satırı önekli ────────────────────────────────────

IZ_ONEKI = "  | "


def _iz_satirlari_denetle(cikti: str) -> list[str]:
    """İlk satır kaydın kendisi; SONRAKİ her satır önekli. Zaman damgasıyla başlayan ikinci bir satır YOK."""
    satirlar = cikti.splitlines()
    assert len(satirlar) >= 2, f"iz yazılmadı: {cikti!r}"
    oneksiz = [s for s in satirlar[1:] if not s.startswith(IZ_ONEKI)]
    assert oneksiz == [], f"yığın izinde ÖNEKSİZ satır (sahte kayıt satırı olabilir): {oneksiz}"
    assert not any(s.startswith("2026-10-01 03:00:00 CRITICAL") for s in satirlar), satirlar
    assert "\r" not in cikti, f"izde ham CR: {cikti!r}"
    return satirlar


def _istisnayla(metin: str):
    def cagri(lg):
        try:
            raise RuntimeError(metin)
        except RuntimeError:
            lg.exception("hata")

    return cagri


@pytest.mark.parametrize(
    "metin", [f"satir1\n{SAHTE}", f"satir1\r\n{SAHTE}", f"satir1\r{SAHTE}"], ids=["LF", "CRLF", "CR"]
)
def test_KRITIK_Y41_istisna_METNINDEKI_satir_sonu_yigin_izinde_SAHTE_SATIR_uretmez(metin):
    satirlar = _iz_satirlari_denetle(_yaz(_istisnayla(metin)))
    assert IZ_ONEKI + "Traceback (most recent call last):" in satirlar, satirlar
    assert any("SAHTE SATIR" in s for s in satirlar), "istisna metni kayboldu (yalnız öneklenmeli)"


def test_KRITIK_Y41_stack_info_da_oneklenir():
    _iz_satirlari_denetle(_yaz(lambda lg: lg.error("yigin", stack_info=True)))


def test_KRITIK_Y41_baska_bicimleyicinin_ONBELLEGE_aldigi_iz_de_oneklenir():
    """logging izi `record.exc_text`'te saklar: kaydı önce başka bir handler (ör. uvicorn'unki) düz
    `logging.Formatter` ile biçimlerse iz ÖNEKSİZ önbelleğe girer; bizim biçimleyici onu da öneklemeli."""
    try:
        raise RuntimeError(f"satir1\n{SAHTE}")
    except RuntimeError:
        kayit = logging.LogRecord("x", logging.ERROR, __file__, 1, "hata", (), sys.exc_info())
    logging.Formatter().format(kayit)
    assert kayit.exc_text and not kayit.exc_text.startswith(IZ_ONEKI), "ön koşul: öneksiz önbellek"
    _iz_satirlari_denetle(_bicimleyici().format(kayit))


def test_KARSIT_Y41_izsiz_kayit_TEK_satir_ve_JSON_kipi_etkilenmez():
    assert _yaz(lambda lg: lg.error("yalin")).count("\n") == 1
    import json

    import backend_service as bs

    try:
        raise RuntimeError(f"satir1\n{SAHTE}")
    except RuntimeError:
        kayit = logging.LogRecord("x", logging.ERROR, __file__, 1, "hata", (), sys.exc_info())
    doc = json.loads(bs._JsonLogFormatter().format(kayit))
    assert "SAHTE SATIR" in doc["exc"], "JSON kipinde iz alanı (zaten tek satır JSON) değişmemeli"


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


def test_KRITIK_Y41_uretim_dosya_gunlugunde_iz_ONEKLI(monkeypatch, tmp_path):
    import backend_service as bs

    yakalanan: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: yakalanan.update(k))
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("PEMF_LOG_JSON", raising=False)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    bs._configure_logging(tmp_path, "INFO")
    handlers = yakalanan["handlers"]
    try:
        try:
            raise RuntimeError(f"upsert reddedildi\n{SAHTE}")
        except RuntimeError:
            kayit = logging.LogRecord(
                "servers.sync_worker", logging.ERROR, __file__, 1, "Sync hatasi", (), sys.exc_info()
            )
        for h in handlers:
            h.handle(kayit)
    finally:
        for h in handlers:
            h.close()
    _iz_satirlari_denetle((tmp_path / "backend_service.log").read_text(encoding="utf-8"))
