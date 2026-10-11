# -*- coding: utf-8 -*-
"""4B-2.14 (4-B incelemesi A2) — D4.20'nin compose çözüm kapısı iki yerden sızar (ölçüldü, `kayit/k4_compose_kolu_sonda.txt`):

(a) Docker CLI kolu (`D420._compose_config`) `docker compose config` sıfır-dışı dönünce SKIP eder. CLI varken sıfır-dışı = compose-spec dosyayı
    REDDETTİ (`docker compose up` da düşer) → kırmızı olmalı. Ölçüldü: `docker-compose.ai.yml`'de tek boşluk girinti kayması → D4.20 + D4.12 +
    COPY + vault + mikroservis + taşınmış kümesi 53 passed, 6 skipped, rc 0 (HEAD: 54 passed, 5 skipped) — ai compose'u PyYAML ile okuyan başka kapı yok.
(b) CLI'sız ana kol (`test_betikler_ACILIYOR._compose_contextleri`) satır ayrıştırıcıdır: `context` her `build:`'de sıfırlanmaz →
    `dockerfile:` `context:`'ten ÖNCE yazılınca bir önceki servisin bağlamıyla eşlenir (B-10.181'in aynı sınıfı: imaj derlenemez, kapı YEŞİL);
    tırnaklı değer / satır sonu yorumu / kısa `build: <yol>` biçimi de compose-spec'ten ayrışır; YAML'ı bozuk dosyayı sessizce "çözer".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_betikler_ACILIYOR as acil  # noqa: E402
import test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420 as d420  # noqa: E402

_ESKI = b"\r\n    image: pemf-ai\r\n"


def _kirik_ai_compose(tmp_path: Path) -> Path:
    ham = (KOK / "docker" / "docker-compose.ai.yml").read_bytes()
    if ham.count(_ESKI) != 1:  # CRLF'siz kopya (autocrlf) da olabilir
        ham = ham.replace(b"\r\n", b"\n")
        eski, yeni = b"\n    image: pemf-ai\n", b"\n     image: pemf-ai\n"
    else:
        eski, yeni = _ESKI, b"\r\n     image: pemf-ai\r\n"
    assert ham.count(eski) == 1, "VAKUM: ai compose'da `image: pemf-ai` satırı yok — kapıyı güncelle"
    (tmp_path / "docker").mkdir()
    p = tmp_path / "docker" / "docker-compose.ai.yml"
    p.write_bytes(ham.replace(eski, yeni))
    return p


@pytest.mark.skipif(d420.DOCKER is None, reason="Docker CLI yok — (a) yalnız CLI kolu için")
def test_KRITIK_compose_spec_REDDEDINCE_capraz_kol_SKIP_degil_FAIL(tmp_path):
    kirik = _kirik_ai_compose(tmp_path)
    try:
        d420._compose_config(str(kirik))
    except pytest.fail.Exception:
        return  # beklenen: compose-spec reddi KIRMIZI
    except pytest.skip.Exception as e:
        pytest.fail(f"compose-spec dosyayı REDDETTİ ama çapraz kol SKIP etti (sahte yeşil): {str(e)[:200]}")
    pytest.fail("bozuk compose dosyası `docker compose config`'ten geçti — mutant kurulamadı")


def test_KRITIK_ana_kol_YAML_bozuk_compose_u_SESSIZCE_cozmez(tmp_path, monkeypatch):
    kirik = _kirik_ai_compose(tmp_path)
    orj = acil._takipli
    monkeypatch.setattr(acil, "_takipli", lambda d: [str(kirik)] if any("compose" in x for x in d) else orj(d))
    try:
        sonuc = acil._compose_contextleri()
    except Exception:  # noqa: BLE001 — YAML hatası = fail-closed (beklenen)
        return
    pytest.fail(
        f"YAML'ı bozuk compose sessizce çözüldü (CLI'sız kapı YEŞİL kalır): {sorted(Path(k).name for k in sonuc)}"
    )


def test_KRITIK_ana_kol_compose_spec_ile_AYNI_cozer_SIRA_TIRNAK_YORUM_KISA_bicim(tmp_path, monkeypatch):
    (tmp_path / "docker").mkdir()
    (tmp_path / "apps" / "ui").mkdir(parents=True)
    compose = tmp_path / "docker" / "compose-sira.yml"
    compose.write_text(
        "services:\n"
        "  a:\n    build:\n      context: ..\n      dockerfile: docker/Dockerfile.a\n"
        "  b:\n    build:\n      dockerfile: docker/Dockerfile.b\n      context: ../apps/ui\n"
        "  c:\n    build:\n      context: \"..\"\n      dockerfile: docker/Dockerfile.c   # yorum\n"
        "  d:\n    build: ../apps/ui\n"
        "  e:\n    image: hazir-imaj\n",
        encoding="utf-8",
    )
    orj = acil._takipli
    monkeypatch.setattr(acil, "_takipli", lambda d: [str(compose)] if any("compose" in x for x in d) else orj(d))
    t, ui = tmp_path.resolve(), (tmp_path / "apps" / "ui").resolve()
    beklenen = {  # compose-spec: context compose dosyasının dizinine, dockerfile context'e göre; varsayılan `Dockerfile`
        str((t / "docker" / "Dockerfile.a").resolve()): t,
        str((ui / "docker" / "Dockerfile.b").resolve()): ui,
        str((t / "docker" / "Dockerfile.c").resolve()): t,
        str((ui / "Dockerfile").resolve()): ui,
    }
    arac = acil._compose_contextleri()

    def _g(p) -> str:
        s = str(p)
        return s[len(str(t)) + 1 :] if s.startswith(str(t)) else s

    assert arac == beklenen, (
        "ölçüm aracı compose-spec'ten AYRIŞTI:\n  arac    = "
        + str({_g(k): _g(v) for k, v in arac.items()})
        + "\n  beklenen= "
        + str({_g(k): _g(v) for k, v in beklenen.items()})
    )
