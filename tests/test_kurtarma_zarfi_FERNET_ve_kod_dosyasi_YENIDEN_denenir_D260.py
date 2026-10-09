# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.60 (B-3.64 · B-3.94) — kurtarma malzemesi: (a) `KURTARMA-KODU.txt` yazılamazsa parmak izi MÜHÜRLENMEZ, sonraki tur yeniden yazar;
(b) at-rest şifreleme KAPALIYKEN de `patient_fernet_key`i taşıyan zarf yazılır (Karar 31: `sqlcipher_key` ÜRETİLMEZ).

B-3.94: `refresh_recovery_material` parmak izini (`.recovery_fp`) kod dosyasından ÖNCE yazıyordu. Kod dosyası bir kez yazılamazsa (disk
dolu / AV / izin) sonraki turlar "değişmedi + zarf sağlam" deyip erken dönüyor, dosya BİR DAHA yazılmıyordu → operatör kodu hiç
öğrenmiyor; uyarı bandı (kod dosyası yok) hiç görünmüyor, kod ucu "şifreleme kapalı olabilir" diyordu.
B-3.64: `sqlcipher_key` yoksa ("at-rest kapalı") zarf HİÇ yazılmıyordu; oysa 9 hasta alanı (ad, sahip, …) `patient_fernet_key` ile
şifreli → makine ölünce başka makinede okunamaz. Plan bu iki varsayımı taşıyan testleri ("şifreleme kapalıysa zarf yazılmaz",
"şifreleme kapalıyken uyarı yok") yanlış öncüllü sayar.

Kapı GERÇEK `refresh_recovery_material` + GERÇEK sır deposu (conftest veri kökü, DPAPI) + GERÇEK `/api/system/recovery-status`. G/Ç
arızası EN ALT katta, gerçek biçimiyle: kod dosyasının yolunda bir DİZİN durur → yazım/takas işletim sisteminden gerçek hata alır.

Karşıt sınır: kod dosyası bu kod için bir kez YAZILDIYSA ve operatör kodu dışarı alıp sildiyse (dosyanın kendi metni "silebilirsiniz"
der) dosya geri YAZILMAZ. Eski sürümün mührü (kod dosyasından ÖNCE vurulmuş, öneksiz) görülürse kod dosyasına bir kez daha bakılır →
o sürümde takılı kalmış kurulum güncellemeden sonraki ilk turda düzelir; zarf bunun için yeniden yazılmaz.
"""

from __future__ import annotations

import re

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    from servers import api_server
    from utils import backup_recovery as br
    from utils import secrets_manager as sm

    veri = sm._data_dir()
    hedef = tmp_path / "yedek"
    hedef.mkdir()
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: veri)
    istemci = TestClient(api_server.app, client=("127.0.0.1", 51234))
    return br, sm, veri, hedef, istemci


def test_KRITIK_kod_dosyasi_YAZILAMAZSA_muhurlenmez_sonraki_tur_YAZAR_ve_UYARI_ister_D260(ortam):
    br, sm, veri, hedef, istemci = ortam
    # Sentetik değer kısa: gitleaks "generic-api-key" kuralı anahtar adlı alana ≥10 karakterlik yüksek entropili değeri sır sayar.
    sm.set_secrets({"sqlcipher_key": "d260-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    engel = veri / br.CODE_FILE_NAME
    engel.mkdir()  # GERÇEK arıza: kod dosyasının yerinde dizin → yazım/takas düşer
    assert br.refresh_recovery_material(veri, [hedef]) is True, "zarf yazılmalı (yedekler korunur)"
    assert engel.is_dir(), "aparat: kod dosyası yazımı DÜŞMEDİ"
    engel.rmdir()  # arıza geçti (disk boşaldı / AV bıraktı)

    br.refresh_recovery_material(veri, [hedef])
    kod = sm.get_secret("backup_recovery_code", generate=False)
    dosya = veri / br.CODE_FILE_NAME
    assert dosya.is_file(), "kod dosyası bir kez yazılamayınca BİR DAHA denenmedi (parmak izi önceden mühürlenmişti)"
    assert br.format_code(kod) in dosya.read_text(encoding="utf-8")
    assert br.open_envelope(kod, (hedef / br.ENVELOPE_NAME).read_bytes()), "zarf ile kod dosyası aynı kodu taşımalı"
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["codeExists"] is True and durum["warn"] is True, (
        f"operatöre kod henüz gösterilmedi ama uyarı yok: {durum}"
    )


def test_KRITIK_eski_surumun_MUHRU_varken_kod_dosyasi_YOKSA_bir_kez_YAZILIR_zarf_DEGISMEZ_D260(ortam):
    """Eski sürüm mührü kod dosyasından ÖNCE vuruyordu: dosya o sürümde yazılamadıysa kurulum "mühür tamam, zarf sağlam" diye
    takılı kaldı. Güncellemeden sonraki ilk tur dosyayı yazmalı (operatör kodu ancak böyle öğrenir); zarf boşuna yeniden yazılmamalı."""
    br, sm, veri, hedef, istemci = ortam
    sm.set_secrets({"sqlcipher_key": "d260-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    assert br.refresh_recovery_material(veri, [hedef]) is True
    muhur = veri / ".recovery_fp"
    # Eski sürümün yazdığı biçim: yalnız 64 hex parmak izi (`fp_file.write_text(fp)`); önek sabiti mutasyon hedefinden OKUNMAZ.
    eski = re.search(r"[0-9a-f]{64}$", muhur.read_text(encoding="utf-8").strip())
    assert eski, "aparat: mühürde parmak izi yok"
    muhur.write_text(eski.group(0), encoding="utf-8")
    (veri / br.CODE_FILE_NAME).unlink()  # eski sürümde yazılamamış kod dosyası
    zarf = (hedef / br.ENVELOPE_NAME).read_bytes()

    assert br.refresh_recovery_material(veri, [hedef]) is True
    kod = sm.get_secret("backup_recovery_code", generate=False)
    dosya = veri / br.CODE_FILE_NAME
    assert dosya.is_file(), "eski sürümde takılı kalmış kurulum: kod dosyası güncellemeden sonra da YAZILMADI"
    assert br.format_code(kod) in dosya.read_text(encoding="utf-8")
    assert (hedef / br.ENVELOPE_NAME).read_bytes() == zarf, (
        "zarf boşuna yeniden yazıldı (operatörün doğruladığı dosya değişti)"
    )
    assert istemci.get("/api/system/recovery-status").json()["warn"] is True

    dosya.unlink()  # operatör kodu dışarı aldı ve sildi → artık mühür yeni biçimde, dosya geri gelmez
    br.refresh_recovery_material(veri, [hedef])
    assert not dosya.exists(), (
        "iyileştirme kalıcı değil: her turda eski mühür gibi davranıp operatörün sildiği dosyayı geri yazıyor"
    )


def test_KARSIT_operator_kod_dosyasini_SILDIYSE_geri_YAZILMAZ_D260(ortam):
    """Karşıt: kod dosyası bu kod için YAZILDIKTAN sonra operatör kodu dışarı alıp sildiyse ("silebilirsiniz") sonraki turlar dosyayı
    geri yazmaz — kod, zarfla aynı diske kendiliğinden geri dönmez."""
    br, sm, veri, hedef, istemci = ortam
    sm.set_secrets({"sqlcipher_key": "d260-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    assert br.refresh_recovery_material(veri, [hedef]) is True
    dosya = veri / br.CODE_FILE_NAME
    assert dosya.is_file(), "ön koşul: kod dosyası yazılmalı"
    dosya.unlink()
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert not dosya.exists(), "operatörün sildiği kurtarma kodu dosyası geri yazıldı"
    assert istemci.get("/api/system/recovery-status").json()["warn"] is False


def test_KRITIK_sqlcipher_YOKKEN_fernet_anahtari_ZARFA_girer_sqlcipher_URETILMEZ_D260(ortam):
    br, sm, veri, hedef, _ = ortam
    fernet = Fernet.generate_key().decode()
    sm.set_secrets({"patient_fernet_key": fernet})
    assert br.refresh_recovery_material(veri, [hedef]) is True, "at-rest kapalıyken Fernet alanları için zarf YAZILMADI"
    kod = sm.get_secret("backup_recovery_code", generate=False)
    assert br.open_envelope(kod, (hedef / br.ENVELOPE_NAME).read_bytes()) == {"patient_fernet_key": fernet}
    assert not sm.get_secret("sqlcipher_key", generate=False), (
        "kurtarma yolu sqlcipher_key ÜRETTİ (şifrelemeyi kazara açar)"
    )
    assert br.format_code(kod) in (veri / br.CODE_FILE_NAME).read_text(encoding="utf-8")


def test_KRITIK_sifreleme_KAPALIYKEN_fernet_zarfi_VARSA_uyari_ister_D260(ortam):
    """At-rest kapalı kurulumda Fernet zarfı + kod dosyası var → operatör kodu makine dışına almalı: uyarı bandı GEREKİR
    (eski kural "şifreleme kapalıyken uyarı yok" yanlış öncüllü — plan)."""
    br, sm, veri, hedef, istemci = ortam
    sm.set_secrets({"patient_fernet_key": Fernet.generate_key().decode()})
    br.refresh_recovery_material(veri, [hedef])
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["atRestEncrypted"] is False, f"aparat: at-rest kapalı olmalı: {durum}"
    assert durum["codeExists"] is True and durum["warn"] is True, f"Fernet zarfının kodu için uyarı yok: {durum}"


def test_KARSIT_kurtarilacak_ANAHTAR_hic_YOKSA_zarf_ve_kod_URETILMEZ_D260(ortam):
    """Karşıt: hiç anahtar yoksa (taze, şifresiz kurulum) zarf yazılmaz, kod ÜRETİLMEZ, uyarı yok — alarm körlüğü yaratılmaz."""
    br, sm, veri, hedef, istemci = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is False
    assert not (hedef / br.ENVELOPE_NAME).exists() and not (veri / br.CODE_FILE_NAME).exists()
    assert not sm.get_secret("backup_recovery_code", generate=False), "anahtar yokken kurtarma kodu üretildi"
    assert istemci.get("/api/system/recovery-status").json()["warn"] is False
