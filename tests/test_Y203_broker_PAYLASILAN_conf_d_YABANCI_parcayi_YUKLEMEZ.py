# Author: mertaygn, cglrgrkn
"""Y203 (sahip, S-D3I.3) — yerel broker paylaşılan `conf.d`'deki YABANCI dosyayı YÜKLEMEZ; A-04 kimliği korunur.

KUSUR (D3I-A2.9 sırasında bulundu, önceden var): launcher çocuğu backend'in broker çalışma kopyası
(`%LOCALAPPDATA%\\PEMF_System\\mosquitto\\pemf_calisma.conf`) SONUNA `include_dir %ProgramData%\\PEMF_System\\mosquitto\\conf.d`
ekliyordu. ProgramData mirası `Users`a her alt dizinde YENİ dosya yaratma verir → bu bilgisayardaki HER yerel hesap oraya bir
`.conf` bırakıp broker'a `plugin <dll>` (broker sürecinde, onu açan hesabın yetkisiyle kod), ek `listener` ya da kimlik
parçasından SONRA okunan `allow_anonymous true` (A-04'ü ezer) yükletebiliyordu. Servis kipinde (`setup_services.ps1` NSSM —
LocalSystem) aynı dizin hiç sertleştirilmiyordu.

KARAR (Y203): broker yalnız hesaba özel / korunmuş yapılandırmayı okur. Çalışma kopyası kimlik YÖNERGELERİNİ satır içi taşır
(`mqtt_kimlik.calisma_kopyasi_yonergeleri` — koddan üretilir, paylaşılan dosyadan OKUNMAZ) ve HİÇBİR `include_dir` eklemez;
tetik paylaşılan `conf.d` parçası DEĞİL, kimlik deposu + broker parola / yetki dosyalarıdır (Y71 onarımı paylaşılan `conf.d`'ye
yazamasa da broker kimlikli açılır). Servis kipinde `conf.d` yalnız SYSTEM + Yöneticilere yazılabilir (`Protect-PemfDir`).

Ölçüm GERÇEK `mqtt_kimlik.hazirla` + GERÇEK `MosquittoSupervisor._kimlik_dahil_conf` ile; broker yapılandırmasının ETKİN içeriği
mosquitto 2.0.18'in okuma kuralıyla (sıralı; `include_dir` yalnız ana dosyada, `*.conf` büyük/küçük harf duyarlı alfabetik;
Windows'ta BOŞ include_dir AÇILMAZ) çıkarılır. Gerçek mosquitto / ACL / hesap YOK (kafes); gerçek broker → TEZGÂH-2.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

YABANCI = "plugin C:/kotu/eklenti.dll\nlistener 1884 0.0.0.0\nallow_anonymous true\n"


@pytest.fixture
def mk(monkeypatch, tmp_path):
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "hesap" / "AppData" / "Local"))
    mqtt_kimlik._onbellek.clear()
    yield mqtt_kimlik
    mqtt_kimlik._onbellek.clear()


def _taban(tmp_path: Path) -> Path:
    t = tmp_path / "paket" / "mosquitto.conf"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text("listener 1883 0.0.0.0\nallow_anonymous true\npersistence false\n", encoding="utf-8")
    return t


def _etkin(ana: Path) -> list[tuple[str, str, Path]]:
    """mosquitto 2.0.18 okuma modeli: (yönerge, değer, kaynak dosya) sıralı listesi. `include_dir` YALNIZ ana dosyada işlenir;
    dizindeki `*.conf` dosyaları büyük/küçük harf duyarlı alfabetik sırayla o noktada okunur; Windows'ta BOŞ include_dir'de
    broker AÇILMAZ (2.0.18'de ölçüldü — rc=3)."""

    def satirlar(p: Path):
        for s in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = s.strip()
            if s and not s.startswith("#"):
                ad, _, deger = s.partition(" ")
                yield ad, deger.strip()

    sonuc: list[tuple[str, str, Path]] = []
    for ad, deger in satirlar(ana):
        if ad != "include_dir":
            sonuc.append((ad, deger, ana))
            continue
        parcalar = sorted((p for p in Path(deger).glob("*") if p.suffix == ".conf"), key=lambda p: p.name)
        assert parcalar, f"BOŞ include_dir — mosquitto (Windows) AÇILMAZ: {deger}"
        for p in parcalar:
            sonuc += [(a, d, p) for a, d in satirlar(p)]
    return sonuc


def _degerler(etkin, ad: str) -> list[str]:
    return [d for a, d, _ in etkin if a == ad]


def _kimlik_etkin(mk, etkin, bd: Path) -> None:
    anonim = _degerler(etkin, "allow_anonymous")
    assert anonim and anonim[-1] == "false", (
        f"broker ANONİM açılır — A-04 kimliği kayboldu (allow_anonymous sırası: {anonim})"
    )
    assert _degerler(etkin, "password_file") == [f"{bd.as_posix()}/{mk.PASSWD_ADI}"], _degerler(etkin, "password_file")
    assert _degerler(etkin, "acl_file") == [f"{bd.as_posix()}/{mk.ACL_ADI}"], _degerler(etkin, "acl_file")
    kimlikler = mk.kimlikleri_oku()
    satir = dict(s.split(":", 1) for s in (bd / mk.PASSWD_ADI).read_text(encoding="utf-8").splitlines() if s)
    assert kimlikler and all(mk.ozet7_dogrula(p, satir[k]) for k, p in kimlikler.items()), (
        "broker parola dosyası depodaki parolalarla doğrulanmıyor — ESP'ye yakılmış kimlik geçersiz (A-04 / A-18)"
    )


def _sup():
    from services.headless_services import MosquittoSupervisor

    return MosquittoSupervisor.__new__(MosquittoSupervisor)


def test_KRITIK_paylasilan_conf_d_YABANCI_parca_broker_yapilandirmasina_GIRMEZ_kimlik_ETKIN(mk, tmp_path):
    taban = _taban(tmp_path)
    mk.hazirla()
    bd = mk.varsayilan_broker_dizini()
    (bd / mk.CONF_DIZINI / "zz_yabanci.conf").write_text(YABANCI, encoding="utf-8")

    calisma = _sup()._kimlik_dahil_conf(taban)

    assert calisma != taban, "hazırlanmış kimlikte broker ANONİM tabanla açılır (A-04 kaybı)"
    etkin = _etkin(calisma)
    disaridan = sorted({str(k) for _, _, k in etkin if k not in (calisma,)})
    assert not disaridan, (
        f"broker hesaba özel çalışma kopyası DIŞINDAN yapılandırma okuyor (paylaşılan conf.d): {disaridan}"
    )
    assert not _degerler(etkin, "plugin") and not _degerler(etkin, "auth_plugin"), (
        "yabancı `plugin` yönergesi broker'a girdi"
    )
    assert _degerler(etkin, "listener") == ["1883 0.0.0.0"], f"yabancı listener eklendi: {_degerler(etkin, 'listener')}"
    _kimlik_etkin(mk, etkin, bd)
    kok = (Path(os.environ["LOCALAPPDATA"]) / "PEMF_System").resolve()
    assert kok in calisma.resolve().parents, f"çalışma kopyası hesaba özel kökte değil: {calisma}"
    assert not (bd / "pemf_calisma.conf").exists(), "çalışma kopyası paylaşılan broker dizinine yazıldı"


def test_KRITIK_ikinci_tur_IDEMPOTENT_sonradan_birakilan_yabanci_parca_da_GIRMEZ(mk, tmp_path):
    taban = _taban(tmp_path)
    mk.hazirla()
    bd = mk.varsayilan_broker_dizini()
    ilk = _sup()._kimlik_dahil_conf(taban)
    ilk_metin = ilk.read_text(encoding="utf-8")
    (bd / mk.CONF_DIZINI / "AA_once_okunur.conf").write_text(YABANCI, encoding="utf-8")
    ikinci = _sup()._kimlik_dahil_conf(taban)
    assert ikinci == ilk and ikinci.read_text(encoding="utf-8") == ilk_metin, (
        "ikinci açılışta çalışma kopyası değişti / büyüdü"
    )
    etkin = _etkin(ikinci)
    assert not _degerler(etkin, "plugin"), "ikinci açılışta yabancı plugin yüklendi"
    _kimlik_etkin(mk, etkin, bd)


def test_KRITIK_paylasilan_kimlik_parcasi_YOKKEN_de_broker_KIMLIKLI_onarim_paylasilan_conf_d_ye_BAGLI_DEGIL(
    mk, tmp_path
):
    """Y71 onarımı paylaşılan `conf.d`'ye yazamazsa (servis kipinde yalnız yöneticiye açık / başka hesabın dizini) launcher çocuğu
    broker yine KİMLİKLİ açılmalı: tetik kimlik deposu + parola / yetki dosyasıdır, paylaşılan parça değil."""
    taban = _taban(tmp_path)
    mk.hazirla()
    bd = mk.varsayilan_broker_dizini()
    (bd / mk.CONF_DIZINI / mk.CONF_ADI).unlink()

    calisma = _sup()._kimlik_dahil_conf(taban)

    assert calisma != taban, (
        "paylaşılan conf.d parçası yokken broker ANONİM açılır — kimlik paylaşılan dizine bağlı (A-04 kaybı)"
    )
    _kimlik_etkin(mk, _etkin(calisma), bd)


def test_KARSIT_kimlik_deposu_YOKKEN_paylasilan_dizine_birakilan_SAHTE_parca_TETIKLEMEZ_taban_AYNEN(mk, tmp_path):
    """Hazırlanmamış (bugünkü saha: ESP kapalı, A-04 ESP dönüşünde) makinede başka bir hesabın paylaşılan dizine bıraktığı sahte
    kimlik parçası / yabancı dosya ne broker'ı kimlikli kipe sokar (eksik parola dosyasıyla broker AÇILMAZ — ESP STOP yolu) ne de
    yüklenir: taban AYNEN, anonim (bugünkü davranış)."""
    taban = _taban(tmp_path)
    bd = mk.varsayilan_broker_dizini()
    (bd / mk.CONF_DIZINI).mkdir(parents=True)
    (bd / mk.CONF_DIZINI / mk.CONF_ADI).write_text(mk.conf_metni(bd), encoding="utf-8")
    (bd / mk.CONF_DIZINI / "zz_yabanci.conf").write_text(YABANCI, encoding="utf-8")
    (bd / mk.PASSWD_ADI).write_text(
        "saldirgan:$7$101$AAAA$BBBB\n", encoding="utf-8"
    )  # sahte parola / yetki dosyası da tetiklemez
    (bd / mk.ACL_ADI).write_text("pattern readwrite #\n", encoding="utf-8")

    assert _sup()._kimlik_dahil_conf(taban) == taban, (
        "kimlik deposu yokken sahte parça broker yapılandırmasını değiştirdi"
    )
    etkin = _etkin(taban)
    assert _degerler(etkin, "allow_anonymous") == ["true"] and not _degerler(etkin, "plugin")
    assert not (Path(os.environ["LOCALAPPDATA"]) / "PEMF_System").exists(), "hazırlanmamışken çalışma kopyası yazıldı"


def test_KRITIK_yonergeler_TEK_kaynaktan_parca_ile_AYNI_ve_cift_password_file_YOK(mk, tmp_path):
    """Servis kipi parçası (`conf.d/pemf_kimlik.conf`) ile satır içi yönergeler AYNI üreticiden: biri değişip öbürü kalırsa kipler
    ayrışır. Tabanın kendi password_file / acl_file'ı varsa taban AYNEN (mosquitto yinelenen password_file'da AÇILMAZ)."""
    mk.hazirla()
    bd = mk.varsayilan_broker_dizini()
    yon = mk.calisma_kopyasi_yonergeleri(bd)
    assert yon is not None
    parca = [
        s
        for s in (bd / mk.CONF_DIZINI / mk.CONF_ADI).read_text(encoding="utf-8").splitlines()
        if s and not s.startswith("#")
    ]
    assert [s for s in yon.splitlines() if s and not s.startswith("#")] == parca
    kendi = tmp_path / "kendi.conf"
    kendi.write_text("listener 1883\nallow_anonymous false\npassword_file /x/y\n", encoding="utf-8")
    assert _sup()._kimlik_dahil_conf(kendi) == kendi, (
        "kendi password_file'ı olan tabana yönerge eklendi (yinelenen password_file)"
    )


# ── servis kipi (yönetici kurulumu; gerçek ACL ölçümü YASAK → betik metni) ───────────────────────────────────────────────────
def _kod(metin: str) -> str:
    """PowerShell yorum satırlarını ve satır sonu yorumlarını at (aranan çağrı yalnız yorumda kalırsa SAYILMAZ)."""
    out = []
    for s in metin.splitlines():
        if s.lstrip().startswith("#"):
            continue
        out.append(re.sub(r"\s+#\s.*$", "", s))
    return "\n".join(out)


def test_KRITIK_servis_kipi_conf_d_YALNIZ_yoneticiye_yazilabilir_setup_services():
    ps = _kod((KOK / "scripts" / "setup_services.ps1").read_text(encoding="utf-8-sig"))
    govde = re.search(r"function Protect-PemfDir\(\[string\]\$Dir\) \{(.*?)\n\}", ps, re.S)
    assert govde, "Protect-PemfDir işlevi yok"
    g = govde.group(1)
    assert "/inheritance:r" in g and "'*S-1-5-32-545:(OI)(CI)RX'" in g, "Protect-PemfDir Users'ı salt-okura indirmiyor"
    assert not re.search(r"S-1-5-32-545:\([^)]*\)\([^)]*\)(?!RX')", g) and "S-1-1-0" not in g and "S-1-5-11" not in g
    cagri = [m.start() for m in re.finditer(r'Protect-PemfDir "\$MosqDataRoot\\conf\.d"', ps)]
    assert len(cagri) == 1, (
        "servis kipinde conf.d sertleştirilmiyor (her yerel hesap broker'a plugin bırakabilir — LocalSystem)"
    )
    yer_tutucu = ps.index("Set-Content -Path $TabanParca")
    baslat = ps.index("& $NssmExe start $ServiceMosq")
    assert yer_tutucu < cagri[0] < baslat, (
        "conf.d, yer tutucu yazıldıktan SONRA ve broker servisi başlamadan ÖNCE sertleşmeli"
    )


def test_KRITIK_servis_kipi_conf_d_YALNIZ_yoneticiye_yazilabilir_install_mosquitto_service():
    ps = _kod((KOK / "scripts" / "install_mosquitto_service.ps1").read_text(encoding="utf-8-sig"))
    m = re.search(r"& icacls \$ConfDir /inheritance:r ([^\n]*)", ps)
    assert m, "A-11 servis yolunda conf.d sertleştirilmiyor (her yerel hesap broker'a plugin bırakabilir — LocalSystem)"
    hak = re.findall(r"/grant '\*(S-[0-9-]+):\(OI\)\(CI\)(\w+)'", m.group(1))
    assert dict(hak) == {"S-1-5-18": "F", "S-1-5-32-544": "F", "S-1-5-32-545": "RX"}, hak
    assert ps.index("Set-Content -Path $TabanParca") < m.start() < ps.index("Set-Content -Path $ConfPath"), (
        "conf.d, yer tutucu yazıldıktan SONRA ve broker yapılandırması / servisi kurulmadan ÖNCE sertleşmeli"
    )
