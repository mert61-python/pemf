# -*- coding: utf-8 -*-
"""YLI-A3.8 (L1 · Y82) — "yarım yakma" kaydı yalnız kart DOĞRULANMIŞ bir hâlde bırakıldıysa silinmeli.

Y82 (sahip): "yakmadan ÖNCE 'yarım yakma' kaydı yazılır, doğrulamadan SONRA silinir; açılışta kayıt görülürse kart kimliği/sürümü
doğrulanır, uyumsuzsa yedekten eski firmware'e GERİ DÖNÜLÜR". `firmware_manager._firmware_uygula` kaydı `yakma_akisi` döndükten sonra
SONUÇ NE OLURSA OLSUN siler → yakıcı hatası (YAKMA_HATASI — kart yarım yazılmış olabilir) ve geri dönüş başarısız (GERI_DONUS_BASARISIZ —
"kart ne yeni ne eski firmware'le doğrulanmış") sonrasında kayıt GİDER: sonraki açılış kurtarmaz, STM bağlanmıyorsa "ST-Link ile ELLE
kurtarın: yedek …" iletisi de çıkmaz.

SAHTE EN ALT KATTA: LN L1 kapısının fikstürü (`ortam`: ağ `_pinli_ac`, yakıcı `stm_yakma._kos` sahte FLASH, `programmer_cli`) — LN
dosyasından içe aktarılır (aynı conftest yalıtımı). YLI orkestratörü bağımsız yeniden üretti (HEAD 2 / 3 KIRMIZI) ve kalıcı kapı yaptı.
"""

from __future__ import annotations

from pathlib import Path

from test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN import _ac, _yeni_surec, ortam  # noqa: F401 — fikstür


def _yazma_bozan(o, *, yeni_hata: bool, yedek_hata: bool, yeni_bozuk: bool = False):
    asil = o.kart.kos

    def kos(cli, argumanlar, timeout=300.0):
        a = list(argumanlar)
        if "-w" in a:
            ikili = Path(a[a.index("-w") + 1])
            veri = ikili.read_bytes()
            if ikili.name == "pemf_fw.bin" and yeni_hata:
                o.kart.flash[: len(veri) // 2] = veri[: len(veri) // 2]  # yarıda kalan yazım
                return 1, "sahte: Error: data write failed (ST-LINK bağlantısı koptu)"
            if ikili.name == "pemf_fw.bin" and yeni_bozuk:
                b = bytearray(veri)
                b[7] ^= 0xFF  # flash yazılanı tutmadı → bağımsız geri okuma farklı
                o.kart.flash[: len(b)] = b
                return 0, "sahte: yazıldı (-v geçti ama flash tutmadı)"
            if ikili.name.startswith("pemf_yedek_") and yedek_hata:
                return 1, "sahte: Error: data write failed (geri dönüş)"
        return asil(cli, argumanlar, timeout)

    return kos


def test_KRITIK_A3_8_yakici_HATASINDA_yarim_kayit_KALIR_ve_acilista_ELLE_kurtarma_soylenir(ortam, monkeypatch):
    o = ortam
    monkeypatch.setattr(o.sy, "_kos", _yazma_bozan(o, yeni_hata=True, yedek_hata=False))
    d = _ac(o)
    print(f"A3OLC|Y82|yakici_hatasi|hata={d.get('hata')!r}|kayit={(o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists()}")
    assert "[7]" in d["hata"], d["hata"]  # YAKMA_HATASI
    assert (o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists(), (
        "yakıcı hatası (kart yarım yazılmış olabilir) sonrasında 'yarım yakma' kaydı SİLİNDİ — sonraki açılış kurtaramaz"
    )
    # Kart açılmıyor (yarım uygulama alanı) → STM bağlanmaz: kayıt varsa operatöre yedeğin yolu söylenir (Y76: karta dokunulmaz).
    _yeni_surec(o)
    d2 = _ac(o, surum="", bagli=False)
    print(f"A3OLC|Y82|yakici_hatasi_sonraki_acilis|yarimYakma={d2.get('yarimYakma')!r}")
    assert (d2.get("yarimYakma") or {}).get("sonuc") == "elle", d2.get("yarimYakma")


def test_KRITIK_A3_8_GERI_DONUS_BASARISIZ_sonrasinda_yarim_kayit_KALIR(ortam, monkeypatch):
    o = ortam
    monkeypatch.setattr(o.sy, "_kos", _yazma_bozan(o, yeni_hata=False, yedek_hata=True, yeni_bozuk=True))
    d = _ac(o)
    print(f"A3OLC|Y82|geri_donus_basarisiz|hata={d.get('hata')!r}|kayit={(o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists()}")
    assert "[11]" in d["hata"], d["hata"]  # GERI_DONUS_BASARISIZ
    assert (o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists(), (
        "geri dönüş BAŞARISIZ ('kart ne yeni ne eski firmware'le doğrulanmış') sonrasında 'yarım yakma' kaydı SİLİNDİ"
    )


def test_A3_8_KARSIT_dogrulanmis_sonuclarda_kayit_SILINIR(ortam):
    """Karşıt: yeni firmware doğrulandı (TAMAM) → kayıt silinir (LN testinin de ölçtüğü kol)."""
    o = ortam
    o.d.kart_bildirir = "2.4"
    d = _ac(o)
    assert d["uygulandi"] is True, d
    assert not (o.kok / o.fm.YARIM_YAKMA_DOSYASI).exists()
