"""DENETİM (offsite-backup-no-key-escrow): yedek .db dosyaları SQLCipher ile şifreli ve
anahtar DPAPI CRYPTPROTECT_LOCAL_MACHINE ile MAKİNEYE bağlıydı → anakart/disk arızasında
veya Windows yeniden kurulduğunda HİÇBİR yedek (off-site dahil) açılamıyordu. Yedek sistemi
yalnız mantıksal bozulmaya karşı koruyordu.

Çözüm (sahip kararı D): sistem üretimi 150-bit kurtarma kodu + yedeklerin yanına şifreli
zarf. Bu dosya zarfın kripto sözleşmesini ve — en az onun kadar önemli — KODUN YEDEK
DİZİNİNE SIZMAMASINI kilitler (kod ve zarf aynı yerdeyse koruma sıfırdır)."""

import json
from pathlib import Path

import pytest

from utils import backup_recovery as br


# ── Kod üretimi ve normalleştirme ────────────────────────────────────────────

def test_kod_150_bit_ve_okunabilir():
    c = br.generate_recovery_code()
    assert c.count("-") == 5 and len(br.normalize_code(c)) == 30
    assert all(ch in br._ALPHABET for ch in br.normalize_code(c))
    # 0/1/8/9 alfabede YOK → elle yazımda rakam-harf karışıklığı azalır
    assert not (set("0189") & set(c))


def test_kodlar_benzersiz():
    kodlar = {br.generate_recovery_code() for _ in range(200)}
    assert len(kodlar) == 200, "kod üreteci tekrar üretiyor (entropi sorunu)"


@pytest.mark.parametrize("varyant", [
    "abcde-fghij-klmno-pqrst-uvwxy-z2345",     # küçük harf
    "ABCDE FGHIJ KLMNO PQRST UVWXY Z2345",     # boşluk
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ2345",          # ayraçsız
    "ABCDE-FGHIJ-KLMN0-PQRST-UVWXY-Z2345",     # O yerine sıfır yazılmış
    "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY-Z2345",     # kanonik
])
def test_yazim_varyantlari_ayni_koda_normallesir(varyant):
    """Operatör kodu kâğıttan okurken tire/boşluk/küçük harf/0-O karıştırır; hepsi
    aynı anahtarı türetmeli — yoksa kurtarma anında 'kod yanlış' denip veri kaybedilir."""
    assert br.normalize_code(varyant) == "ABCDEFGHIJKLMNOPQRSTUVWXYZ2345"


# ── Zarf ─────────────────────────────────────────────────────────────────────

_KEYS = {"sqlcipher_key": "s3cr3t-sqlcipher-anahtari-xyz", "patient_fernet_key": "p4t13nt-fernet-key"}


def test_zarf_dogru_kodla_acilir():
    kod = br.generate_recovery_code()
    assert br.open_envelope(kod, br.build_envelope(kod, _KEYS)) == _KEYS


def test_zarf_yazim_varyantiyla_da_acilir():
    kod = br.generate_recovery_code()
    blob = br.build_envelope(kod, _KEYS)
    bozuk_yazim = br.normalize_code(kod).lower().replace("O", "0")
    assert br.open_envelope(bozuk_yazim, blob) == _KEYS


def test_yanlis_kod_acmaz():
    blob = br.build_envelope(br.generate_recovery_code(), _KEYS)
    with pytest.raises(ValueError, match="YANLIS"):
        br.open_envelope(br.generate_recovery_code(), blob)


def test_zarf_anahtarlari_DUZ_METIN_ICERMEZ():
    """Zarf, yedek dizininde (NAS/USB) korumasız durur. Anahtar oradan düz okunabilseydi
    tüm şifreleme anlamsız olurdu."""
    kod = br.generate_recovery_code()
    blob = br.build_envelope(kod, _KEYS)
    for gizli in _KEYS.values():
        assert gizli.encode() not in blob
    # Kodun kendisi de (ve hash'i de) zarfa yazılmaz — çevrimdışı kaba kuvvet hedefi olmasın
    assert br.normalize_code(kod).encode() not in blob


def test_zarf_her_seferinde_farkli_tuz_kullanir():
    kod = br.generate_recovery_code()
    a = json.loads(br.build_envelope(kod, _KEYS))
    b = json.loads(br.build_envelope(kod, _KEYS))
    assert a["salt"] != b["salt"] and a["ct"] != b["ct"]


def test_bozuk_ve_yabanci_dosya_reddedilir():
    with pytest.raises(ValueError):
        br.open_envelope("ABCDE", b"bu json bile degil")
    with pytest.raises(ValueError, match="degil"):
        br.open_envelope("ABCDE", json.dumps({"tur": "baska-sey"}).encode())


def test_kdf_parametreleri_zarftan_okunur():
    """Parametreler ileride sertleşse bile ESKİ zarflar açılmaya devam etmeli —
    aksi halde bir sürüm yükseltmesi eski yedekleri kurtarılamaz yapar."""
    kod = br.generate_recovery_code()
    doc = json.loads(br.build_envelope(kod, _KEYS))
    assert doc["kdf"]["n"] == br._SCRYPT_N and doc["kdf"]["dklen"] == 32
    doc["kdf"]["n"] = 2 ** 15                       # parametreyi bozarsak açılmamalı
    with pytest.raises(ValueError):
        br.open_envelope(kod, json.dumps(doc).encode())


# ── Uçtan uca: yedek dizinine yazım ──────────────────────────────────────────

@pytest.fixture()
def izole_sirlar(tmp_path, monkeypatch):
    """Sır deposunu tmp'ye al — testin makinenin GERÇEK pemf_secrets.json'ına
    dokunmadığından emin ol (daha önce bir ajan gerçek dosyayı ACL'le kilitlemişti)."""
    from utils import secrets_manager as sm
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sm, "_CACHE", None, raising=False)
    store = {}

    def _get(key, default="", generate=True):
        # `generate` bayrağını GERÇEKTEN uygula: gerçek SecretsManager generate=True ile
        # yeni anahtar ÜRETİR. Stub bunu yok sayarsa "üretme yok" testi boş güvence verir
        # (mutasyon testi bu zayıflığı yakaladı).
        if key in store:
            return store[key]
        if generate:
            store[key] = f"URETILDI-{key}"
            return store[key]
        return default

    def _set(key, value):
        store[key] = value

    monkeypatch.setattr(sm, "get_secret", _get)
    monkeypatch.setattr(sm, "set_secret", _set)
    return store


def test_uctan_uca_zarf_yazilir_ve_acilir(tmp_path, izole_sirlar):
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"

    assert br.refresh_recovery_material(app, [yedek]) is True

    zarf = yedek / br.ENVELOPE_NAME
    assert zarf.exists()
    kod = izole_sirlar["backup_recovery_code"]
    assert br.open_envelope(kod, zarf.read_bytes()) == _KEYS

    # Kod dosyası YEREL veri dizinine yazılır (operatör buradan alıp dışarı taşır)
    assert (app / br.CODE_FILE_NAME).exists()
    assert br.format_code(kod) in (app / br.CODE_FILE_NAME).read_text(encoding="utf-8")


def test_KOD_YEDEK_DIZININE_ASLA_YAZILMAZ(tmp_path, izole_sirlar):
    """EN KRİTİK DAVRANIŞ: kod ve zarf aynı dizindeyse zarfın koruması SIFIRDIR.
    Yedek dizini NAS/USB'ye kopyalanır; kod oraya sızarsa yedeği çalan her şeyi açar."""
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"
    br.refresh_recovery_material(app, [yedek])

    kod_norm = br.normalize_code(izole_sirlar["backup_recovery_code"])
    for p in yedek.rglob("*"):
        if p.is_file():
            veri = p.read_bytes()
            assert kod_norm.encode() not in veri, f"KURTARMA KODU yedek dizinine sizdi: {p.name}"
            assert br.CODE_FILE_NAME.encode() not in p.name.encode()


def test_sifreleme_kapaliysa_zarf_YAZILMAZ_ve_anahtar_URETILMEZ(tmp_path, izole_sirlar):
    """sqlcipher_key yoksa at-rest şifreleme kapalıdır. Burada anahtar ÜRETMEK,
    şifrelemeyi kazara açıp mevcut düz-metin DB'yi okunamaz yapardı."""
    izole_sirlar.clear()
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"

    assert br.refresh_recovery_material(app, [yedek]) is False
    assert not (yedek / br.ENVELOPE_NAME).exists()
    assert "sqlcipher_key" not in izole_sirlar, "kurtarma yolu sqlcipher_key URETTI (şifrelemeyi kazara açar)"
    assert "backup_recovery_code" not in izole_sirlar


def test_anahtar_degismediyse_zarf_yeniden_yazilmaz(tmp_path, izole_sirlar):
    """Operatörün doğruladığı zarf her gün değişip şüphe uyandırmasın."""
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"

    br.refresh_recovery_material(app, [yedek])
    ilk = (yedek / br.ENVELOPE_NAME).read_bytes()
    br.refresh_recovery_material(app, [yedek])
    assert (yedek / br.ENVELOPE_NAME).read_bytes() == ilk, "zarf gereksiz yere yeniden yazıldı"


def test_anahtar_degisince_zarf_YENILENIR(tmp_path, izole_sirlar):
    """Re-key sonrası zarf eski anahtarı taşımaya devam ederse kurtarma SESSİZCE bozulur."""
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"
    br.refresh_recovery_material(app, [yedek])

    izole_sirlar["sqlcipher_key"] = "YENI-anahtar-rekey-sonrasi"
    br.refresh_recovery_material(app, [yedek])

    kod = izole_sirlar["backup_recovery_code"]
    acilan = br.open_envelope(kod, (yedek / br.ENVELOPE_NAME).read_bytes())
    assert acilan["sqlcipher_key"] == "YENI-anahtar-rekey-sonrasi"


def test_zarf_silinirse_geri_yazilir(tmp_path, izole_sirlar):
    """Parmak izi 'değişmedi' dese bile eksik zarf tamamlanmalı (yeni off-site hedefi)."""
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "backups"
    br.refresh_recovery_material(app, [yedek])
    (yedek / br.ENVELOPE_NAME).unlink()

    assert br.refresh_recovery_material(app, [yedek]) is True
    assert (yedek / br.ENVELOPE_NAME).exists()


def test_kod_kalicidir_her_yedekte_degismez(tmp_path, izole_sirlar):
    """Kod her yedekte yenilenseydi operatörün kasadaki kopyası GEÇERSİZ olurdu."""
    izole_sirlar.update(_KEYS)
    app = tmp_path / "app"
    app.mkdir()
    br.refresh_recovery_material(app, [tmp_path / "b1"])
    k1 = izole_sirlar["backup_recovery_code"]
    br.refresh_recovery_material(app, [tmp_path / "b2"])
    assert izole_sirlar["backup_recovery_code"] == k1

    # ...ve ESKİ zarf hâlâ aynı kodla açılmalı
    assert br.open_envelope(k1, (tmp_path / "b1" / br.ENVELOPE_NAME).read_bytes()) == _KEYS
