# Author: mertaygn, cglrgrkn
"""T-b (T3 bulgusu, Y195) — `stm_yak.py` ve `STM32_Programmer_CLI` çağıran HER yol ST-Link'i SERİ NUMARASIYLA seçer (`sn=`); iki ST-Link
takılıyken seçim yoksa karta DOKUNMADAN durur.

ÖLÇÜLEN KUSUR (T3, 2026-10-23/24 `YAYIN-T3.md`): `utils.stm_yakma` her komutu `-c port=SWD` ile veriyordu → yakıcı İLK bulduğu proba
bağlanır; tezgâhta iki kart (tezgâh + saha) takılıyken yedek / yazma / geri okuma YANLIŞ karta gidebilirdi. T3 betikleri bu yüzden her
komutu elle `sn=` ile sabitledi.
SÖZLEŞME:
  * Seçim TEK yerde (`stlink_sec`, yakıcının kendi listesi `-l st-link` — karta yazmaz): tek prob → onun SN'i; birden çok prob + seçim
    yok → `STLINK_SECILEMEDI` (16), hiçbir `-c` komutu YOK; istenen SN takılı değil / liste alınamadı / prob yok → aynı.
  * Seçimden sonra yedek, yazma, geri okuma, yeniden başlatma, geri dönüş ve elle kurtarma komutlarının HEPSİ `sn=<SN>` taşır.
  * Backend'in kendi yakması (oto-firmware, Y1 kapalı) da aynı seçimden geçer.
  * Kaynakta `port=SWD` dizgisi YALNIZ `_baglan` içinde (yeni bir komut seçimi atlayamaz).
Yakıcı SAHTE, EN ALT katta (`stm_yakma._kos`); kart doğrulaması için seri port sahte. Gerçek ST-Link / port / yakma YOK.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN import ortam  # noqa: F401 — fikstür (backend yakma yolu)
from test_Ta_stm_yak_GERI_DONUS_ve_NACK_ESIGI_TEZGAH2 import _Kart  # bayt düzeyinde kart öykünmesi

KOK = Path(__file__).resolve().parents[1]
SN1 = "066DFF565251887067064422"  # tezgâh kartının ST-Link'i (`DENETIM/t2/kanit/C1_rst_once.txt`)
SN2 = "0671FF484851897167154333"


def _liste(*sn_ler: str) -> str:
    """Yakıcının `-l st-link` çıktısı (prob başına `ST-LINK SN  :` satırı — tezgâh çıktısındaki biçim)."""
    govde = "".join(
        f"ST-Link Probe {i} :\n   ST-LINK SN  : {sn}\n   ST-LINK FW  : V2J46M31\n   Board Name  : NUCLEO-F429ZI\n"
        for i, sn in enumerate(sn_ler)
    )
    return (
        "-------- Connected ST-LINK Probes List --------\n\n"
        + govde
        + "-----------------------------------------------\n"
    )


class _Yakici:
    """EN ALT kat: yakıcı CLI. `-l st-link` → prob listesi; `-w` / `-r` sahte flash; çağrılar kaydedilir."""

    def __init__(self, sn_ler: tuple[str, ...] = (SN1,), liste_rc: int = 0):
        self.sn_ler, self.liste_rc = sn_ler, liste_rc
        self.flash = bytearray(b"ONCEKI-FW-" * 16) + bytearray(b"\xff" * 64)
        self.cagri: list[list[str]] = []

    def __call__(self, _cli, argumanlar, timeout=300.0):
        a = list(argumanlar)
        self.cagri.append(a)
        if a[:1] == ["-l"]:
            return self.liste_rc, (_liste(*self.sn_ler) if self.liste_rc == 0 else "Error: ST-Link listesi")
        if "-w" in a:
            veri = Path(a[a.index("-w") + 1]).read_bytes()
            self.flash[: len(veri)] = veri
        if "-r" in a:
            i = a.index("-r")
            boy, hedef = int(a[i + 2]), Path(a[i + 3])
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(bytes(self.flash[:boy]).ljust(boy, b"\xff"))
        return 0, "sahte yakici: tamam"

    def baglantilar(self) -> list[list[str]]:
        return [c for c in self.cagri if "-c" in c]


@pytest.fixture
def ortamlar(monkeypatch, tmp_path):
    import serial
    import utils.stm_yakma as sy

    durum = {"tur": "yeni"}
    monkeypatch.setattr(serial, "Serial", lambda port, baud=115200, timeout=None, **_k: _Kart(durum["tur"]))
    monkeypatch.setattr("utils.stm32_uart.portlari_listele", lambda: [])
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"YENI-FIRMWARE-" * 8)

    def kur(sn_ler=(SN1,), liste_rc=0):
        y = _Yakici(tuple(sn_ler), liste_rc)
        monkeypatch.setattr(sy, "_kos", y)
        return y

    return sy, ikili, kur, durum


def _akis(sy, ikili, tmp_path, **k):
    return sy.yakma_akisi(
        ikili, port="COM_TB", guvenlik_kontrolu=lambda: (True, "test"), yedek_dizin=tmp_path / "y", **k
    )


def _hepsi_sn(y: _Yakici, sn: str) -> None:
    b = y.baglantilar()
    assert b, "aparat: hiç -c komutu yok"
    yanlis = [c for c in b if f"sn={sn}" not in c or c.count("-c") != 1 or c[c.index("-c") + 1] != "port=SWD"]
    assert not yanlis, f"sn={sn} TAŞIMAYAN yakıcı komutu (yanlış karta gidebilir): {yanlis}"


# ── (1) tek prob → her komut onun SN'iyle ────────────────────────────────────────────────────────────────────────


def test_KRITIK_tek_STLINK_her_komut_sn_ile(ortamlar, tmp_path):
    sy, ikili, kur, _d = ortamlar
    y = kur((SN1,))
    s = _akis(sy, ikili, tmp_path)
    assert s.kod == sy.TAMAM, f"{s.kod} {s.ozet}"
    _hepsi_sn(y, SN1)
    assert sum(1 for c in y.baglantilar() if "-r" in c) >= 2 and sum(1 for c in y.baglantilar() if "-w" in c) == 1


def test_KRITIK_geri_donus_komutlari_da_sn_ile(ortamlar, tmp_path):
    sy, ikili, kur, d = ortamlar
    y = kur((SN1,))
    d["tur"] = "eski"  # yeni firmware kartı paketimizi reddediyor → OTOMATİK geri dönüş (T-a)
    s = _akis(sy, ikili, tmp_path)
    assert s.kod == sy.UYUMSUZ_GERI_DONULDU and sum(1 for c in y.cagri if "-w" in c) == 2, f"{s.kod} {s.ozet}"
    _hepsi_sn(y, SN1)


# ── (2) iki prob → seçim yoksa DUR, seçim varsa o SN ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kuru", [False, True], ids=["yakma", "kuru"])
def test_KRITIK_iki_STLINK_secimsiz_KARTA_DOKUNMADAN_durur(ortamlar, tmp_path, kuru):
    sy, ikili, kur, _d = ortamlar
    y = kur((SN1, SN2))
    s = _akis(sy, ikili, tmp_path, kuru=kuru)
    assert s.kod == getattr(sy, "STLINK_SECILEMEDI", -1), (
        f"iki ST-Link takılıyken seçimsiz akış durmadı: {s.kod} {s.ozet}"
    )
    assert not y.baglantilar(), f"seçim yokken karta bağlanıldı: {y.baglantilar()}"
    assert SN1 in s.ozet and SN2 in s.ozet and "--stlink-sn" in s.ozet, s.ozet


def test_KRITIK_iki_STLINK_secilen_SN_ile_yakar(ortamlar, tmp_path):
    sy, ikili, kur, _d = ortamlar
    y = kur((SN1, SN2))
    s = _akis(sy, ikili, tmp_path, stlink_sn=SN2.lower())
    assert s.kod == sy.TAMAM, f"{s.kod} {s.ozet}"
    _hepsi_sn(y, SN2)


@pytest.mark.parametrize(
    ("sn_ler", "liste_rc", "istenen"),
    [((SN1,), 0, SN2), ((), 0, None), ((SN1,), 1, None)],
    ids=["istenen_takili_degil", "prob_yok", "liste_alinamadi"],
)
def test_KRITIK_secilemezse_hicbir_komut_YOK(ortamlar, tmp_path, sn_ler, liste_rc, istenen):
    sy, ikili, kur, _d = ortamlar
    y = kur(sn_ler, liste_rc)
    s = _akis(sy, ikili, tmp_path, stlink_sn=istenen)
    assert s.kod == getattr(sy, "STLINK_SECILEMEDI", -1), f"{s.kod} {s.ozet}"
    assert not y.baglantilar(), y.baglantilar()


# ── (3) elle kurtarma ve CLI ─────────────────────────────────────────────────────────────────────────────────────


def _cli(argv):
    p = KOK / "scripts" / "stm_yak.py"
    spec = importlib.util.spec_from_file_location("_stm_yak_tb", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.main(argv)


def test_KRITIK_elle_kurtarma_da_iki_STLINKte_secim_ister_ve_SN_ile_yazar(ortamlar, tmp_path, monkeypatch, capsys):
    sy, _ikili, kur, d = ortamlar
    monkeypatch.setattr(sy, "seans_ve_bobin_kontrolu", lambda _b: (True, "test: backend kapalı"))
    eski = tmp_path / "saha_yedek_1.bin"
    eski.write_bytes(b"SAHA-IMAJI-" * 12)
    d["tur"] = "eski"
    y = kur((SN1, SN2))
    rc = _cli(["--kurtarma", "--bin", str(eski), "--sha256", sy.sha256(eski), "--port", "COM_TB"])
    assert rc == sy.STLINK_SECILEMEDI and not y.baglantilar(), (rc, y.cagri, capsys.readouterr().out)
    y = kur((SN1, SN2))
    rc = _cli(["--kurtarma", "--bin", str(eski), "--sha256", sy.sha256(eski), "--port", "COM_TB", "--stlink-sn", SN1])
    assert rc == 0, capsys.readouterr().out
    _hepsi_sn(y, SN1)


def test_KRITIK_cli_stlink_sn_ARGUMANI_akisa_gider(ortamlar, tmp_path, monkeypatch, capsys):
    sy, ikili, kur, _d = ortamlar
    monkeypatch.setattr(sy, "seans_ve_bobin_kontrolu", lambda _b: (True, "test: backend kapalı"))
    kur((SN1, SN2))
    rc = _cli(["--bin", str(ikili), "--kuru", "--stlink-sn", SN2])
    out = capsys.readouterr().out
    assert rc == 0 and f"sn={SN2}" in out, out


# ── (4) backend'in kendi yakması da aynı seçimden geçer ──────────────────────────────────────────────────────────


def test_KRITIK_backend_yakmasi_iki_STLINKte_KARTA_DOKUNMAZ(ortam, monkeypatch):
    import test_firmware_otomatik_ONKOSULLAR_Y80_Y81_Y82_LN as ln

    o = ortam
    asil = o.kart.kos
    cagri: list[list[str]] = []

    def kos(cli, argumanlar, timeout=300.0):
        a = list(argumanlar)
        cagri.append(a)
        if a[:1] == ["-l"]:
            return 0, _liste(SN1, SN2)
        return asil(cli, argumanlar, timeout)

    monkeypatch.setattr(o.sy, "_kos", kos)
    eski = bytes(o.kart.flash[:32])
    d = ln._ac(o)
    assert f"[{o.sy.STLINK_SECILEMEDI}]" in str(d.get("hata")), d
    assert not [c for c in cagri if "-c" in c], f"backend yakması iki ST-Link'te karta bağlandı: {cagri}"
    assert bytes(o.kart.flash[:32]) == eski


# ── (5) kaynak: `port=SWD` yalnız `_baglan` içinde ──────────────────────────────────────────────────────────────


def test_KRITIK_port_SWD_dizgisi_YALNIZ_baglan_icinde():
    kaynak = (KOK / "apps" / "backend" / "utils" / "stm_yakma.py").read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    disarida = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str) and "port=SWD" in dugum.value:
            disarida.append(dugum)
    baglan = next(f for f in agac.body if isinstance(f, ast.FunctionDef) and f.name == "_baglan")
    icindekiler = {id(n) for n in ast.walk(baglan)}
    kod_dizgileri = [n for n in disarida if id(n) not in icindekiler and not _docstring_mi(agac, n)]
    assert not kod_dizgileri, (
        f"`port=SWD` `_baglan` DIŞINDA kullanılıyor (sn= atlanır): satır {[n.lineno for n in kod_dizgileri]}"
    )
    assert any(id(n) in icindekiler for n in disarida), "aparat: `_baglan` içinde port=SWD yok"


def _docstring_mi(agac: ast.Module, dugum: ast.Constant) -> bool:
    for n in ast.walk(agac):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body:
            ilk = n.body[0]
            if isinstance(ilk, ast.Expr) and ilk.value is dugum:
                return True
    return False
