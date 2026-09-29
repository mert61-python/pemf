# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""URUN SENARYO TAKIMI kendi kapisi (2026-09-17).

`scripts/urun_senaryolari.py` sevk edilen EXE'yi calistirip olcer; CI'da EXE YOKTUR, bu
yuzden BU dosya senaryolari KOSTURMAZ. Koruduğu sey baska: takimin GUVENILIR kalmasi.

⚠️ NEDEN GEREKLI. Bir olcum takimi sessizce degersizlesebilir ve bunu kimse fark etmez:

  1. Senaryolar TEKER TEKER silinir -> "hepsi gecti" yazar, ama geriye uc senaryo kalmistir.
  2. KARSIT-KANIT senaryolari atilir -> geri kalan her sey BEDAVAYA yesillenir. Somut ornek:
     C1-C4 "jeton zorlamasi acikken E-stop kapilanmiyor" der. Jeton kapisi HIC calismiyor
     olsaydi da ayni yesili verirlerdi. C0 (kapi ucretli analizi GERCEKTEN 402 ile reddediyor)
     olmadan o dort senaryo bir sey kanitlamaz. Ayni sekilde A1'in "sifreli" iddiasi A0
     olmadan, B9b'nin "uydurmuyor" iddiasi C9 olmadan havada kalir.
  3. BAYAT IKILI nobeti dusurulur -> eski bir EXE olculur ve rapor "urun dogru" der. Bu tuzaga
     bu depoda saatler harcandi (bkz. build'in sahte cikis kodu olayi).
  4. Senaryo KODLARI cakisir -> rapor iki farkli seyi ayni kodla basar; ozet satirinda hangisinin
     dustugu anlasilmaz. (Ilk yazimda C0/C5/C7 hem hata yolunda hem gercek senaryoda
     kullaniliyordu; bu kapi yazilirken yakalandi.)
  5. Sabit kullanici yolu kalir -> baska makinede kosmaz, yani bir daha KOSULMAZ.

Bu kapilarin her biri MUTASYONLA kirmizi gorulmustur (2026-09-17).
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "urun_senaryolari.py"

#: ⚠️ BU SAYAC BIR KEZ ISIRMADI. Ilk yazimda 48'di ama TUM `kayit(...)` cagrilarini sayiyordu;
#: oysa besi OLCUM DEGIL, "backend acilamadi" hata yolu. Gercek senaryo 48, toplam kod 53 ->
#: bir senaryo silindiginde 52 kaliyor ve kapi YESIL doniyordu. Mutasyon yakaladi (2026-09-17).
#: Ders: sayac ankraji, saydigi seyin TANIMIYLA birlikte yazilir.
HATA_YOLU_KODLARI = {"B0", "C-ACILIS1", "C-ACILIS2", "C-ACILIS3", "D0"}

#: 2026-09-17 olcumunde 48 GERCEK senaryo vardi. Eklemek serbest, silmek KIRMIZI.
#: (Depodaki rota-sozlesmesi kapisiyla ayni desen — "sessiz kuculme" en sinsi gerilemedir.)
ASGARI_SENARYO = 48

#: Bunlar olmadan geri kalan senaryolar BEDAVAYA yesillenir.
KARSIT_KANIT_KODLARI = {
    "A0",  # sifreleme KAPALIYKEN saglik ucu "sifreli" DEMEMELI
    "B9b",  # launcher'siz acilista buildId UYDURULMAMALI
    "C0",  # jeton kapisi ucretli analizi GERCEKTEN reddedebilmeli
    "C9",  # ...ve sha gecildiginde buildId'yi RAPORLAYABILMELI
}


def _agac() -> ast.Module:
    return ast.parse(BETIK.read_text(encoding="utf-8"))


def _senaryo_kodlari() -> list[str]:
    """`kayit("KOD", ...)` cagrilarinin BIRINCI argumani — metinden degil AST'den."""
    kodlar = []
    for n in ast.walk(_agac()):
        if not isinstance(n, ast.Call):
            continue
        ad = getattr(n.func, "id", getattr(n.func, "attr", None))
        if ad != "kayit" or not n.args:
            continue
        ilk = n.args[0]
        if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
            kodlar.append(ilk.value)
    return kodlar


def test_KRITIK_betik_yerinde():
    assert BETIK.exists(), (
        "scripts/urun_senaryolari.py YOK -> urun-seviyesi dogrulama kayboldu. Suit yesilken "
        "urunun hasta gecmisini kaybettigi 2026-09-13 sinifi bir daha olculemez."
    )


def test_KRITIK_senaryo_sayisi_SESSIZCE_KUCULMEDI():
    olculen = set(_senaryo_kodlari()) - HATA_YOLU_KODLARI
    assert len(olculen) >= ASGARI_SENARYO, (
        f"OLCUM senaryosu sayisi {len(olculen)} — beklenen en az {ASGARI_SENARYO}. Takim "
        "kucultulduyse bu SABIT de bilincli olarak dusurulmeli; sessiz kuculme raporun anlamini "
        "bozar. (Hata-yolu kodlari sayilmaz: onlar olcum degil, 'backend acilamadi' dallari.)"
    )


def test_KRITIK_KARSIT_KANIT_senaryolari_DURUYOR():
    """⚠️ Bu kapinin isi: "hepsi gecti" cumlesini anlamli tutmak."""
    kodlar = set(_senaryo_kodlari())
    eksik = sorted(KARSIT_KANIT_KODLARI - kodlar)
    assert not eksik, (
        f"karsit-kanit senaryolari KAYBOLMUS: {eksik}. Bunlar olmadan olculen ozellik KAPALI olsa "
        "bile takim YESIL doner (or. jeton kapisi hic calismazken 'E-stop kapilanmiyor' demek)."
    )


def test_KRITIK_senaryo_kodlari_BENZERSIZ():
    """Ayni kod iki farkli olcumde kullanilirsa ozet satiri hangisinin dustugunu SOYLEYEMEZ."""
    kodlar = _senaryo_kodlari()
    tekrar = sorted({k for k in kodlar if kodlar.count(k) > 1})
    assert not tekrar, (
        f"senaryo kodu TEKRARLANIYOR: {tekrar}. Ilk yazimda C0/C5/C7 hem 'backend acilamadi' hata "
        "yolunda hem gercek senaryoda kullaniliyordu -> rapor iki ayri seyi ayni satirla basiyordu."
    )


def test_KRITIK_BAYAT_IKILI_nobeti_main_icinden_CAGRILIYOR():
    """⚠️ Fonksiyonun VAR OLMASI yetmez — cagrilmazsa eski EXE olculur ve rapor YALAN soyler.

    Capa `main` govdesindeki GERCEK cagriya pinli (metin aramasi docstring'e takilirdi:
    modul docstring'i zaten "BAYAT-IKILI NOBETI" diyor).
    """
    agac = _agac()
    main = next((n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    assert main is not None, "betikte `main` yok — giris noktasi degismis, kapi guncellenmeli"
    cagrilar = {getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(main) if isinstance(c, ast.Call)}
    assert "bayat_ikili_nobeti" in cagrilar, (
        "`main` artik bayat-ikili nobetini CAGIRMIYOR -> kaynaklardan eski bir EXE olculup "
        "'urun dogru' diye raporlanabilir. Bu tuzaga bu depoda daha once saatler harcandi."
    )


def test_KRITIK_nobet_BAYATSA_DURUYOR():
    """Nobet 'uyarip devam' etmemeli: olcum gecersizse KOSMAMALI."""
    agac = _agac()
    fn = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "bayat_ikili_nobeti"),
        None,
    )
    assert fn is not None, "bayat_ikili_nobeti fonksiyonu YOK"

    # ⚠️ `any(Raise in fn)` YETMEZ — MUTASYONLA olculdu (2026-09-17): fonksiyonda AYRICA
    # "EXE yok" dali da firlatiyor, bu yuzden BAYATLIK dalindaki `raise`i `print`e cevirmek
    # kapiyi YESIL birakiyordu. Capa, `bayat` listesini denetleyen DALIN KENDISINE pinli.
    bayat_dali = next(
        (
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.If) and any(isinstance(x, ast.Name) and x.id == "bayat" for x in ast.walk(n.test))
        ),
        None,
    )
    assert bayat_dali is not None, (
        "nobette `bayat` listesini denetleyen dal YOK -> kaynak/EXE zaman karsilastirmasi kalkmis"
    )
    assert any(isinstance(n, ast.Raise) for n in bayat_dali.body), (
        "bayat EXE bulundugunda artik FIRLATILMIYOR -> betik yalnizca uyarip olcmeye devam eder; "
        "urettigi rapor GECERSIZ olur ama GECERLI gorunur. Bu tuzaga bu depoda saatler harcandi."
    )


def test_KARSIT_KANIT_betikte_SABIT_kullanici_yolu_YOK():
    """Sabit yol kalirsa betik baska makinede kosmaz -> bir daha HIC kosulmaz."""
    metin = BETIK.read_text(encoding="utf-8")
    for kotu in ("C:\\Users\\", "C:/Users/"):
        assert kotu not in metin, (
            f"betikte sabit kullanici yolu var ({kotu!r}) -> yalniz yazildigi makinede kosar. "
            "EXE yolu --exe / PEMF_EXE / depo-ici varsayilan uzerinden cozulmeli."
        )


def test_KARSIT_KANIT_calisma_alani_DEPO_AGACINDA_DEGIL():
    """Senaryolar ACL-kilitli ve bozuk dosyalar uretir; bunlar depoya sizmamali."""
    agac = _agac()
    for n in ast.walk(agac):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CALISMA" for t in n.targets):
            kaynak = ast.unparse(n.value)
            assert "gettempdir" in kaynak, (
                f"CALISMA alani gecici dizinde DEGIL ({kaynak}) -> ACL-kilitli dosyalar ve bozuk "
                "sir dosyalari depo agacinda kalir."
            )
            return
    raise AssertionError("CALISMA atamasi bulunamadi — kapi bayatlamis")


# ── D0Ö.09 (B-10.31 · B-10.77) — EXE ortamı ve anahtar deposu denetimi ────────────────────────────
# ⚠️ Bu kapılar da EXE BAŞLATMAZ ve GERÇEK kasayı OKUMAZ: Popen, kasa özeti ve cmdkey alt süreci sahtedir.

#: Dış ortamda (sahibin kabuğu) bulunabilecek, GERÇEK kaynaklara işaret eden değişkenler (nöbetçi değerler).
#: D0Ö.09 ek (tur 3): `kostur` bunları MİRAS ALMAMALI — PEMF_BACKUP_DIR kurtarma zarfını gerçek off-site
#: dizine yazdırır, PEMF_MQTT_CLOUD_* E-stop'u gerçek broker'a aynalar.
_MIRAS_NOBETCILERI = {
    "PEMF_BACKUP_DIR": "GERCEK_offsite_yedek",
    "PEMF_MQTT_CLOUD_HOST": "gercek-broker.invalid",
    "PEMF_SENTRY_DSN": "https://gercek@sentry.invalid/1",
    "PEMF_KEEP_PLAIN_BACKUP": "1",
    "SUPABASE_KEY": "gercek-anahtar",
}


def _guvenli_exe_ortami_mi(env: dict, kok: Path) -> list[str]:
    """kostur'un EXE'ye verdiği ortamın güvenlik ihlalleri (boş liste = güvenli)."""
    from urllib.parse import urlparse

    ihlal = []
    for ad in ("PEMF_DEVICE_IDENTITY_DIR", "PROGRAMDATA"):
        deger = env.get(ad, "")
        if not (deger and "GERCEK_" not in deger and Path(deger).resolve().is_relative_to(kok.resolve())):
            ihlal.append(f"{ad}={deger!r} (gerçek makine cihaz sırrı — B-10.31)")
    for ad, beklenen in (
        ("PEMF_FW_AUTO_UPDATE", "0"),
        ("PEMF_HOTSPOT", "0"),
        ("PEMF_CLOUD_PATIENT_SYNC", "0"),
        ("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring"),
    ):
        if env.get(ad) != beklenen:
            ihlal.append(f"{ad}={env.get(ad)!r} (beklenen {beklenen!r})")
    if urlparse(env.get("SUPABASE_URL", "")).hostname not in ("127.0.0.1", "localhost", "::1"):
        ihlal.append(f"SUPABASE_URL={env.get('SUPABASE_URL')!r} (canlı Supabase'e cihaz kaydı/TOFU mührü)")
    saglama = env.get("PEMF_CLOUD_PROVISION_PATH", "")
    if not (saglama and Path(saglama).resolve().is_relative_to(kok.resolve()) and not Path(saglama).exists()):
        ihlal.append(f"PEMF_CLOUD_PROVISION_PATH={saglama!r} (E-stop bulut aynası GERÇEK broker'a STOP yayınlar)")
    return ihlal


def test_KRITIK_EXE_ortami_cihaz_kimligi_ve_ProgramData_SCRATCH_fw_ve_hotspot_KAPALI(tmp_path, monkeypatch):
    """B-10.31: 21 EXE açılışı GERÇEK ProgramData cihaz sırrını (`PEMF_System/device_identity.json`) yazıyor ya
    da okuyordu; oto-firmware ve hotspot açılışta koşulsuz başlıyordu. `kostur` EXE'ye kimlik deposunu ve
    ProgramData'yı scratch altında, oto-firmware ve hotspot'u KAPALI vermeli. EK (tur 3): bulut kara-delik
    (Supabase + provizyonsuz E-stop aynası), hasta senkronu kapalı, null kasa; dış ortamdan PEMF_*/SUPABASE_*
    MİRAS YOK."""
    from exe_kapisi_surucusu import kostur_ortami

    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "GERCEK_PROGRAMDATA"))
    for ad, deger in _MIRAS_NOBETCILERI.items():
        monkeypatch.setenv(ad, str(tmp_path / deger) if deger.startswith("GERCEK_") else deger)
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    # Koşucu/conftest dış ortamda null arka uç verir → kostur onu MİRAS alıp kapıyı maskelerdi (ölçüldü).
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.Windows.WinVaultKeyring")
    env = kostur_ortami(tmp_path, monkeypatch)
    ihlal = _guvenli_exe_ortami_mi(env, tmp_path)
    assert not ihlal, f"urun_senaryolari EXE'si gerçek sisteme dokunabilir: {ihlal}"
    sizan = {ad: env[ad] for ad in _MIRAS_NOBETCILERI if ad in env}
    assert not sizan, f"urun_senaryolari EXE'si dış ortamın GERÇEK kaynak değişkenlerini MİRAS aldı: {sizan}"


def test_KRITIK_kostur_ek_sozlugu_KIMLIK_ve_BULUT_yalitimini_EZEMEZ(tmp_path, monkeypatch):
    """`kostur(ek=...)` güvenlik anahtarlarını SESSİZCE ezmemeli (D0Ö.03 ekinin FW/STM kolunun eşi)."""
    import exe_kapisi_surucusu as ks

    yakalanan = {}

    class _SahteSurec:
        def __init__(self, argv, env=None, **kw):
            yakalanan["env"] = {k.upper(): v for k, v in (env or {}).items()}

        def poll(self):
            return 0

    for ad in ks.YALITIM_DEGISKENLERI:
        monkeypatch.delenv(ad, raising=False)
    us = ks.urun_senaryolari_modulu()
    monkeypatch.setattr(us, "subprocess", ks.AltSurecVekili(Popen=_SahteSurec))
    (tmp_path / "calisma").mkdir()
    monkeypatch.setattr(us, "CALISMA", tmp_path / "calisma")
    ek = {
        "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "GERCEK_kimlik"),
        "SUPABASE_URL": "https://gercek.supabase.co",
        "PYTHON_KEYRING_BACKEND": "keyring.backends.Windows.WinVaultKeyring",
        "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "GERCEK_provizyon.json"),
    }
    us.kostur(tmp_path / "veri", sifreli=False, ek=ek, sure=1, saglik_bekle=False)
    ihlal = _guvenli_exe_ortami_mi(yakalanan["env"], tmp_path)
    assert not ihlal, f"kostur(ek=...) kimlik/bulut/kasa yalıtımını EZDİ: {ihlal}"


def _main_sahteli(tmp_path, monkeypatch):
    """`main()`i ölçümlerini koşturmadan çağırmak için: nöbet, tohum ve gruplar boş; SONUCLAR boş."""
    import sys

    from exe_kapisi_surucusu import urun_senaryolari_modulu

    us = urun_senaryolari_modulu()
    monkeypatch.setattr(us, "bayat_ikili_nobeti", lambda: None)
    monkeypatch.setattr(us, "CALISMA", tmp_path / "calisma")
    monkeypatch.setattr(us, "tohum_uret", lambda: True)
    for grup in ("grup_a", "grup_b", "grup_c", "grup_d"):
        monkeypatch.setattr(us, grup, lambda: None)
    monkeypatch.setattr(us, "SONUCLAR", [])
    monkeypatch.setattr(sys, "argv", ["urun_senaryolari.py", "B"])
    return us


def test_KRITIK_anahtar_deposu_DEGISTIYSE_cikis_SIFIR_DEGIL(tmp_path, monkeypatch):
    """B-10.77: izolasyon denetimi kaydın EZİLMESİNİ göremiyordu (yalnız SAYI karşılaştırıyordu) ve
    'DEGISTI' dese bile exit 0 dönüyordu. Aynı SAYIDA ama DEĞERİ değişmiş kasa sahtelenir → main() 1."""
    from exe_kapisi_surucusu import AltSurecVekili

    us = _main_sahteli(tmp_path, monkeypatch)
    ozetler = iter([(2, "once-ozeti"), (2, "sonra-ozeti")])  # aynı SAYI, farklı DEĞER (bir kayıt ezildi)
    monkeypatch.setattr(us, "_anahtar_deposu_ozeti", lambda: next(ozetler))

    class _AyniSayi:  # eski kod yolu (powershell cmdkey | say) — gerçek kasa LİSTELENMEZ
        stdout, stderr, returncode = "2\n", "", 0

    monkeypatch.setattr(us, "subprocess", AltSurecVekili(run=lambda *a, **k: _AyniSayi()))
    assert us.main() == 1, "anahtar deposu kaydı EZİLDİ (aynı sayı, farklı değer) ama betik exit 0 döndü (B-10.77)"


def test_KARSIT_KANIT_anahtar_deposu_DEGISMEDIYSE_cikis_SIFIR(tmp_path, monkeypatch):
    """Karşıt-kanıt: kasa değişmediyse (ve senaryo yoksa) main() 0 — kapı her durumda 1 döndürmüyor."""
    from exe_kapisi_surucusu import AltSurecVekili

    us = _main_sahteli(tmp_path, monkeypatch)
    monkeypatch.setattr(us, "_anahtar_deposu_ozeti", lambda: (2, "ayni-ozet"))

    class _AyniSayi:
        stdout, stderr, returncode = "2\n", "", 0

    monkeypatch.setattr(us, "subprocess", AltSurecVekili(run=lambda *a, **k: _AyniSayi()))
    assert us.main() == 0


_LISTE = (
    "Currently stored credentials:\n\n"
    "    Target: LegacyGeneric:target=PEMF_GUI\n    Type: Generic\n    User: master_secret\n\n"
    "    Target: LegacyGeneric:target=sqlcipher_key@PEMF_GUI\n    Type: Generic\n    User: sqlcipher_key\n\n"
    "    Target: LegacyGeneric:target=patient_fernet_key@PEMF_GUI\n    Type: Generic\n\n"
    "    Target: LegacyGeneric:target=PEMF_GATE_SYS_1a2b@PEMF_GUI\n    Type: Generic\n\n"
    "    Hedef: LegacyGeneric:target=baska-uygulama\n    Type: Generic\n"
)


class _Liste:
    stdout, stderr, returncode = _LISTE, "", 0


class _Dustu:
    stdout, stderr, returncode = "", "Erişim reddedildi.", 1


def test_KRITIK_anahtar_deposu_ozeti_EZILMIS_kaydi_GORUR(monkeypatch):
    """`_anahtar_deposu_ozeti` (sayı, özet) döndürür; aynı sayıda ama DEĞERİ değişmiş kayıt özeti DEĞİŞTİRİR.
    Yalnız ürünün kayıtları okunur: düz `PEMF_GUI` ve `<kullanıcı>@PEMF_GUI` (süitin geçici `PEMF_GATE_*`
    kayıtları ve başka uygulamalar HARİÇ). cmdkey listesi ve CredRead SAHTEDİR — gerçek kasa okunmaz."""
    from exe_kapisi_surucusu import AltSurecVekili, urun_senaryolari_modulu

    us = urun_senaryolari_modulu()
    monkeypatch.setattr(us, "subprocess", AltSurecVekili(run=lambda *a, **k: _Liste()))
    kasa = {"PEMF_GUI": b"M", "sqlcipher_key@PEMF_GUI": b"A", "patient_fernet_key@PEMF_GUI": b"B"}
    okunan = []

    class _SahteCred:
        CRED_TYPE_GENERIC = 1

        @staticmethod
        def CredRead(Type=None, TargetName=None, Flags=0):
            okunan.append(TargetName)
            return {"TargetName": TargetName, "CredentialBlob": kasa[TargetName]}

    monkeypatch.setattr(us, "_kasa_modulu", lambda: _SahteCred)
    sayi1, ozet1 = us._anahtar_deposu_ozeti()
    kasa["sqlcipher_key@PEMF_GUI"] = b"EZILDI"
    sayi2, ozet2 = us._anahtar_deposu_ozeti()
    assert sayi1 == sayi2 == 3, (sayi1, sayi2)
    assert ozet1 != ozet2, "aynı sayıda ama DEĞERİ değişmiş kayıt özeti DEĞİŞTİRMEDİ — ezilme görünmez"
    assert set(okunan) == set(kasa), f"okunan kayıtlar ürünün kayıtları değil: {sorted(set(okunan))}"


def test_KRITIK_anahtar_deposu_OLCULEMEZSE_cikis_SIFIR_DEGIL(tmp_path, monkeypatch):
    """B-10.77'nin 3. bileşeni: ölçüm düştüğünde (cmdkey hata döner ya da kasa API'si yoksa) iki taraf da
    'boş' görünüp DEGISMEDI deniyordu. Ölçülemeyen kasa TEMİZ SAYILMAZ → main() 1."""
    from exe_kapisi_surucusu import AltSurecVekili

    us = _main_sahteli(tmp_path, monkeypatch)
    monkeypatch.setattr(us, "subprocess", AltSurecVekili(run=lambda *a, **k: _Dustu()))
    assert us.main() == 1, "cmdkey düştü (ölçüm YOK) ama betik exit 0 döndü — 'ölçülemedi' 'değişmedi' sayıldı"

    us = _main_sahteli(tmp_path, monkeypatch)
    monkeypatch.setattr(us, "subprocess", AltSurecVekili(run=lambda *a, **k: _Liste()))
    monkeypatch.setattr(us, "_kasa_modulu", lambda: None)
    assert us.main() == 1, "kasa API'si yok (değerler okunamadı) ama betik exit 0 döndü"
