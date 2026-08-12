# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI GERÇEKTEN KOŞUYOR MU (2026-08-09 denetimi, Tier 1).

ARIZA: iş akışları vardı ama pratikte HİÇ çalışmıyordu.
  • tetikleyici yalnız `main, master` idi; geliştirme AKTİF DALDA yapıldığı için hiçbir
    değişiklikte koşmuyordu,
  • yalnız `ubuntu-latest` vardı; oysa ürün WINDOWS'ta çalışıyor ve launcher / ProgramData /
    DPAPI / güvenlik-duvarı yollarının tamamı Windows'a özgü,
  • `cargo test` yalnız `launcher-v*` TAG'inde koşuyordu — yani YAYINDAN SONRA,
  • arayüz için `tsc --noEmit` ve `jest` HİÇ koşmuyordu.
Sonuç: 700+ test değişiklik anında çalışmıyordu; regresyonlar ancak elle koşturulunca görülüyordu.

⚠️ Bu dosya CI'ı ÇALIŞTIRMAZ; iş akışı TANIMININ kapsamını kilitler. Bir iş sessizce
düşerse (ör. biri `matrix`i kaldırır ya da jest adımını siler) burası kırılır.
"""

import subprocess
from pathlib import Path

import pytest

W = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _yukle(ad):
    yaml = pytest.importorskip("yaml", reason="pyyaml yok — iş akışı şeması kontrol edilemiyor")
    return yaml.safe_load((W / ad).read_text(encoding="utf-8"))


def _tetikleyici(d):
    """PyYAML `on:` anahtarını Python `True`'ya çevirir (YAML 1.1 boolean) — ikisini de dene."""
    return d.get("on") or d.get(True)


AKTIF_DAL = "production-hardening"


# ── tetikleyici ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml"])
def test_KRITIK_aktif_dal_TETIKLENIR(dosya):
    """Aktif dal listede yoksa iş akışı sahadaki hiçbir değişiklikte koşmaz — yani YOK demektir."""
    dallar = _tetikleyici(_yukle(dosya))["push"]["branches"]
    assert AKTIF_DAL in dallar, f"{dosya} aktif dalda ({AKTIF_DAL}) KOSMUYOR: {dallar}"


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml"])
def test_pull_request_de_tetikler(dosya):
    assert "pull_request" in _tetikleyici(_yukle(dosya))


# ── kapsam: hangi işler var ──────────────────────────────────────────────────


#: `tests.yml`in kapsaması BEKLENEN işler — TAM küme (alt-küme değil).
#: ⚠️ 2026-08-12: eskiden `{"backend","launcher","frontend","site"}` bekleniyordu. Ama `pf/`
#: (Expo mobil) ve `pemf-vet-web/` (kendi git deposu) BU DEPODA İZLENMEZ — `git ls-files`
#: ikisinde de 0 döner. O işler checkout sonrası var olmayan dizinlerde `npm ci` çalıştırdığı
#: için HİÇBİR ZAMAN geçemezdi ve hattı 16/16 kırmızı tutan sebeplerdendi; kaldırıldılar.
#: Kapsam sorusu ölmedi, `test_arayuz_ve_site_BU_DEPODA_DEGIL` ile canlı tutuluyor.
BEKLENEN_ISLER = {"backend", "launcher", "sir-taramasi"}


def test_KRITIK_tum_isler_TANIMLI():
    """Kritik yol işleri; biri düşerse o katman test edilmez. TAM eşitlik aranır: hem sessiz
    KAYBOLMA hem de belgelenmemiş EKLEME burada görünür."""
    isler = set(_yukle("tests.yml")["jobs"])
    assert isler == BEKLENEN_ISLER, (
        f"tests.yml is kumesi degisti — beklenen {sorted(BEKLENEN_ISLER)}, bulunan {sorted(isler)}. "
        "Bilerek degistiyse BEKLENEN_ISLER'i gerekcesiyle guncelle."
    )


def test_KRITIK_backend_WINDOWSTA_da_kosar():
    """Ürün Windows'ta çalışıyor: ProgramData veri kökü, DPAPI, güvenlik duvarı, dosya kilitleri.
    Yalnız ubuntu'da koşan bir takım bu yolların hiçbirini görmez."""
    os_listesi = _yukle("tests.yml")["jobs"]["backend"]["strategy"]["matrix"]["os"]
    assert any("windows" in o for o in os_listesi), f"windows matrixte yok: {os_listesi}"
    assert any("ubuntu" in o for o in os_listesi), f"linux matrixte yok: {os_listesi}"


def test_matrix_fail_fast_KAPALI():
    """Bir platformun düşmesi diğerinin sonucunu gizlememeli."""
    assert _yukle("tests.yml")["jobs"]["backend"]["strategy"]["fail-fast"] is False


def test_KRITIK_launcher_WINDOWSTA_derlenir():
    """Launcher'ın Windows'a özgü yolları (DPAPI, icacls, NSIS kancaları) yalnız orada derlenir."""
    assert "windows" in _yukle("tests.yml")["jobs"]["launcher"]["runs-on"]


def _adimlar(is_adi, dosya="tests.yml"):
    return " ".join(
        str(a.get("run", "")) + " " + str(a.get("uses", "")) for a in _yukle(dosya)["jobs"][is_adi]["steps"]
    )


def test_KRITIK_launcher_ENTEGRASYON_testlerini_de_kosar():
    """`--all-targets` olmadan `core/tests/real_artifacts.rs` KOŞMAZ — üretim manifest'inin
    şema/URL/platform değişmezlerini doğrulayan asıl kapı orasıdır."""
    assert "--all-targets" in _adimlar("launcher")


@pytest.mark.parametrize("dizin", ["pf", "pemf-vet-web"])
def test_arayuz_ve_site_BU_DEPODA_DEGIL(dizin):
    """Arayüz (`pf`) ve site (`pemf-vet-web`) CI işleri 2026-08-12'de KALDIRILDI; gerekçe:
    ikisi de bu depoda izlenmez, dolayısıyla o işler temiz checkout'ta asla koşamazdı.

    ⚠️ Bu test kaldırılan kapının YERİNE geçer ve gerekçeyi CANLI tutar: dizinlerden biri bir
    gün gerçekten depoya alınırsa varsayım çöker ve burası kırılır — o an `tests.yml`ye
    `tsc --noEmit` + `jest` / `npm run build` işleri GERİ EKLENMELİDİR. Aksi hâlde kapsam
    kaybı sessiz olurdu: kimse kaldırılmış bir işin geri gelmesi gerektiğini hatırlamaz.
    (Kaldırma kapsamı yok etmedi; kontroller kendi depolarında yapılır.)
    """
    kok = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(["git", "ls-files", dizin], cwd=str(kok), capture_output=True, text=True, timeout=30)
    except Exception as e:  # git yoksa varsayım doğrulanamaz
        pytest.skip(f"git calistirilamadi: {type(e).__name__}: {e}")
    if r.returncode != 0:
        pytest.skip(f"git ls-files basarisiz (rc={r.returncode})")
    assert not r.stdout.strip(), (
        f"'{dizin}/' ARTIK DEPODA IZLENIYOR → tests.yml'den kaldirilan CI isi GERI EKLENMELI "
        "(tip kontrolu + test/build). Bkz. tests.yml sonundaki 'KALDIRILDI (2026-08-12)' notu."
    )


def test_backend_pytest_kosar():
    assert "pytest tests" in _adimlar("backend")


# ── SIR TARAMASI (2026-08-09 denetimi, Tier 3) ──────────────────────────────
# `.pre-commit-config.yaml` gitleaks hook'unu TANIMLIYORDU ama `pre-commit install` hiç
# çalıştırılmamıştı (`.git/hooks` boştu) → kapı bir kez bile açılmadı. Depo PUBLIC ve geçmişinde
# canlı sır bulunmuş bir depo. Hook yalnız onu kuran kişiyi korur; CI işi herkesi korur.


def test_KRITIK_gitleaks_CIDA_kosar():
    isler = _yukle("tests.yml")["jobs"]
    hepsi = " ".join(_adimlar(i) for i in isler)
    assert "gitleaks" in hepsi.lower(), "hicbir CI isi sir taramasi yapmiyor"


def test_KRITIK_gitleaks_isi_BLOKLAYICI():
    """`continue-on-error: true` bir sır kapısını dekorasyona çevirir."""
    isler = _yukle("tests.yml")["jobs"]
    for ad, is_ in isler.items():
        adimlar = is_.get("steps", [])
        if not any("gitleaks" in str(a.get("uses", "")).lower() for a in adimlar):
            continue
        assert is_.get("continue-on-error") is not True, f"{ad} isi bloklamiyor"
        for a in adimlar:
            if "gitleaks" in str(a.get("uses", "")).lower():
                assert a.get("continue-on-error") is not True, f"{ad}/gitleaks adimi bloklamiyor"
        return
    pytest.fail("gitleaks adimi bulunamadi")


def test_gitleaks_GECMISI_de_tarar():
    """`fetch-depth` varsayılanı 1'dir: yalnız son commit iner. Sır bir önceki commit'te
    girdiyse tarama onu HİÇ görmez — bu deponun somut geçmişi tam olarak budur."""
    for is_ in _yukle("tests.yml")["jobs"].values():
        adimlar = is_.get("steps", [])
        if not any("gitleaks" in str(a.get("uses", "")).lower() for a in adimlar):
            continue
        checkout = next((a for a in adimlar if "actions/checkout" in str(a.get("uses", ""))), None)
        assert checkout, "gitleaks isinde checkout yok"
        assert str((checkout.get("with") or {}).get("fetch-depth")) == "0", (
            "gitleaks yalniz son commit'i tariyor — gecmisteki sir gorunmez"
        )
        return


def test_pre_commit_YAPILANDIRMASI_gitleaks_iceriyor():
    kok = Path(__file__).resolve().parent.parent
    cfg = (kok / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks" in cfg, "pre-commit yapilandirmasinda gitleaks yok"
    assert "detect-private-key" in cfg, "ozel anahtar kapisi yok"


def test_bootstrap_pre_commit_KURAR():
    """Yapılandırma kurulmadıkça hiçbir şey yapmaz; bootstrap kurulumu üstlenmeli."""
    kok = Path(__file__).resolve().parent.parent
    b = (kok / "bootstrap.ps1").read_text(encoding="utf-8", errors="replace")
    assert "pre_commit install" in b or "pre-commit install" in b, (
        "bootstrap.ps1 pre-commit hook'unu KURMUYOR — yeni makinede kapi kapali kalir"
    )


# ── en az yetki (regresyon kapısı) ───────────────────────────────────────────


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml", "launcher.yml"])
def test_permissions_SALT_OKUR(dosya):
    """Ele geçirilmiş bir bağımlılık/action, varsayılan token'la depoya YAZABİLİRDİ."""
    d = _yukle(dosya)
    assert d.get("permissions", {}).get("contents") == "read", f"{dosya} en-az-yetki degil"
