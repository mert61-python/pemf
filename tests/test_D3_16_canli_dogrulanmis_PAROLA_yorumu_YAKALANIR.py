# Author: mertaygn, cglrgrkn
"""D3.16 (B-6.24 · A-18) — kaynak yorumundaki "canlı doğrulanmış" düz kimlik bilgisi HEAD'den kaldırıldı ve bu biçimi yakalayan özel
gitleaks kuralı (`pemf-canli-dogrulanmis-parola-yorumu`) var.

ÖLÇÜLEN (HEAD): `apps/ui/src/screens/AuthScreen.tsx` yorumunda `Canlı doğrulandı: "<değer>" 200` biçiminde canlı doğrulanmış bir
parola; depo config'iyle gitleaks 0 bulgu veriyordu (düşük entropi — varsayılan kurallar kör). DEĞER HİÇBİR ÇIKTIYA BASILMAZ: kör kapı
GERÇEK OLMAYAN rastgele bir parolayla ölçülür. Rotasyon + geçmiş temizliği sahibin eylemidir (A-18; force-push gerektirir).
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from test_gitleaks_config_derlenir import _bulgu_sayisi  # noqa: F401 — gerçek gitleaks + depo config'i (D3.02 bulucusu)

KOK = Path(__file__).resolve().parents[1]


def _kural_regex() -> re.Pattern:
    toml = (KOK / ".gitleaks.toml").read_text(encoding="utf-8")
    i = toml.index('id = "pemf-canli-dogrulanmis-parola-yorumu"')
    m = re.search(r"regex = '''(.*?)'''", toml[i:])
    assert m, "kuralın regex'i yok"
    return re.compile(m.group(1))


def test_KRITIK_D3_16_gercek_gitleaks_canli_dogrulanmis_yorumu_YAKALAR(tmp_path):
    sahte = "Dg" + secrets.token_hex(5)  # GERÇEK OLMAYAN
    yorum = f'    # (Canlı doğrulandı: "{sahte}" 200, "{sahte} " 400.)\n'
    assert _bulgu_sayisi(tmp_path, yorum) >= 1, "özel kural canlı doğrulanmış parola yorumunu GÖRMÜYOR"


def test_KARSIT_D3_16_degersiz_anlatim_YAKALANMAZ(tmp_path):
    assert (
        _bulgu_sayisi(tmp_path, "    # (Canlı doğrulandı: kırpılmış parola 200, sonunda boşluklu aynısı 400.)\n") == 0
    )


def test_KRITIK_D3_16_arayuz_kaynaginda_bu_bicim_YOK():
    r = _kural_regex()
    isabet = [
        str(p.relative_to(KOK))
        for p in (KOK / "apps" / "ui" / "src").rglob("*.ts*")
        if r.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not isabet, f"canlı doğrulanmış kimlik bilgisi yorumu kaynakta duruyor (değer basılmadı): {isabet}"
