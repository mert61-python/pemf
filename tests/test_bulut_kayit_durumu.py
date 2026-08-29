# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BULUT KAYIT DURUMU BAYATLAMAZ — denetim 2026-08-28 #02.

`/api/health` → `cloudRegistry` alanı, uzaktan erişimin çalışıp çalışmadığını söyleyen TEK
makine-okunabilir sinyaldir; yeni arayüz rozeti de buna bakar. Bu yüzden alanın DÜRÜST olması
rozetin kendisinden önce gelir: bayat bir "ok", teşhissizlikten kötüdür — arızayı aktif olarak
gizler ve rozet yanlış susar.

ÖLÇÜLEN AÇIK (çürütme turunda bulundu, ilk reçetede yanlış yere konmuştu): asıl bayatlama yolu
`_publish_device_registry`in DIŞ `except` dalıdır (`logger.warning(...); return False`) — orada
`_registry_status` güncellenmiyordu. `if not self.client` erken çıkışına ise üretimde pratikte
ulaşılmaz (`_ensure_client` istemciyi None'a çekmez), yine de sessiz bırakılmadı.

⚠️ DOKUNULMAYANLAR (bilerek): `secret_mismatch` sınıflandırması, fallback DENEMEME kararı ve
`return False` ile backoff davranışı. Fallback anon tablo-upsert v2 SQL'de zaten reddedilir;
denemek yanıltıcı ikinci bir hata üretir.
"""

from __future__ import annotations

import pytest

from servers.sync_worker import CloudSyncWorker


class _PatlayanIstemci:
    """RPC çağrısında verilen hatayı fırlatan sahte Supabase istemcisi."""

    def __init__(self, mesaj: str):
        self._mesaj = mesaj

    def rpc(self, *a, **k):
        raise RuntimeError(self._mesaj)

    def table(self, *a, **k):  # pragma: no cover — buraya düşülmemeli
        raise AssertionError("fallback tablo-upsert DENENDİ (secret_mismatch'te denenmemeli)")


def _worker(istemci=None) -> CloudSyncWorker:
    w = CloudSyncWorker("https://ornek.supabase.co", "anon-anahtar")
    w.client = istemci
    return w


def test_KRITIK_secret_mismatch_siniflandiriliyor():
    """Ana sinyal: TOFU mühür uyuşmazlığı kendi sınıfını almalı (genel 'error' değil)."""
    w = _worker(_PatlayanIstemci("P0001 device secret mismatch"))
    assert w._publish_device_registry() is False
    assert w._registry_status == "secret_mismatch", (
        f"sır uyuşmazlığı '{w._registry_status}' diye sınıflandı — arayüz doğru teşhisi gösteremez"
    )


def test_ag_hatasi_error_olarak_siniflanir():
    """RPC'nin kendisi patlarsa iç dal zaten 'error' yazar (mevcut davranış korunur)."""
    w = _worker(_PatlayanIstemci("connection reset by peer"))
    w._registry_status = "ok"
    assert w._publish_device_registry() is False
    assert w._registry_status == "error"


def test_KRITIK_RPC_ONCESI_hata_da_bayat_ok_BIRAKMAZ(monkeypatch):
    """⚠️ ASIL BAYATLAMA YOLU — ilk testim bunu ıskalıyordu (mutasyonla ölçüldü).

    RPC çağrısı PATLARSA iç `else` dalı zaten `error` yazıyor; yani "ağ hatası" senaryosu dış
    `except`'i hiç sınamıyor. Dış `except`'e ancak RPC'ye VARILAMADAN oluşan bir hata düşer
    (yerel IP okuma, port çözme, payload kurma). Eskiden o yolda `_registry_status`
    GÜNCELLENMİYORDU: bir kez "ok" olmuş cihaz sonsuza dek "ok" der, /api/health yalan söyler
    ve yeni arayüz rozeti yanlış susar.
    """
    from servers import auto_discovery

    monkeypatch.setattr(
        auto_discovery, "_get_local_ip", lambda *a, **k: (_ for _ in ()).throw(OSError("ag arayuzu okunamadi"))
    )

    class _CagrilmayanIstemci:
        def rpc(self, *a, **k):  # pragma: no cover — buraya varılmamalı
            raise AssertionError("RPC'ye varıldı — senaryo RPC ÖNCESİ hatayı sınamıyor")

    w = _worker(_CagrilmayanIstemci())
    w._registry_status = "ok"  # önceki başarılı tur
    assert w._publish_device_registry() is False
    assert w._registry_status != "ok", (
        "RPC öncesi hata sonrası durum 'ok' KALDI → bayat sinyal; /api/health sağlıklı der, "
        "rozet susar, arıza görünmez (denetim #02'nin sinyal tarafı)"
    )
    assert w._registry_status == "error"


def test_KRITIK_secret_mismatch_sonraki_turda_KORUNUR(monkeypatch):
    """Kalıcı tanı, sonradan gelen bir RPC-öncesi hatayla genel 'error'a DÜŞÜRÜLMEMELİ —
    yoksa rozet 'geçici ağ sorunu' der ve operatör kalıcı arızayı geçici sanar."""
    w = _worker(_PatlayanIstemci("P0001 device secret mismatch"))
    w._publish_device_registry()
    assert w._registry_status == "secret_mismatch"

    from servers import auto_discovery

    monkeypatch.setattr(
        auto_discovery, "_get_local_ip", lambda *a, **k: (_ for _ in ()).throw(OSError("ag arayuzu okunamadi"))
    )
    w._publish_device_registry()
    assert w._registry_status == "secret_mismatch", "kalıcı tanı genel hataya düşürüldü"


def test_istemci_yokken_durum_sessiz_kalmaz():
    """İstemci hiç kurulmamışsa da durum yazılır (arayüz belirsizlikte kalmasın)."""
    w = _worker(None)
    assert w._publish_device_registry() is False
    assert w._registry_status == "istemci_yok"


def test_KARSIT_KANIT_secret_mismatchte_fallback_DENENMEZ():
    """Fallback anon tablo-upsert v2 SQL'de zaten reddedilir; denemek yanıltıcı ikinci hata
    üretir. `_PatlayanIstemci.table` çağrılırsa AssertionError fırlar."""
    w = _worker(_PatlayanIstemci("P0001 device secret mismatch"))
    w._publish_device_registry()  # AssertionError fırlarsa test kırmızı olur
    assert w._registry_status == "secret_mismatch"


def test_saglik_ucu_durumu_YAYINLIYOR():
    """Sözleşmenin ucu: /api/health alanı taşımalı (arayüz rozeti buna bağlı)."""
    from fastapi.testclient import TestClient

    from servers import api_server

    c = TestClient(api_server.app, client=("127.0.0.1", 51242))
    d = c.get("/api/health").json()
    assert "cloudRegistry" in d, "/api/health cloudRegistry alanını yayınlamıyor — rozet kör kalır"


def test_arayuz_bu_alani_GERCEKTEN_okuyor():
    """⚠️ BULGUNUN ÖZÜ: alan yayınlanıyordu ama hiçbir üretim dosyası OKUMUYORDU.

    Sözleşmenin iki ucu da tutulmalı; yalnız backend'i kilitlemek bu arızayı tekrar üretir."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1] / "pf" / "src"
    okuyanlar = [
        p
        for p in kok.rglob("*.ts*")
        if "__tests__" not in p.parts and "cloudRegistry" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert okuyanlar, (
        "pf/ altında `cloudRegistry` okuyan ÜRETİM dosyası yok — backend durumu yayınlıyor ama "
        "hiçbir ekran göstermiyor (bulgunun ta kendisi)"
    )


@pytest.mark.parametrize("durum", ["secret_mismatch", "rpc_missing", "error", "istemci_yok"])
def test_arayuz_her_bozuk_durumu_TANIYOR(durum):
    """Backend'in üretebildiği her bozuk durumun arayüzde bir karşılığı olmalı; aksi hâlde
    yeni bir durum eklendiğinde rozet sessizce susar (aynı sınıf, yeni örnek)."""
    from pathlib import Path

    # ⚠️ ÇIPA: `case "<durum>":` aranır, düz metin DEĞİL. İlk hâli düz metin araması yapıyordu
    # ve `secret_mismatch`i DOSYA BAŞINDAKİ YORUMDA buluyordu → `case` dalını silen mutasyon
    # kapıyı YEŞİL bırakıyordu (ölçüldü). Bu projede aynı zayıf-çıpa hatası daha önce iki kez
    # ısırdı; kural: çıpayı gerçek koda pinle, açıklama metnine değil.
    kaynak = (Path(__file__).resolve().parents[1] / "pf" / "src" / "services" / "bulutKayit.ts").read_text(
        encoding="utf-8"
    )
    assert f'case "{durum}":' in kaynak, (
        f"arayüz '{durum}' durumu için bir `case` dalı taşımıyor → o durumda rozet SUSAR"
    )
