# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.31 (B-3.96) — `config.json` yazım yolunun iki koruması DAVRANIŞLA ölçülür.

`tests/test_config_manager_safety.py` iki korumayı kaynak METNİNDE arıyordu (`inspect.getsource`): (1) şifreleme
yapılamadığında `enc:` öneki EKLENMEZ (yanlış güvence: dosyayı inceleyen sırrı şifreli sanar); (2) yazım ATOMİKTİR
(tmp + fsync + `os.replace`, süreç içi kilit) — güç kesintisi / disk dolması `config.json`u 0 bayt ya da yarım bırakmaz,
klinik ayarları varsayılana dönmez. Ölçüldü: önekin koşulsuz eklendiği (M1) ve `os.replace` yerine doğrudan yazıldığı
(M2) mutantlarda o metin kapıları YEŞİL kalıyordu. Bu dosya aynı korumaları GERÇEK `ProductionConfigManager` örneği ve
GERÇEK disk üzerinde ölçer; arıza EN ALT katta, gerçek biçimiyle kurulur (şifreleme `Fernet.encrypt` düzeyinde düşer;
yazım YARIDA kalır: içeriğin yarısı dosyaya iner, sonra `OSError(ENOSPC)`).

A-29 / D2.81 bu yazım yoluna dokunacağı için ÖNKOŞUL kapıdır: iddialar dosya baytları ve genel API (`set` / `save`)
üzerindendir.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

SIR = "SAHTE-MQTT-PAROLA-D231"


@pytest.fixture()
def yonetici(tmp_path, monkeypatch):
    """Taze `ProductionConfigManager`; app-data tmp'de. ACL kilidi kayıtçı (konu ACL değil — D2.79/D2.81 ölçer)."""
    from utils import production_config_manager as pcm

    monkeypatch.setattr(pcm.ProductionConfigManager, "_get_app_data_dir", lambda self: tmp_path)
    import utils.file_acl as _acl

    monkeypatch.setattr(_acl, "lock_down_file", lambda *a, **k: True)
    # Singleton sıfırlanır: aksi hâlde süitin önceki örneği (başka app-data) miras alınır.
    monkeypatch.setattr(pcm.ProductionConfigManager, "_instance", None)
    return pcm


def _uret(pcm):
    return pcm.ProductionConfigManager()


def _ham_bellek(m, yol: str):
    """Bellekteki HAM (çözülmemiş) değer — genel `get` şifreyi çözdüğü için önek orada görünmez."""
    dugum = getattr(m, "_config", {})
    for parca in yol.split("."):
        if not isinstance(dugum, dict) or parca not in dugum:
            return None
        dugum = dugum[parca]
    return dugum


def test_KRITIK_sifreleme_DUSERSE_enc_oneki_ne_diske_ne_bellege_girer_D231(yonetici, tmp_path, monkeypatch):
    """Şifreleme EN ALT katta düşer (`Fernet.encrypt` istisna); `set('mqtt.pass', …)` sonrası ne diskte ne bellekte
    `enc:` önekli değer olmalı. Değer yazılmışsa dürüstçe DÜZ yazılmıştır (ürün kararı: uyarı + düz, sahte önek yok)."""
    from cryptography.fernet import Fernet

    m = _uret(yonetici)

    def _patla(self, data):
        raise ValueError("sahte: şifreleme yapılamadı (anahtar bozuk)")

    monkeypatch.setattr(Fernet, "encrypt", _patla)
    try:
        m.set("mqtt.pass", SIR)
    except Exception:
        pass  # fail-closed bir sürüm hiç yazmayabilir — iddia yine geçerli: SAHTE ÖNEK YOK

    disk = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "enc:" + SIR not in disk, "diskte 'enc:<DÜZ METİN>' — dosyayı inceleyen sırrı şifreli sanar (yanlış güvence)"
    ham = _ham_bellek(m, "mqtt.pass")
    assert not (isinstance(ham, str) and ham.startswith("enc:")), f"bellekte sahte 'enc:' önekli değer: {ham[:12]!r}…"


def test_KARSIT_sifreleme_CALISIRSA_enc_oneki_EKLENIR_ve_cozulur_D231(yonetici, tmp_path):
    """Karşıt: şifreleme çalışıyorsa disk `enc:` önekli ŞİFRELİ değer taşır (düz sır diskte YOK) ve `get` çözer.
    Bu kol olmadan yukarıdaki kapı 'hiç şifrelemeyen' bir sürümde de yeşil kalırdı."""
    m = _uret(yonetici)
    m.set("mqtt.pass", SIR)
    disk = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert SIR not in disk, "şifreleme çalışırken sır diske DÜZ yazıldı"
    assert '"enc:' in disk, "şifreli değer 'enc:' önekiyle işaretlenmedi"
    assert m.get("mqtt.pass") == SIR


def test_KRITIK_yazim_YARIDA_duserse_config_ESKI_baytlarla_kalir_D231(yonetici, tmp_path, monkeypatch):
    """Disk yazımın ORTASINDA dolar: içeriğin yarısı dosyaya iner, sonra `OSError(ENOSPC)`. `config.json` önceki
    baytlarla AYNI kalmalı ve yeni bir örnek önceki ayarı okumalı (truncate-then-write burada dosyayı yarım bırakır)."""
    m = _uret(yonetici)
    m.set("mqtt.broker_url", "192.168.10.5")
    hedef = tmp_path / "config.json"
    once = hedef.read_bytes()

    gercek_dump = json.dump

    def _yarim(obj, fp, *a, **k):
        metin = json.dumps(obj, *a, **k)
        fp.write(metin[: len(metin) // 2])
        fp.flush()
        raise OSError(28, "No space left on device (sahte: disk YARIDA doldu)")

    monkeypatch.setattr(json, "dump", _yarim)
    with pytest.raises(OSError):
        m.set("mqtt.broker_url", "10.0.0.99")
    monkeypatch.setattr(json, "dump", gercek_dump)

    assert hedef.read_bytes() == once, "yarıda kalan yazım config.json'u BOZDU (önceki baytlar değil)"
    yonetici.ProductionConfigManager._instance = None
    assert _uret(yonetici).get("mqtt.broker_url") == "192.168.10.5", "yeni örnek önceki ayarı okuyamadı"


def test_KRITIK_eszamanli_kayitlar_SERILESIR_hata_ve_bozuk_dosya_YOK_D231(yonetici, tmp_path, monkeypatch):
    """İki iş parçacığı aynı anda kaydeder (ör. eşzamanlı iki POST /api/settings). Disk yavaş: her kayıt içeriğin yarısını
    yazar, ~40 ms bekler (AV taraması / yavaş eMMC), kalanını yazar. Kayıtlar serileşmeli: hiçbir kayıt hata vermemeli,
    son dosya geçerli JSON olmalı ve yazılan değerlerden birini taşımalı. Kilit yoksa iki yazıcı ortak .tmp'yi aynı
    anda keser/yazar → takas düşer ya da `config.json` iç içe geçmiş baytlarla kalır.
    (Gecikme takasta değil YAZIMDA: takasta eşit gecikme iki iş parçacığını adım adım ilerletip yarışı tesadüfen
    örtüyordu — ölçüldü, kilitsiz mutant yeşil kaldı.)"""
    m = _uret(yonetici)
    gercek_dump = json.dump

    def _yavas_yazim(obj, fp, *a, **k):
        metin = json.dumps(obj, *a, **k)
        yari = len(metin) // 2
        fp.write(metin[:yari])
        fp.flush()
        time.sleep(0.04)
        fp.write(metin[yari:])

    monkeypatch.setattr(json, "dump", _yavas_yazim)
    hatalar: list[BaseException] = []
    degerler = {"a": [f"10.0.1.{i}" for i in range(6)], "b": [f"10.0.2.{i}" for i in range(6)]}

    def _yaz(ad):
        for d in degerler[ad]:
            try:
                m.set("mqtt.broker_url", d)
            except BaseException as e:  # noqa: BLE001 — kaydın düştüğü HER biçim sayılır
                hatalar.append(e)

    isler = [threading.Thread(target=_yaz, args=(ad,)) for ad in degerler]
    for t in isler:
        t.start()
    for t in isler:
        t.join(30)
    monkeypatch.setattr(json, "dump", gercek_dump)

    assert not hatalar, f"eşzamanlı kayıt DÜŞTÜ ({len(hatalar)}): {hatalar[:2]!r}"
    son = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert son["mqtt"]["broker_url"] in degerler["a"] + degerler["b"], "son dosya yazılan değerlerden birini taşımıyor"
