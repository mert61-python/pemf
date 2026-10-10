# -*- coding: utf-8 -*-
"""E2-3.1 (2-E incelemesi A3) — `vault_emanet.py --tatbikat` token'sız ve ETKİLEŞİMSİZ (stdin = NUL) koşunca ASILMAZ; "SINANMADI" der.

D2.E05 sözleşmesi: token verilmezse (ve etkileşimli konsol yoksa) tatbikat "kurtarma token'i SINANMADI" der, çıkış 1, Vault'a
istek YOK. Bekçi `sys.stdin.isatty()` idi — Windows'ta `NUL` bir KARAKTER AYGITIDIR, `isatty()` True döner. Zamanlanmış görev /
otomasyon / `< NUL` ile koşan tatbikat `getpass` → `msvcrt.getwch` yoluna girer: gizli konsolda SONSUZA DEK bekler, konsolsuz
süreçte (DETACHED) %100 CPU ile dönüp belleği büyütür — hiç sonuç / çıkış kodu vermez (ölçüldü, 2-E incelemesi E2-3.1).

Kapı: GERÇEK yorumlayıcıda alt süreç (`betik_alt_sureci.yalitik_ortam`; kökler tmp_path'te, null kasa), stdin = NUL, görünür
pencere AÇILMAZ (CREATE_NO_WINDOW / DETACHED_PROCESS), Vault yerine loopback rastgele portta SAHTE Vault. Zaman aşımında süreç
öldürülür (artık süreç bırakılmaz).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import yalitik_ortam
from sahte_vault_sunucusu import SahteVault

DEPO = Path(__file__).resolve().parents[1]
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NUL aygıtı (isatty True) davranışı")
@pytest.mark.parametrize(
    "bayrak", [CREATE_NO_WINDOW, DETACHED_PROCESS], ids=["gizli_konsol_zamanlanmis_gorev", "konsolsuz_otomasyon"]
)
def test_KRITIK_tatbikat_TOKENSIZ_NUL_girdide_ASILMAZ_SINANMADI_der_E231(tmp_path, bayrak):
    env = yalitik_ortam(tmp_path / "ev")
    env["PEMF_DATA_DIR"] = str(tmp_path / "veri")
    with SahteVault(kok="kok-sahte-e231", kurtarma="kurtarma-sahte-e231") as v:
        env["PEMF_VAULT_ADRES"] = v.adres
        p = subprocess.Popen(
            [sys.executable, str(DEPO / "scripts" / "vault_emanet.py"), "--tatbikat"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(DEPO),
            creationflags=bayrak,
        )
        try:
            ham, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate(timeout=15)
            pytest.fail(
                "tatbikat token'sız + stdin NUL iken 30 sn'de BİTMEDİ (getpass konsolu bekliyor / döngüde) — "
                "'SINANMADI' + çıkış 1 bekleniyordu"
            )
    cikti = ham.decode("utf-8", "replace")
    assert p.returncode == 1 and "SINANMADI" in cikti, f"rc={p.returncode}\n{cikti[-800:]}"
    assert "TATBIKAT BASARILI" not in cikti
    assert v.istekler == [], f"token verilmeden Vault'a istek gitti: {v.istekler}"
