# Author: mertaygn, cglrgrkn
"""D3.23 (B-9.19) + İG-9.10 + İG-9.12 — backend Docker imajı (`COPY . .`) build makinesinin GERÇEK sırlarını ve dev artefaktları ALMAZ.

ÖLÇÜLEN (HEAD, moby/patternmatcher anlamı — `test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420._dislanir_mi`): kök-çapalı desenler
alt dizinleri görmüyordu → `build_tools/secrets_backup.py::_KALEMLER` (firmware Secrets.h / data/config.json, bulut E-stop aynası kimliği)
+ `apps/web/.vercel/.env.production.local`, `apps/web/.git.arsiv-…/config`, `build_tools/_static_password.py`, alt dizin `.env.*` → 11
yolun 10'u bağlamda. Bağlam ~12,7 GB (alt dizin APK / ZIP / EXE / günlük, node_modules — İG-9.10). Gerçek `docker build` KOŞULMAZ
(indirme) → ölçü desen anlamıyla; `[ERTELENDİ — indirme]` gerçek imaj denetimi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420 as d420  # noqa: E402 — moby ölçücüsü (belgeyle kalibre)

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "build_tools"))
import secrets_backup as sb  # noqa: E402

IGNORE = KOK / "docker" / "Dockerfile.backend.dockerignore"


def _sir_yollari() -> list[str]:
    kalem = {str(y.relative_to(sb.GUII)).replace("\\", "/") for _, y, _ in sb._KALEMLER if sb.GUII in y.parents}
    return sorted(kalem | set(sb._SW_DOSYALAR))


@pytest.mark.parametrize(
    "yol",
    [
        *_sir_yollari(),
        "apps/web/.vercel/.env.production.local",
        "apps/web/.env.production.local",
        "apps/web/.git.arsiv-20260901/config",
        "build_tools/_static_password.py",
        "apps/backend/.env.local",
        "release-keystore/pemf-release.jks",
    ],
)
def test_KRITIK_D3_23_sir_yolu_backend_imaj_BAGLAMINDAN_dislanir(yol):
    assert d420._dislanir_mi(yol, d420._desenler(IGNORE)), f"{yol} backend imajına GİRİYOR (COPY . .)"


@pytest.mark.parametrize(
    "yol",
    [
        "release_assets/PEMF_Vet_Mobil.apk",
        "pemf-app-packages/base-deps.zip",
        "apps/ui/node_modules/react/index.js",
        "apps/backend/logs/backend_service.log",
        "launcher/target/release/x.exe",
    ],
)
def test_KRITIK_IG_9_10_alt_dizin_artefaktlari_dislanir(yol):
    assert d420._dislanir_mi(yol, d420._desenler(IGNORE)), f"{yol} bağlamda (imaj şişer / günlük sızar)"


@pytest.mark.parametrize(
    "yol",
    [
        "apps/backend/backend_service.py",
        "ai_hub/__init__.py",
        "requirements-docker.txt",
        "docker/backend-entrypoint.sh",
    ],
)
def test_KARSIT_D3_23_calisma_kodu_IMAJA_girer(yol):
    assert not d420._dislanir_mi(yol, d420._desenler(IGNORE)), f"{yol} dışlandı — imaj çalışmaz"


def test_KRITIK_D3_23_sir_kalem_listesi_BOS_degil():
    assert len(_sir_yollari()) >= 5, "VAKUM: secrets_backup kalemleri okunamadı"
