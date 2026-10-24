# Author: mertaygn, cglrgrkn
"""D3.45 (B-10.95) + Y33 — AI ağırlıklarının SHA-256 manifesti SÜRÜMLÜ (izlenen) ve takipli ağırlıklar HER KOŞUDA ona göre doğrulanır.

ÖLÇÜLEN KÖR KAPI (2026-10-25): `scripts/model_butunluk.py` doğru çalışıyordu ama hiçbir test / CI adımı onu koşmuyordu; manifest
(`release_assets/ai_models_sha256.json`) `.gitignore`'daki `release_assets/*` yüzünden SÜRÜM DIŞIYDI → `docs/VERIFICATION.md` §6'daki
"✅ DOĞRULANDI" elle yapılmış bir koşumun kaydıydı; bozulan / değişen ağırlığı hiçbir otomatik adım görmüyordu.
SÖZLEŞME: manifest izlenir (Y33 — izlenmeyen 46 ağırlığın listesi de depoda); git'te izlenen her ağırlık manifestte ve bayt-birebir
(ÜRÜNÜN doğrulayıcısıyla: `model_butunluk.dogrula`); doğrulayıcı tek baytlık bozulmayı yakalar. Takipsiz ağırlıklar ortamda varsa aynı
çağrıda denetlenir (yoksa "başka kökten çözülür" — doğrulayıcının kendi kuralı).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "scripts"))
import model_butunluk as mb  # noqa: E402


def _git(*a: str) -> list[str]:
    r = subprocess.run(["git", "-C", str(KOK), *a], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        pytest.skip(f"git yok / depo değil: {r.stderr.strip()[:120]}")
    return [x for x in r.stdout.split("\0") if x]


def _takipli() -> list[str]:
    on = "release_assets/ai_models/"
    return sorted(
        p[len(on) :] for p in _git("ls-files", "-z", "--", on) if Path(p).suffix.lower() in mb.AGIRLIK_UZANTILARI
    )


def test_KRITIK_D3_45_manifest_SURUMLU_Y33():
    # `check-ignore --no-index`: 0 = yok sayılıyor (sürüm dışı), 1 = izlenebilir; dizin durumundan bağımsız (.gitignore kuralı).
    r = subprocess.run(
        ["git", "-C", str(KOK), "check-ignore", "-q", "--no-index", "release_assets/ai_models_sha256.json"],
        capture_output=True,
    )
    if r.returncode not in (0, 1):
        pytest.skip("git yok / depo değil")
    assert r.returncode == 1, "manifest .gitignore'da — sürüm dışı (Y33); bütünlük kapısı elle koşuma kalır"
    assert mb.MANIFEST.is_file(), f"manifest yok: {mb.MANIFEST}"


def test_KRITIK_D3_45_her_takipli_agirlik_manifestte_ve_BAYT_BIREBIR(capsys):
    beklenen = __import__("json").loads(mb.MANIFEST.read_text(encoding="utf-8"))["dosyalar"]
    takipli = _takipli()
    assert len(takipli) >= 10, f"takipli ağırlık sayısı düştü: {takipli}"
    assert not (set(takipli) - set(beklenen)), (
        f"manifestte olmayan takipli ağırlık: {sorted(set(takipli) - set(beklenen))}"
    )
    assert mb.dogrula(mb.KAYNAK, tam=False) == 0, capsys.readouterr().out[-1500:]
    out = capsys.readouterr().out
    for rel in takipli:
        p = mb.KAYNAK / rel
        assert p.stat().st_size == beklenen[rel]["bayt"] and mb._ozet(p) == beklenen[rel]["sha256"], (
            f"{rel} manifestle aynı değil"
        )
    assert "BOZUK" not in out


def test_KRITIK_D3_45_dogrulayici_TEK_BAYTLIK_bozulmayi_yakalar(tmp_path, capsys):
    kopya = tmp_path / "ai_models"
    for rel in _takipli():
        (kopya / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mb.KAYNAK / rel, kopya / rel)
    assert mb.dogrula(kopya, tam=False) == 0
    hedef = kopya / next(r for r in _takipli() if r.endswith(".onnx"))
    veri = bytearray(hedef.read_bytes())
    veri[len(veri) // 2] ^= 0x01  # boyut AYNI, içerik farklı
    hedef.write_bytes(bytes(veri))
    capsys.readouterr()
    assert mb.dogrula(kopya, tam=False) == 1, "tek baytlık bozulma (aynı boyut) yakalanmadı"
    assert "BOZUK" in capsys.readouterr().out
