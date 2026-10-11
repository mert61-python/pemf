# -*- coding: utf-8 -*-
"""D4.20 (B-10.181 · B-10.203) — Docker sevk hattında F1b (`pf/` → `apps/ui/`) artığı kalmaz.

ARIZA: (1) `docker-compose.yml` / `docker-compose.micro.yml` frontend servisi `context: ../apps/ui` +
`dockerfile: ../docker/Dockerfile.frontend` diyor. Compose-spec'te dockerfile yolu BAĞLAMA göredir → `apps/docker/Dockerfile.frontend`
(YOK): frontend imajı derlenemiyor. COPY kapısı (`test_betikler_ACILIYOR`) çözülemeyen dockerfile'ı `continue` ile atlıyordu → hiçbir kapı
görmedi. (2) `docker/Dockerfile.backend.dockerignore` (ve `Dockerfile.ai.dockerignore`, kök `.dockerignore`) arayüz kaynağını hâlâ eski `pf/`
adıyla dışlıyor → `apps/ui` kaynağı backend/AI imajına giriyor.

Ölçüm: `test_betikler_ACILIYOR._compose_contextleri` (GERÇEK işlev; compose'dan OKUR) + Docker CLI varsa `docker compose ... config` (daemon
GEREKMEZ; compose-spec'in kendi çözümü) çapraz kolu. Taşınmış dizin tablosu tek kaynaktan: `test_tasinmis_dizin_calisan_kodda_YOK.TASINMIS`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_betikler_ACILIYOR import _compose_contextleri, _takipli
from test_tasinmis_dizin_calisan_kodda_YOK import TASINMIS

KOK = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker")


def _takipli_mi(yol: str | Path) -> bool:
    try:
        rel = Path(yol).resolve().relative_to(KOK).as_posix()
    except ValueError:
        return False
    return rel in set(_takipli([rel]))


def test_KRITIK_compose_build_dockerfile_TAKIPLI_dosyaya_cozulur_B10_181():
    ctx = _compose_contextleri()
    assert len(ctx) >= 3, f"VAKUM: compose'dan yalnız {len(ctx)} build okundu"
    cozulmeyen = sorted(str(Path(df).relative_to(KOK)) for df in ctx if not _takipli_mi(df))
    assert not cozulmeyen, (
        f"compose build dockerfile yolu (bağlama göre) takipli bir dosyaya ÇÖZÜLMÜYOR: {cozulmeyen} — imaj derlenemez"
    )


def _compose_config(dosya: str) -> dict:
    r = subprocess.run(
        [DOCKER, "compose", "-f", dosya, "config", "--format", "json"],
        cwd=str(KOK / "docker"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if r.returncode != 0:
        # 4B-2.14: CLI varken sıfır-dışı = compose-spec dosyayı REDDETTİ (`docker compose up` da düşer) → KIRMIZI.
        # Yalnız `compose` eklentisi yoksa (ortam) atlanır.
        v = subprocess.run(
            [DOCKER, "compose", "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if v.returncode != 0:
            pytest.skip(f"docker compose eklentisi yok: {v.stderr.strip()[:200]}")
        pytest.fail(f"compose-spec dosyayı REDDETTİ ({dosya}) — imaj derlenemez: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


@pytest.mark.skipif(DOCKER is None, reason="Docker CLI yok — compose-spec kolu (yalnız `config`, daemon gerekmez)")
@pytest.mark.parametrize("dosya", ["docker-compose.yml", "docker-compose.micro.yml", "docker-compose.ai.yml"])
def test_KRITIK_compose_spec_kendi_cozumu_ile_AYNI_ve_dosya_VAR(dosya):
    """Ölçüm aracının (`_compose_contextleri`) compose-spec'le aynı çözdüğü kanıtlanır; çözülen dockerfile diskte ve takipli olmalı."""
    ctx = _compose_contextleri()
    for ad, servis in _compose_config(dosya)["services"].items():
        b = servis.get("build")
        if not b:
            continue
        df = (Path(b["context"]) / b.get("dockerfile", "Dockerfile")).resolve()
        assert df.is_file() and _takipli_mi(df), f"{dosya}:{ad} dockerfile çözümü {df} — dosya YOK/takipsiz"
        assert ctx.get(str(df)) == Path(b["context"]).resolve(), (
            f"{dosya}:{ad} — test aracının çözümü compose-spec'ten AYRIŞTI: {ctx.get(str(df))} != {b['context']}"
        )


def _ignore_dosyalari() -> list[str]:
    return [r for r in _takipli(["*.dockerignore", ".dockerignore", "**/.dockerignore"])]


def _desenler(yol: Path) -> list[str]:
    return [
        s.strip()
        for s in yol.read_text(encoding="utf-8", errors="replace").splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]


def test_KRITIK_ignore_dosyalarinda_TASINMIS_dizin_adi_YOK_B10_203():
    eskiler = set(TASINMIS)
    assert eskiler, "VAKUM: taşınmış dizin tablosu boş"
    dosyalar = _ignore_dosyalari()
    assert len(dosyalar) >= 3, f"VAKUM: yalnız {dosyalar}"
    bayat = [
        f"{rel}: {d}"
        for rel in dosyalar
        for d in _desenler(KOK / rel)
        if set(d.lstrip("!").strip("/").split("/")) & eskiler
    ]
    assert not bayat, f".dockerignore girdisi TAŞINMIŞ dizinin ESKİ adını dışlıyor (yeni yer imaja girer): {bayat}"


def _desen_regex(desen: str) -> re.Pattern[str]:
    """moby/patternmatcher anlamı (4B-2.12; Docker belgesi örnekleriyle kalibre): `*` ve `?` `/` GEÇMEZ, `**/` her derinlik (sıfır dahil),
    `**` her şey, `[...]` tek ayraç-dışı karakter; desen bir DİZİNİ eşlerse altındaki her şey de dışlanır. (Eski `fnmatch` yaklaşığı `*`'ı
    `/` üzerinden geçiriyordu: `*/temp*` → `a/b/temp` yanlış "dışlanır".)"""
    d = desen.strip("/")
    out, i = "", 0
    while i < len(d):
        if d.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif d.startswith("**", i):
            out, i = out + ".*", i + 2
        elif d[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif d[i] == "?":
            out, i = out + "[^/]", i + 1
        elif d[i] == "[" and d.find("]", i + 1) > i:
            j = d.find("]", i + 1)
            out, i = out + "(?:(?!/)" + d[i : j + 1] + ")", j + 1
        else:
            out, i = out + re.escape(d[i]), i + 1
    return re.compile("^" + out + "(?:/.*)?$")


def _dislanir_mi(rel_yol: str, desenler: list[str]) -> bool:
    """Docker `.dockerignore` anlamı: son eşleşen kazanır; `!` geri alır; dizin deseni altını kapsar (moby `_desen_regex`)."""
    sonuc = False
    for d in desenler:
        ters = d.startswith("!")
        if _desen_regex(d.lstrip("!").strip()).match(rel_yol):
            sonuc = not ters
    return sonuc


def test_KRITIK_backend_ve_AI_imaji_ARAYUZ_kaynagini_DISLAR_B10_203():
    """Bir imajın build bağlamı başka bir servisin bağlamını İÇERİYORSA (kök ⊃ apps/ui) o alt bağlam etkin ignore dosyasında dışlanmalı."""
    ctx = _compose_contextleri()
    baglamlar = set(ctx.values())
    sizan, bakilan = [], 0
    for df, taban in ctx.items():
        ignore = Path(df + ".dockerignore")
        if not ignore.is_file():
            ignore = taban / ".dockerignore"
        desenler = _desenler(ignore) if ignore.is_file() else []
        for alt in baglamlar:
            if alt == taban or taban not in alt.parents:
                continue
            rel = alt.relative_to(taban).as_posix()
            ornekler = _takipli([f"{rel}/package.json"]) or _takipli([f"{rel}/*"])[:1]
            assert ornekler, f"VAKUM: {rel} altında takipli dosya yok"
            bakilan += 1
            if not _dislanir_mi(ornekler[0], desenler):
                sizan.append(f"{Path(df).name} ({ignore.name}) → {ornekler[0]}")
    assert bakilan >= 2, f"VAKUM: yalnız {bakilan} (imaj, alt bağlam) çifti sınandı"
    assert not sizan, f"arayüz kaynağı backend/AI imajına GİRİYOR: {sizan}"
