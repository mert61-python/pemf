# -*- coding: utf-8 -*-
"""4B-1.7 — D4.12 kapısı (`test_docker_KALICI_makine_kimligi_D412.py`) commit iletisinde İDDİA edilen üç özelliği ÖLÇMÜYOR (kör kapı;
ölçüldü: altı mutant D412 + D420'de 14/14 YEŞİL):

  (1) CRLF: depoda `.gitattributes` YOK; Windows checkout'u (`core.autocrlf=true` — sahibin makinesi) giriş betiğini CRLF getirir ve
      Dockerfile onu `sed -i 's/\\r$//'` ile normalize eder. Satır silinirse Debian `/bin/sh` (dash) `set -eu\\r` ile düşer → konteyner
      AÇILMAZ. D412 betiği koşmadan önce CRLF'i KENDİSİ normalize ediyor ve git-bash `sh` CR'ye toleranslı (ölçüldü) → kör.
  (2) `exec "$@"`: CMD betiğin süreci YERİNE geçer (micro compose'ta PID 1 = uvicorn; `docker stop` SIGTERM'i ona ulaşır). `exec` silinirse
      komut yine koşar → D412 yeşil; sahada kabuk PID 1'de kalır, SIGTERM yutulur, 10 sn sonra SIGKILL (düzgün kapanış yok).
  (3) Kimlik birimi `/data`'dan AYRI ("yalnız veri yedeği sırları açmaz"). Compose kimlik dizinini veri birimine bağlarsa D412 yeşil (o da
      adlı birim) → veri yedeği makine kimliğini + `pemf_secrets.json`'u BİRLİKTE taşır, SQLCipher anahtarı yedekten çözülür.

Ölçüm: (1) git'in KENDİ Windows checkout baytları (`git -c core.autocrlf=true cat-file --filters HEAD:<betik>`) + Dockerfile'daki RUN
normalizasyonunun yorumlanması (git-bash `sed` metin kipinde `\\r$`'ı eşleştirmez — ölçüldü, 27/27 CR kaldı — bu yüzden komut koşturulmaz,
desteklenen biçimler Python'da uygulanır); (2) GERÇEK betik `sh` ile, komut ebeveyninin `/proc/$PPID/cmdline`'ını okur (aparat öz-denetimi:
`exec`'siz sarıcıda ad GÖRÜNMELİ); (3) compose (PyYAML) + Dockerfile `ENV PEMF_DATA_DIR`.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath

import pytest
import yaml

_YOL = Path(__file__).with_name("test_docker_KALICI_makine_kimligi_D412.py")
_spec = importlib.util.spec_from_file_location("zz_d412_4b17", _YOL)
d412 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d412)

KOK = d412.KOK
REL = d412.BETIK.relative_to(KOK).as_posix()


# ---------------------------------------------------------------- (1) CRLF
def _windows_checkout_baytlari() -> bytes:
    r = subprocess.run(
        ["git", "-c", "core.autocrlf=true", "cat-file", "--filters", f"HEAD:{REL}"],
        cwd=str(KOK),
        capture_output=True,
        timeout=60,
    )
    assert r.returncode == 0, f"git cat-file --filters koşmadı: {r.stderr[:300]!r}"
    return r.stdout


def _sed_uygula(argv: list[str], bayt: bytes) -> bytes | None:
    """`sed -i [-e] 's/<desen>/<yerine>/[g]' <dosya>` — yalnız bu biçim; başka biçim None (desteklenmiyor → normalize sayılmaz)."""
    if "-i" not in argv:
        return None
    ifadeler = [a for a in argv[1:] if a.startswith("s") and len(a) > 3 and not a.startswith("-")]
    if len(ifadeler) != 1:
        return None
    ifade = ifadeler[0]
    ayr = ifade[1]
    parca = ifade[2:].split(ayr)
    if len(parca) != 3:
        return None
    desen = parca[0].replace("\\r", "\r").replace("\\t", "\t")
    yerine = parca[1]
    satirlar = bayt.decode("utf-8").split("\n")
    return "\n".join(re.sub(desen, yerine, s, count=0 if "g" in parca[2] else 1) for s in satirlar).encode("utf-8")


def _imajdaki_betik(bayt: bytes) -> tuple[bytes, list[str]]:
    """Dockerfile'ı yorumlar: betiği imaja getiren SON COPY'den sonraki RUN alt komutlarından betiğe dokunanlar uygulanır."""
    t = d412._dockerfile_talimatlari()
    workdir = [a for ad, a in t if ad == "WORKDIR"][-1]
    mutlak = str(PurePosixPath(workdir) / REL)

    def _getirir(arg: str) -> bool:
        k = [x for x in shlex.split(arg) if not x.startswith("--")]
        return any(s in (".", "./", "docker", "docker/", REL) for s in k[:-1])

    copy_i = [i for i, (ad, a) in enumerate(t) if ad == "COPY" and _getirir(a)]
    assert copy_i, "Dockerfile.backend giriş betiğini imaja kopyalamıyor (çıpa)"
    uygulanan = []
    for ad, arg in t[copy_i[-1] + 1 :]:
        if ad != "RUN":
            continue
        for alt in re.split(r"&&|;", arg):
            if REL not in alt and mutlak not in alt:
                continue
            argv = shlex.split(alt.strip())
            if not argv:
                continue
            yeni = None
            if argv[0] == "sed":
                yeni = _sed_uygula(argv, bayt)
            elif argv[0] == "dos2unix":
                yeni = bayt.replace(b"\r\n", b"\n")
            if yeni is not None:
                bayt = yeni
                uygulanan.append(alt.strip())
    return bayt, uygulanan


def test_ONCUL_windows_checkout_betigi_CRLF_getirir_ya_da_LF_kilitli():
    """Öncül: ölçüm aracının girdisi gerçek. `.gitattributes` `eol=lf` yoksa Windows checkout'u CR taşır (ölçülen: 27 satır)."""
    b = _windows_checkout_baytlari()
    assert b.startswith(b"#!"), "çıpa: betik baytları okunamadı"
    attr = subprocess.run(
        ["git", "check-attr", "eol", "--", REL], cwd=str(KOK), capture_output=True, text=True, timeout=60
    ).stdout
    if "eol: lf" in attr:
        assert b"\r" not in b
    else:
        assert b"\r\n" in b, f"autocrlf=true checkout'u CR üretmedi — araç yanlış ({attr.strip()})"


def test_KRITIK_imajdaki_giris_betigi_CR_TASIMAZ_windows_checkouttan_derlense_bile():
    b, uygulanan = _imajdaki_betik(_windows_checkout_baytlari())
    cr = sum(1 for s in b.split(b"\n") if s.endswith(b"\r"))
    assert cr == 0, (
        f"Windows checkout'undan (core.autocrlf=true; depoda .gitattributes eol=lf YOK) derlenen imajda giriş betiği {cr} satırda CR "
        f"taşır → dash `set -eu\\r` ile düşer, konteyner AÇILMAZ. Dockerfile'da betiğe uygulanan normalizasyon: {uygulanan or 'YOK'}. "
        "Çözüm: `.gitattributes`'a `*.sh text eol=lf` ya da COPY'den sonra `sed -i 's/\\r$//' <betik>`."
    )


# ---------------------------------------------------------------- (2) exec
_KOMUT = 'cat /proc/$PPID/cmdline 2>/dev/null | tr "\\0" " "; echo; echo KOMUT-KOSTU'


def _ebeveyn_cikti(betik_metni: str, ad: str, tmp_path: Path) -> subprocess.CompletedProcess:
    if d412.SH is None:
        pytest.skip("sh yok")
    d = tmp_path / ad
    (d / "birim").mkdir(parents=True)
    kopya = d / f"{ad}.sh"
    kopya.write_bytes(betik_metni.replace(d412._kimlik_yolu(), (d / "birim" / "machine-id").as_posix()).encode("utf-8"))
    return subprocess.run(
        [d412.SH, kopya.as_posix(), "sh", "-c", _KOMUT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def test_KRITIK_giris_betigi_CMDyi_EXEC_eder_kabuk_PID1de_kalmaz(tmp_path):
    metin = d412.BETIK.read_text(encoding="utf-8").replace("\r\n", "\n")
    # Aparat öz-denetimi: exec'SİZ sarıcıda komutun ebeveyni sarıcı kabuktur → adı GÖRÜNMELİ (yoksa araç bu platformda kör).
    oz = _ebeveyn_cikti('#!/bin/sh\nset -eu\n"$@"\n', "zz4b17_execsiz_sarici", tmp_path)
    assert "KOMUT-KOSTU" in oz.stdout and "zz4b17_execsiz_sarici" in oz.stdout, (
        f"ölçüm aracı exec'siz kabuğu göremiyor (/proc yok?) — kapı bu platformda kör: {oz.stdout!r} {oz.stderr[:200]!r}"
    )
    r = _ebeveyn_cikti(metin, "zz4b17_gercek_giris", tmp_path)
    assert r.returncode == 0 and "KOMUT-KOSTU" in r.stdout, (
        f"giriş betiği CMD'yi koşturmadı: {r.stdout!r} {r.stderr[:300]!r}"
    )
    assert "zz4b17_gercek_giris" not in r.stdout, (
        "giriş betiği CMD'yi `exec` ETMİYOR: komutun ebeveyni hâlâ betik kabuğu → konteynerde kabuk PID 1'de kalır, `docker stop` "
        "SIGTERM'i backend'e ulaşmaz (10 sn sonra SIGKILL, düzgün kapanış yok)"
    )


# ---------------------------------------------------------------- (3) ayrı birim
def _veri_dizini() -> str:
    env = " ".join(a for ad, a in d412._dockerfile_talimatlari() if ad == "ENV")
    m = re.search(r"\bPEMF_DATA_DIR=(\S+)", env)
    assert m, "çıpa: Dockerfile.backend ENV PEMF_DATA_DIR yok"
    return m.group(1).strip("'\"")


@pytest.mark.parametrize("rel", d412.COMPOSE_BACKEND)
def test_KRITIK_kimlik_birimi_VERI_biriminden_AYRI_veri_yedegi_sirlari_acmaz(rel):
    veri = _veri_dizini()
    kimlik_dizini = str(PurePosixPath(d412._kimlik_yolu()).parent)
    assert not PurePosixPath(kimlik_dizini).is_relative_to(PurePosixPath(veri)), (
        f"kimlik dizini {kimlik_dizini} veri dizini {veri} ALTINDA → veri yedeği kimliği de taşır"
    )
    belge = yaml.safe_load((KOK / rel).read_text(encoding="utf-8"))
    bulunan = 0
    for ad, servis in belge["services"].items():
        if not str((servis.get("build") or {}).get("dockerfile", "")).endswith("Dockerfile.backend"):
            continue
        kaynak = {}
        for v in servis.get("volumes") or []:
            k, _, kalan = str(v).partition(":")
            kaynak[kalan.split(":")[0]] = k
        assert kimlik_dizini in kaynak and veri in kaynak, f"{rel}:{ad} çıpa: kimlik/veri bağı yok: {kaynak}"
        assert kaynak[kimlik_dizini] != kaynak[veri], (
            f"{rel}:{ad}: makine kimliği ({kimlik_dizini}) VERİ birimine ({kaynak[veri]}) bağlı → yalnız veri yedeği makine kimliğini ve "
            "pemf_secrets.json'u BİRLİKTE taşır; yedeği alan SQLCipher anahtarını çözer (D4.12'nin 'yalnız veri yedeği sırları açmaz' iddiası)"
        )
        bulunan += 1
    assert bulunan, f"{rel}: Dockerfile.backend servisi yok (çıpa)"
