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

import re
import subprocess
from pathlib import Path

import capraz
import pytest

W = Path(__file__).resolve().parent.parent / ".github" / "workflows"
KOK = W.parent.parent


def _yukle(ad):
    yaml = capraz.paket_yoksa_atla("yaml", sebep="pyyaml yok — iş akışı şeması kontrol edilemiyor")
    return yaml.safe_load((W / ad).read_text(encoding="utf-8"))


def test_KRITIK_security_yml_torch_CVE_GORUNURLUK_iddiasi_GERCEK_D6_56():
    """Tur 2 kolu (D67 çürütme, mutant e4): torch tekerlekleri PyPI'da YOK (`+cpu`, ek index) → pip-audit onları ATLAR; iş akışı
    yorumu torch CVE'lerinin bu adımda GÖRÜNDÜĞÜNÜ söylemez, GÖRÜNMEDİĞİNİ söyler; "bloklayıcı yapma" tarifi `|| true`'yu da anar."""
    req = (KOK / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^torch==[\d.]+\+cpu", req, re.M) and "--extra-index-url" in req, (
        "ölçüt değişti: torch artık PyPI'dan geliyor olabilir — security.yml torch CVE yorumu yeniden ölçülmeli"
    )
    sec = (W / "security.yml").read_text(encoding="utf-8")
    yorum = " ".join(s.strip().lstrip("#").strip() for s in sec.splitlines() if s.strip().startswith("#"))
    assert not re.search(r"(?i)\b(?:burada|adımda) GÖRÜNÜR", yorum), (
        "security.yml torch CVE'lerinin pip-audit'te GÖRÜNDÜĞÜNÜ söylüyor"
    )
    assert re.search(r"torch CVE'leri[^.]*GÖRÜNMEZ", yorum), (
        "security.yml torch CVE'lerinin bu adımda GÖRÜNMEDİĞİNİ söylemiyor"
    )
    assert "|| true" in sec and "continue-on-error'ı kaldırmakla OLMAZ" in yorum, (
        "bloklayıcı yapma tarifi `|| true`'yu anmıyor"
    )


def test_KRITIK_D5_32_PyYAML_CI_test_bagimliliklarinda_PINLI():
    """D5.32 (B-10.206): bu dosyanın TÜM iş akışı kapıları `_yukle` → `importorskip("yaml")` ile PyYAML'a bağlı. Pin
    `requirements-test.txt`ten düşerse CI'da hepsi SESSİZCE atlanır (adı konmuş tek kırmızı yoktu; yalnız ilgisiz bir testin
    TypeError'ı). Statik kapı: pin VAR ve TAM sürümle (`==`) — PyYAML'ı içe aktarmadan, dosyadan okunur."""
    gereksinim = (KOK / "requirements-test.txt").read_text(encoding="utf-8")
    satirlar = [s.split("#", 1)[0].strip() for s in gereksinim.splitlines()]
    pin = [s for s in satirlar if re.match(r"(?i)^pyyaml\s*==\s*\d+(\.\d+)*\s*$", s)]
    assert len(pin) == 1, (
        f"PyYAML requirements-test.txt'te TAM sürümle (==) pinli değil ({pin}) — CI iş akışı kapıları "
        "(`_yukle`) PyYAML olmadan SESSİZCE ATLANIR"
    )


def _tetikleyici(d):
    """PyYAML `on:` anahtarını Python `True`'ya çevirir (YAML 1.1 boolean) — ikisini de dene."""
    return d.get("on") or d.get(True)


#: ⚠️ 4-A inc. S-A2.1 (Y123 önerilen, 2026-10-11): aktif geliştirme dalı `duzeltme/dalga-2`; `production-hardening` yalnız
#: listede kalan eski dal. Push tetikleyicisi GitHub dal desenidir (`duzeltme/**`) — eşleşme düz üyelik değil desenle ölçülür.
AKTIF_DAL = "duzeltme/dalga-2"


def _dal_eslesir(dal: str, desen: str) -> bool:
    """GitHub `branches` deseni: `**` her karakteri (`/` dahil), `*` `/` dışındakileri eşler."""
    rx = re.escape(desen).replace(r"\*\*", "\0").replace(r"\*", "[^/]*").replace("\0", ".*")
    return re.fullmatch(rx, dal) is not None


# ── tetikleyici ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml", "frontend.yml", "site.yml"])
def test_KRITIK_aktif_dal_TETIKLENIR(dosya):
    """Aktif dal listede yoksa iş akışı sahadaki hiçbir değişiklikte koşmaz — yani YOK demektir."""
    dallar = _tetikleyici(_yukle(dosya))["push"]["branches"]
    assert any(_dal_eslesir(AKTIF_DAL, d) for d in dallar), f"{dosya} aktif dalda ({AKTIF_DAL}) KOSMUYOR: {dallar}"
    assert not _dal_eslesir("duzeltme/dalga-2", "duzeltme/*/x") and _dal_eslesir("feature/a/b", "feature/**"), (
        "desen ölçücüsü"
    )


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml"])
def test_pull_request_de_tetikler(dosya):
    assert "pull_request" in _tetikleyici(_yukle(dosya))


# ── kapsam: hangi işler var ──────────────────────────────────────────────────


#: `tests.yml`in kapsaması BEKLENEN işler — TAM küme (alt-küme değil).
#: ⚠️ 2026-08-12: eskiden `{"backend","launcher","frontend","site"}` bekleniyordu; `apps/ui/` ve
#: `apps/web/` o tarihte AYRI depolardaydi ve buradaki isler var olmayan dizinlerde `npm ci`
#: kosturdugu icin asla gecemezdi -> kaldirildilar.
#: ⚠️ 2026-08-18 MONOREPO: ikisi de artik depoda, ama isler `tests.yml`ye GERI EKLENMEDI —
#: KENDI yol-filtreli is akislarina konuldular (`frontend.yml`, `site.yml`). Sebep: `tests.yml`
#: filtresiz kosmali (capraz-katman kapilari icin), ama Expo/Vite hatlarinin her backend
#: degisikliginde kosmasi gereksiz. Kapsam `test_KRITIK_arayuz_ve_site_CI_KAPSAMINDA` ile kilitli.
BEKLENEN_ISLER = {"backend", "launcher", "sir-taramasi"}


def test_KRITIK_tum_isler_TANIMLI():
    """Kritik yol işleri; biri düşerse o katman test edilmez. TAM eşitlik aranır: hem sessiz
    KAYBOLMA hem de belgelenmemiş EKLEME burada görünür."""
    isler = set(_yukle("tests.yml")["jobs"])
    assert isler == BEKLENEN_ISLER, (
        f"tests.yml is kumesi degisti — beklenen {sorted(BEKLENEN_ISLER)}, bulunan {sorted(isler)}. "
        "Bilerek degistiyse BEKLENEN_ISLER'i gerekcesiyle guncelle."
    )


def test_KRITIK_backend_YALNIZ_WINDOWSTA_kosar_Y320():
    """Ürün Windows'ta çalışıyor: ProgramData veri kökü, DPAPI, güvenlik duvarı, dosya kilitleri.
    Yalnız ubuntu'da koşan bir takım bu yolların hiçbirini görmez. YS1b · Y320 (sahip 25-11): CI yalnız Windows ürün hattı —
    `ubuntu-latest` kopyası KALKTI (Linux / macOS paketleme kapsam dışı, Docker da silindi — Y317)."""
    os_listesi = _yukle("tests.yml")["jobs"]["backend"]["strategy"]["matrix"]["os"]
    assert os_listesi == ["windows-latest"], f"backend matrisi yalnız windows-latest olmalı (Y320): {os_listesi}"


#: Y320: Linux / macOS backend paketleme iş akışları KALDIRILDI (git geçmişinde kalır).
_Y320_KALDIRILAN = ("linux-backend.yml", "mac-backend.yml")


@pytest.mark.parametrize("ad", _Y320_KALDIRILAN)
def test_KRITIK_Y320_linux_mac_backend_paketleme_is_akisi_YOK(ad):
    assert not (W / ad).exists(), (
        f"{ad} geri gelmiş — Y320: CI yalnız Windows ürün hattı (Linux / macOS paketleme kapsam dışı)"
    )
    assert len(_is_akislari()) >= 5, f"iş akışı listesi boş / eksik okunuyor (kör kapı): {_is_akislari()}"


def test_matrix_fail_fast_KAPALI():
    """Bir platformun düşmesi diğerinin sonucunu gizlememeli."""
    assert _yukle("tests.yml")["jobs"]["backend"]["strategy"]["fail-fast"] is False


@pytest.mark.parametrize(("dosya", "is_adi"), [("frontend.yml", "test"), ("site.yml", "site")])
def test_KRITIK_arayuz_ve_site_CI_Node_22_ve_USTU_YS1f(dosya, is_adi):
    """YS1f (26-11): frontend-ci Node 20 ile koşuyordu → @supabase/realtime-js Node < 22de yerleşik WebSocket bulamayıp istemciyi
    KURARKEN atıyordu (28 jest süiti yüklenemedi; ESLint kırmızıyken jest koşmadığı için görünmedi). site.yml aynı dersi önceden almıştı."""
    surumler = [
        str((a.get("with") or {}).get("node-version", ""))
        for a in _yukle(dosya)["jobs"][is_adi]["steps"]
        if str(a.get("uses", "")).startswith("actions/setup-node")
    ]
    assert len(surumler) == 1, f"{dosya}: TEK setup-node adımı bekleniyordu: {surumler}"
    ana = re.match(r"^(\d+)", surumler[0])
    assert ana and int(ana.group(1)) >= 22, (
        f"{dosya}: Node {surumler[0]!r} — 22 altı (Supabase realtime yerleşik WebSocket ister)"
    )


def test_KRITIK_backend_isi_URUN_ortamini_ve_TS_kapilarinin_girdilerini_KURAR_YS1g():
    """YS1g (sahip 26-11: "koşmamış hiç test olmamalı"): backend işi (1) ÜRÜN ortamını
    DERLEME KİLİDİNDEN kurar (`--no-deps -r build_tools/myenv-requirements.txt`, bootstrap.ps1 komutu), (2) pytest'ten ÖNCE Node + apps/ui / apps/web bağımlılıklarını, arayüz web dışa aktarımını
    (`frontend/dist`) ve DEMA derlemesini kurar; (3) DEMA dist kapısı zorunlu kipte koşar (atlanamaz)."""
    adimlar = _yukle("tests.yml")["jobs"]["backend"]["steps"]
    metin = [str(a.get("run", "")) + " " + str(a.get("uses", "")) for a in adimlar]
    pyt = next(i for i, m in enumerate(metin) if "pytest tests" in m)
    kilit = [
        i
        for i, m in enumerate(metin)
        if re.search(
            r"pip install --no-deps -r build_tools/myenv-requirements\.txt --extra-index-url https://download\.pytorch\.org/whl/cpu",
            m,
        )
    ]
    assert kilit and kilit[0] < pyt, "CI ürün DERLEME KİLİDİNİ (bootstrap.ps1 komutu) pytest'ten önce kurmuyor"
    req = (KOK / "requirements-test.txt").read_text(encoding="utf-8")
    assert not re.search(r"^opencv-python-headless==", req, re.M), "headless + ürün opencv-python birlikte cv2'yi ezer"
    for parca in (
        "actions/setup-node",
        "cd apps/ui && npm install",
        "cd apps/web && npm ci",
        "npm run export:web",
        "frontend/dist",
        "npm run build",
    ):
        konum = [i for i, m in enumerate(metin) if parca in m]
        assert konum and max(konum) < pyt, f"backend işinde pytest'ten ÖNCE {parca!r} yok — TS / dist kapıları ATLANIR"
    node = next(a for a in adimlar if str(a.get("uses", "")).startswith("actions/setup-node"))
    assert int(str(node["with"]["node-version"]).split(".")[0]) >= 22
    ortam = adimlar[pyt].get("env") or {}
    assert str(ortam.get("PEMF_DEMA_DIST_ZORUNLU")) == "1", (
        "DEMA dist kapısı zorunlu değil — derleme düşse de SESSİZCE atlanır"
    )
    yukle = [
        a
        for a in adimlar
        if str(a.get("uses", "")).startswith("actions/upload-artifact")
        and "pytest-junit.xml" in str((a.get("with") or {}).get("path", ""))
    ]
    assert yukle and str(yukle[0].get("if", "")).strip() == "always()", (
        "junit eseri (test başına sonuç + atlama nedeni) kırmızı koşuda da yüklenmiyor — CI-ATLANAN listesi kaybolur"
    )


#: YS1k: `makensis` isteyen kurucu kanca testleri — CI'da NSIS yokken "makensis yok" diye ATLIYORLARDI (17 test).
_NSIS_ISTEYENLER = (
    "test_18K_K1_nsis_estop_VARSAYILAN_port.py",
    "test_YH_SYH2_sessiz_kaldirma_backend_port_SILINIR_veri_koku_KALIR.py",
    "test_YH_Y296_etkilesimli_kaldirma_ISARETSIZ_backend_port_SILINIR.py",
    "test_i18n_launcher_altyapi.py",
    "test_kaldirma_yetim_surec_temizligi.py",
)


def test_KRITIK_backend_isi_NSIS_derleyicisini_SABIT_OZETLE_kurar_testlere_YOLU_verir_YS1k():
    """YS1k: backend işi pytest'ten ÖNCE Tauri'nin NSIS dağıtımını (ürün kurucusunu derleyen) SHA-256 doğrulamasıyla kurar ve yolu
    `PEMF_MAKENSIS` ile verir; kanca testlerinin hepsi yolu önce bu değişkenden okur (yoksa yine sessizce atlarlardı)."""
    adimlar = _yukle("tests.yml")["jobs"]["backend"]["steps"]
    metin = [str(a.get("run", "")) for a in adimlar]
    pyt = next(i for i, m in enumerate(metin) if "pytest tests" in m)
    nsis = [i for i, m in enumerate(metin) if "nsis-3.11.zip" in m]
    assert len(nsis) == 1 and nsis[0] < pyt, "NSIS kurulum adımı yok ya da pytest'ten SONRA"
    adim, govde = adimlar[nsis[0]], metin[nsis[0]]
    assert adim.get("if") == "runner.os == 'Windows'" and not adim.get("continue-on-error"), adim
    assert "set -euo pipefail" in govde, "indirme / özet hatası adımı düşürmüyor"
    for adres in (
        "https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.11/nsis-3.11.zip",
        "https://github.com/tauri-apps/nsis-tauri-utils/releases/download/nsis_tauri_utils-v0.5.3/nsis_tauri_utils.dll",
    ):
        assert adres in govde, f"sabit adres yok: {adres}"
    assert len(re.findall(r'echo "[0-9a-f]{64}  [^"]+" \| sha256sum -c -', govde)) == 2, (
        "iki indirmenin İKİSİ de SHA-256 ile doğrulanmıyor"
    )
    assert re.search(r'echo "PEMF_MAKENSIS=.*" >> "\$GITHUB_ENV"', govde), "makensis yolu testlere verilmiyor"
    assert "makensis.exe\" -VERSION" in govde, "kurulan derleyici çalıştırılıp sınanmıyor"
    for ad in _NSIS_ISTEYENLER:
        assert "PEMF_MAKENSIS" in (KOK / "tests" / ad).read_text(encoding="utf-8"), (
            f"{ad} makensis yolunu PEMF_MAKENSIS'ten okumuyor"
        )


def test_KRITIK_backend_checkout_TAM_gecmis_YS1k():
    """YS1k: site yasal metin mührünün geçmiş kolu (D6.33) kaynak commit'i git geçmişinde arar — sığ klonda (fetch-depth 1) ATLIYORDU."""
    adimlar = _yukle("tests.yml")["jobs"]["backend"]["steps"]
    cek = [a for a in adimlar if str(a.get("uses", "")).startswith("actions/checkout")]
    assert len(cek) == 1 and str((cek[0].get("with") or {}).get("fetch-depth")) == "0", cek


def test_KRITIK_backend_isi_UYELIKSIZ_olusturulmus_YEREL_GRUP_kurar_hesaba_DOKUNMAZ_YS1m():
    """YS1m: Y96 grup ACE'i kolu (`file_acl` 2 satır) bu makinede OLUŞTURULMUŞ bir yerel grup ister; koşucuda yoktu (kapsam %99,99).
    Adım pytest'ten ÖNCE, Windows'ta, hata yutmadan grubu kurar; grup ÜYELİKSİZ — hesap eklenmez, parola değiştirilmez (`net user`)."""
    adimlar = _yukle("tests.yml")["jobs"]["backend"]["steps"]
    metin = [str(a.get("run", "")) for a in adimlar]
    pyt = next(i for i, m in enumerate(metin) if "pytest tests" in m)
    grup = [i for i, m in enumerate(metin) if "net localgroup pemf-ci-paylasim /add" in m]
    assert len(grup) == 1 and grup[0] < pyt, "yerel grup kurulum adımı yok ya da pytest'ten SONRA"
    adim, govde = adimlar[grup[0]], metin[grup[0]]
    assert adim.get("if") == "runner.os == 'Windows'" and not adim.get("continue-on-error"), adim
    assert govde.count("exit 1") >= 2, "kurulum / doğrulama hatası adımı düşürmüyor"
    assert not re.search(r"net localgroup \S+ \S+ /add", govde), (
        "gruba HESAP ekleniyor (üyelik yeni oturum ister; gereksiz)"
    )
    assert not re.search(r"\bnet user\b|Set-LocalUser|Add-LocalGroupMember", govde), "koşucu hesabına dokunuluyor"


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


#: Dizin -> o katmani kapsayan is akisi ve icinde BULUNMASI gereken adim parcalari.
#: ⚠️ 2026-08-18 MONOREPO: onceki kapi (`test_arayuz_ve_site_BU_DEPODA_DEGIL`) "bu dizinler
#: depoda IZLENMIYOR, o yuzden CI isleri kaldirildi" varsayimini kilitliyordu ve dizinler
#: subtree ile depoya alininca DOGRU sekilde KIRILDI — tam da tasarlandigi gibi. Varsayim
#: coktugu icin kapi da degisti: artik "izlenmiyor" degil, "CI KAPSAMINDA" olduklarini zorluyor.
#: Kapsam `tests.yml`de DEGIL ayri is akislarinda: ikisi de yol-filtreli (`paths:`) olmali ki
#: backend degisikligi Expo/Vite hatlarini bosuna tetiklemesin. `tests.yml`in kendisi bilerek
#: filtresizdir (capraz-katman kapilari her degisiklikte kosmali).
CI_KAPSAMI = {
    "apps/ui": ("frontend.yml", ("tsc --noEmit", "npm test")),
    "apps/web": ("site.yml", ("tsc -b", "tsc -p api --noEmit", "npm test", "check:legal")),
}


@pytest.mark.parametrize("dizin", sorted(CI_KAPSAMI))
def test_KRITIK_arayuz_ve_site_CI_KAPSAMINDA(dizin):
    """Arayuz (`apps/ui`) ve site (`apps/web`) monorepo'ya alindi -> CI kapisi ZORUNLU.

    ⚠️ SITE 2026-08-18'e kadar HIC test edilmiyordu: kendi deposunda tek bir workflow yoktu ve
    iyzico odeme uclari (checkout/callback/webhook/cancel) tip kontrolu bile gormeden deploy
    oluyordu. Bu, birlestirmenin en somut kazanci — geri kaymasin diye kilitleniyor.
    """
    dosya, beklenen_adimlar = CI_KAPSAMI[dizin]
    yol = W / dosya
    assert yol.is_file(), f"{dizin}/ depoda ama CI is akisi YOK: .github/workflows/{dosya}"

    d = _yukle(dosya)
    isler = d["jobs"]
    hepsi = " ".join(_adimlar(i, dosya) for i in isler)
    for parca in beklenen_adimlar:
        assert parca in hepsi, f"{dosya}: '{parca}' adimi YOK — {dizin}/ icin kapsam eksik"

    # Calisma dizini gercekten o alt dizin olmali; yoksa adimlar kokte kosar ve YANLIS agaci test eder.
    calisma = ((d.get("defaults") or {}).get("run") or {}).get("working-directory")
    assert calisma == dizin, f"{dosya}: working-directory '{calisma}' — '{dizin}' olmali"


@pytest.mark.parametrize("dizin", sorted(CI_KAPSAMI))
def test_arayuz_ve_site_is_akislari_YOL_FILTRELI(dizin):
    """Bu iki hat yol-filtreli olmali: backend/firmware degisikligi Expo/Vite'i tetiklemesin.

    (`tests.yml` bilerek filtresizdir — capraz-katman kapilari OTEKI tarafin dosyalarini okur.)"""
    dosya = CI_KAPSAMI[dizin][0]
    tetik = _tetikleyici(_yukle(dosya))
    yollar = tetik["push"].get("paths")
    assert yollar, f"{dosya}: push tetikleyicisinde `paths` YOK — her degisiklikte bosuna kosar"
    assert any(dizin in y for y in yollar), f"{dosya}: paths '{dizin}' icermiyor: {yollar}"


@pytest.mark.parametrize("dizin", sorted(CI_KAPSAMI))
def test_KRITIK_alt_dizinde_KOK_DISI_github_yapilandirmasi_KALMAZ(dizin):
    """`apps/ui/.github/` ya da `apps/web/.github/` altinda workflow/dependabot KALMAMALI.

    ⚠️ SESSIZ KIRILMA (2026-08-18'de ikisi de yakalandi): GitHub bu dosyalari YALNIZCA kok
    `.github/` altindan okur. subtree sonrasi `apps/ui/.github/workflows/frontend.yml` ve
    `apps/ui/.github/dependabot.yml` alt dizinde kaldi -> ikisi de SESSIZCE etkisizdi (hata yok,
    sadece yokluk). Koke tasindilar; bu kapi geri kaymayi engeller."""
    alt = W.parent.parent / dizin / ".github"
    if not alt.exists():
        return
    artik = [p.name for p in alt.rglob("*") if p.is_file() and p.suffix in (".yml", ".yaml")]
    assert not artik, (
        f"{dizin}/.github altinda kok-disi yapilandirma var: {artik} — GitHub bunlari OKUMAZ, "
        f"sessizce etkisiz kalirlar. Kok `.github/` altina tasiyin."
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
    b = (kok / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8", errors="replace")
    assert "pre_commit install" in b or "pre-commit install" in b, (
        "bootstrap.ps1 pre-commit hook'unu KURMUYOR — yeni makinede kapi kapali kalir"
    )


# ── en az yetki (regresyon kapısı) ───────────────────────────────────────────


@pytest.mark.parametrize("dosya", ["tests.yml", "lint.yml", "security.yml", "launcher.yml"])
def test_permissions_SALT_OKUR(dosya):
    """Ele geçirilmiş bir bağımlılık/action, varsayılan token'la depoya YAZABİLİRDİ."""
    d = _yukle(dosya)
    assert d.get("permissions", {}).get("contents") == "read", f"{dosya} en-az-yetki degil"


# ── BLOKLAYICILIK (D4.05 · B-10.115, B-10.152 — 2026-10-10) ─────────────────
# Önceki kapılar işlerin VARLIĞINI ölçüyordu, BLOKLAYICILIĞINI değil: `tests.yml`'in pytest satırına `|| true`, Windows
# ratchet adımından `--cov` silmek, `fail_under` 50→49 ya da bir işe `continue-on-error: true` eklemek dosyadaki her
# testi YEŞİL bırakıyordu ("ratchet boş güvenceydi" arızası + sahip kararı "fail_under=50 düşürülmez" kapısızdı).
# Artık TÜM iş akışlarındaki her iş ve adım taranır; bloklamayan biçim yalnız aşağıdaki gerekçeli izin listesindeyse
# kabul edilir ve KULLANILMAYAN izin satırı da kırmızıdır (izin listesi bayatlayıp genişlemesin).

#: Run satırında hatayı YUTAN biçimler. `|| KOD=$?` gibi kodu yakalayıp yeniden çıkan biçim yutma DEĞİLDİR.
# ⚠️ 4-A inc. 4A-2.7: eski desen `(…|:|…)\b` idi — `:`dan sonra satır sonu/boşluk gelince `\b` HİÇ eşleşmez (`|| :` KAÇIYORDU).
_YUTMA = re.compile(r"\|\|\s*(true|:|exit\s+0|echo|/bin/true)(?![\w/-])")
#: `if:` için sabit-yanlış değerler (iş/adım hiç koşmaz).
_SABIT_YANLIS = re.compile(r"^\s*(false|0|\$\{\{\s*(false|0)\s*\}\})\s*$", re.I)

#: BİLİNÇLİ istisnalar: (dosya, iş, adım adı) → izinli biçimler. Her satır sahibin/denetimin kararıdır.
BLOKLAMAYAN_IZINLI = {
    # Biçim kontrolü bilgi amaçlı (lint işi `ruff check` ile bloklar).
    ("lint.yml", "ruff", "Ruff format check (bilgi amaçlı — hata verse de iş başarısız olmaz)"): {"|| true"},
    # pip-audit bilgi amaçlı: torch/onnx CVE'leri bilinen-ertelenen (Ö.4-Y3); exact-ID izin listesi sahip işi.
    ("security.yml", "pip-audit", "pip-audit — çekirdek + SHIPPED AI ağacı (bilgi amaçlı, bloklamaz)"): {
        "continue-on-error",
        "|| true",
    },
    # Tarayıcı kurulamazsa görünüm kapısı kendisi "ATLANDI" der (exit 3 → uyarı); kapının kendisi bloklar.
    ("site.yml", "site", "Tarayici (headless olcum icin)"): {"continue-on-error"},
    # (YS1b · Y320: `linux-backend.yml` "Doğrula + paketle" izni iş akışıyla birlikte KALKTI — İG-9.58 artık yok.)
}


def _is_akislari() -> list[str]:
    return sorted(p.name for p in W.glob("*.yml"))


def _adim_adi(adim: dict) -> str:
    return str(adim.get("name") or adim.get("uses") or str(adim.get("run", ""))[:60])


def _bloklamayan(deger_cont, deger_if) -> list[str]:
    bul = []
    if deger_cont not in (None, False) and str(deger_cont).strip().lower() != "false":
        bul.append("continue-on-error")
    if deger_if is not None and _SABIT_YANLIS.match(str(deger_if)):
        bul.append("if-sabit-yanlis")
    return bul


def bloklamayan_bicimler() -> dict[tuple[str, str, str], set[str]]:
    """{(dosya, iş, adım | '<iş>'): {biçimler}} — TÜM iş akışlarında bloklamayan her biçim."""
    sonuc: dict[tuple[str, str, str], set[str]] = {}
    for dosya in _is_akislari():
        for is_adi, is_ in (_yukle(dosya).get("jobs") or {}).items():
            for b in _bloklamayan(is_.get("continue-on-error"), is_.get("if")):
                sonuc.setdefault((dosya, is_adi, "<iş>"), set()).add(b)
            for adim in is_.get("steps") or []:
                anahtar = (dosya, is_adi, _adim_adi(adim))
                for b in _bloklamayan(adim.get("continue-on-error"), adim.get("if")):
                    sonuc.setdefault(anahtar, set()).add(b)
                for m in _YUTMA.finditer(str(adim.get("run", ""))):
                    sonuc.setdefault(anahtar, set()).add("|| " + m.group(1).split()[0])
    return sonuc


def test_KRITIK_hicbir_is_ya_da_adim_IZINSIZ_bloklamayan_degil():
    """`continue-on-error`, sabit-yanlış `if:` ve hata yutan `||` yalnız gerekçeli izin listesinde."""
    # YS1b · Y320: linux-backend.yml + mac-backend.yml kalktı (9 → 7). Sayı yerine AD kümesi: okunamayan / kaybolan her iş akışı görünür.
    beklenen = {
        "frontend.yml",
        "launcher.yml",
        "lint.yml",
        "security.yml",
        "site.yml",
        "supabase-ping.yml",
        "tests.yml",
    }
    assert beklenen <= set(_is_akislari()), (
        f"VAKUM: yalnız {_is_akislari()} tarandı (eksik {sorted(beklenen - set(_is_akislari()))})"
    )
    bulunan = bloklamayan_bicimler()
    izinsiz = {k: v - BLOKLAMAYAN_IZINLI.get(k, set()) for k, v in bulunan.items()}
    izinsiz = {k: sorted(v) for k, v in izinsiz.items() if v}
    assert not izinsiz, (
        f"BLOKLAMAYAN iş/adım (izin listesinde yok): {izinsiz}. Bir CI kapısı dekorasyona dönüşmesin; bilinçliyse "
        "BLOKLAMAYAN_IZINLI'ya gerekçesiyle ekleyin."
    )


def test_KRITIK_izin_listesi_BAYATLAMAZ():
    """İzin listesinde olup artık iş akışında karşılığı olmayan biçim kalmasın (liste yalnız küçülür)."""
    bulunan = bloklamayan_bicimler()
    bayat = {k: sorted(v - bulunan.get(k, set())) for k, v in BLOKLAMAYAN_IZINLI.items() if v - bulunan.get(k, set())}
    assert not bayat, f"izin listesinde KULLANILMAYAN satır: {bayat} — kaldırın (ya da adım adı değiştiyse güncelleyin)"


#: Kapının bloklayıcı saydığı işler ve her birinin ASIL adımı (run/uses içinde aranan parça).
BLOKLAYICI_ISLER = {
    ("tests.yml", "backend"): "pytest tests",
    ("tests.yml", "launcher"): "cargo test",
    ("tests.yml", "sir-taramasi"): "gitleaks",
    ("lint.yml", "ruff"): "ruff check",
    ("site.yml", "site"): "npm test",
    ("frontend.yml", "test"): "tsc --noEmit",
}


@pytest.mark.parametrize("dosya,is_adi", sorted(BLOKLAYICI_ISLER))
def test_KRITIK_bloklayici_isin_ASIL_adimi_VAR_ve_KOSAR(dosya, is_adi):
    """Bloklayıcı iş ve asıl adımı var; iş ya da asıl adım koşulsuz-kapalı (`if: false`) ya da yutucu değil."""
    is_ = (_yukle(dosya).get("jobs") or {}).get(is_adi)
    assert is_, f"{dosya}: bloklayıcı iş '{is_adi}' YOK"
    parca = BLOKLAYICI_ISLER[(dosya, is_adi)]
    asil = [a for a in is_.get("steps") or [] if parca in (str(a.get("run", "")) + " " + str(a.get("uses", "")))]
    assert asil, f"{dosya}/{is_adi}: '{parca}' adımı YOK"
    for a in asil:
        bicim = (
            _bloklamayan(a.get("continue-on-error"), a.get("if"))
            + ["|| " + m for m in _YUTMA.findall(str(a.get("run", "")))]
            + _asil_komut_kabuk_sorunlari(str(a.get("run", "")))
        )
        assert not bicim, f"{dosya}/{is_adi}: asıl adım '{_adim_adi(a)}' bloklamıyor: {bicim}"


def _asil_komut_kabuk_sorunlari(run: str) -> list[str]:
    """4-A inc. 4A-2.7: asıl komutun çıkış kodunu KABUK yutabilir. GitHub varsayılanları: Linux `bash -e {0}` (pipefail YOK →
    `pytest | tee` teenin koduyla biter), Windows pwsh yalnız SON native komutun `$LASTEXITCODE`'una bakar (`pytest` ardından
    `python -m coverage xml` → yeşil), `set +e` / özel `shell: bash {0}` (-e yok) çok satırda aynı. Asıl adım TEK satır ve
    borusuz olmalı (bugünkü bütün asıl adımlar öyle — envanter ölçüldü)."""
    satirlar = [s for s in run.splitlines() if s.strip() and not s.strip().startswith("#")]
    sorun = []
    if len(satirlar) > 1:
        sorun.append(f"cok-satirli-asil-adim ({len(satirlar)} satir: kabuk ara komutun kodunu yutabilir)")
    if any(re.search(r"(?<!\|)\|(?!\|)", s) for s in satirlar):
        sorun.append("boru (`|`): varsayilan bash'te pipefail yok")
    return sorun


def test_KRITIK_Windows_ratchet_adimi_KAPSAMI_OLCER():
    """`fail_under` eşiği ancak kapsam ÖLÇÜLÜRSE işler: Windows pytest adımında `--cov` + `--cov-report` şart."""
    adimlar = _yukle("tests.yml")["jobs"]["backend"]["steps"]
    # ⚠️ `runner.os != 'Windows'` de "Windows" içerir — EŞİTLİK koşuluna çapalı (ilk sürüm iki adımı da seçiyordu).
    win_mi = re.compile(r"runner\.os\s*==\s*['\"]Windows['\"]")
    win = [a for a in adimlar if "pytest tests" in str(a.get("run", "")) and win_mi.search(str(a.get("if", "")))]
    assert len(win) == 1, f"Windows'ta koşan TEK pytest adımı bekleniyordu, bulunan {len(win)}"
    komut = str(win[0]["run"])
    assert re.search(r"(^|\s)--cov(\s|=|$)", komut), f"Windows ratchet adımı kapsamı ÖLÇMÜYOR: {komut}"
    assert "--cov-report" in komut, f"Windows ratchet adımında --cov-report yok: {komut}"
    # 4-A inc. 4A-2.8: komut satırı `--cov-fail-under` pyproject eşiğini EZER, `--cov-config` başka ayar dosyasına yönlendirir.
    for dosya in _is_akislari():
        for is_ in (_yukle(dosya).get("jobs") or {}).values():
            for a in is_.get("steps") or []:
                ez = re.findall(r"--cov-(?:fail-under|config)\b\S*", str(a.get("run", "")))
                assert not ez, f"{dosya}/{_adim_adi(a)}: {ez} — pyproject fail_under eşiğini EZER (sahip kararı #20)"


def _fail_under() -> float:
    metin = (KOK / "pyproject.toml").read_text(encoding="utf-8")
    blok = re.search(r"^\[tool\.coverage\.report\]\s*$(.*?)(?=^\[)", metin, re.M | re.S)
    assert blok, "pyproject.toml'da [tool.coverage.report] bölümü yok"
    m = re.search(r"^fail_under\s*=\s*([0-9.]+)\s*$", blok.group(1), re.M)
    assert m, "[tool.coverage.report] fail_under tanımsız — ratchet YOK"
    return float(m.group(1))


#: Ratchet TABANI — test sabiti (mutasyon hedefi pyproject'ten OKUNMAZ). Sahip kararı #20: yalnız yükseltilir. D4.02 adım 2
#: (2026-10-10): genişlemiş kaynakla ölçülen %79,14 → eşik 75; taban da 75'e çekildi (50'de kalsaydı 75→51 düşürmesi YEŞİLDİ).
#: KP-2 A5 (Y243, 2026-11-03): CI eşdeğeri ölçülen %96,58 → eşik 95; taban 95 (75'te kalsaydı 95→76 düşürmesi YEŞİLDİ).
#: KP-2 kapanış (2026-11-03): KP-2 C testleriyle ölçülen %97,41 → eşik ve taban 96.
#: KP-3 AŞAMA D (2026-11-08): KP-3 C testleriyle ölçülen %99,88 (@ c83b47e9; C18 kalan 30 satırı kapattı + 1 ULASILAMAZ etiketi) → eşik ve taban 98.
#: KP-4 C (2026-11-11): CI eşdeğeri (temiz klon kp2s @ 147bcaea, modelsiz / eserSİZ, tests.yml Windows adımı aynen) TOPLAM %99,98 (26504 ifade, 5 kapsanmayan — hepsi ai_router model yolları) → eşik ve taban 99.
#: KP-6 F (2026-11-16): kapanış (modelli tam süit, uç 03186e40) %100 (26 924 deyim, 0 eksik) + CI-eşdeğeri (E13 paketli, kp2s) ∪ K6C10 testleri %100 (0 eksik) → eşik ve taban 100.
_FAIL_UNDER_TABANI = 100


def test_KRITIK_fail_under_SAHIP_KARARI_TABANIN_ALTINA_DUSMEZ():
    """Sahip kararı (#20): kapsam eşiği DÜŞÜRÜLMEZ (yalnız yükseltilir) — taban son ölçülen yükseltmenin değeridir."""
    assert _fail_under() >= _FAIL_UNDER_TABANI, (
        f"fail_under {_fail_under()} < {_FAIL_UNDER_TABANI} — sahip kararı: eşik düşürülmez"
    )
    # 4-A inc. 4A-2.8: coverage.py ayarı `.coveragerc` → `setup.cfg [coverage:*]` → `tox.ini [coverage:*]` → pyproject
    # sırasıyla arar ve İLK bulunanı kullanır (pyproject hiç okunmaz); pytest-cov `--cov-fail-under` (addopts) dosyayı ezer.
    assert not (KOK / ".coveragerc").exists(), (
        ".coveragerc VAR — pyproject [tool.coverage] hiç okunmaz, eşik oradan gelir"
    )
    for ad in ("setup.cfg", "tox.ini"):
        yol = KOK / ad
        if yol.exists():
            assert not re.search(r"^\[coverage:", yol.read_text(encoding="utf-8", errors="replace"), re.M), (
                f"{ad} [coverage:*] bölümü taşıyor — pyproject eşiği okunmaz"
            )
    ez = re.findall(r"--cov-(?:fail-under|config)\b\S*", (KOK / "pyproject.toml").read_text(encoding="utf-8"))
    assert not ez, f"pyproject (addopts) {ez} — fail_under eşiğini EZER"
