# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.69 (B-7.27 · B-7.28) — başlatıcıda tarayıcının yerel `confirm()` / `alert()` / `prompt()` kutusu YOK; güvenlik duvarı uyarısı sözlükte.

Kusur (B-7.27): arka plan indirmesini İPTAL eden (inen ≤1,4 GB'ı SİLEN) tek onay `if (!confirm(t().bgCancelConfirm)) return;` ile
tarayıcının yerel kutusunda soruluyordu — uygulamanın kendi onay modalı (`askConfirm`: dil / görsel kimlik, odak GÜVENLİ varsayılanda)
varken. METIN-KILAVUZU §6: "Tarayıcının confirm/alert kutuları kullanılmaz."
B-7.28: `firewallKontrol` gövdesindeki uyarı ve "İzin ver (yönetici)" düğmesi sözlük dışında sabit Türkçeydi (EN kipte Türkçe görünür) —
I18N-P1'de kataloğa taşındı (`ui.fwEngel` / `ui.fwKuralYok` / `ui.fwIzinVer`); bu kapı geri gelmesini kilitler.

Gerçek tarayıcı / Tauri BAŞLATILMAZ: betik yorumları soyulmuş metin üzerinde (dize-bilinçli soyucu) ölçülür.
"""

from __future__ import annotations

import re
from pathlib import Path

from i18n_yardimci import launcher_ui as ui
from test_client_arayuz_sade_dil import _js_dizgeleri, _soy

KOK = Path(__file__).resolve().parent.parent
UI = KOK / "launcher" / "app" / "ui" / "index.html"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def _betik() -> str:
    src = _soy(UI.read_text(encoding="utf-8"))
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", src, flags=re.S | re.I))


def _islev_govdesi(betik: str, ad: str) -> str:
    m = re.search(rf"(?:async\s+)?function\s+{re.escape(ad)}\s*\([^)]*\)\s*\{{", betik)
    assert m, f"index.html'de `{ad}` işlevi bulunamadı"
    derinlik, i = 1, m.end()
    while i < len(betik) and derinlik:
        derinlik += {"{": 1, "}": -1}.get(betik[i], 0)
        i += 1
    return betik[m.end() : i - 1]


def test_KRITIK_yerel_confirm_alert_prompt_CAGRISI_YOK_D6_69():
    """Yorum soyulmuş betikte `confirm(` / `alert(` / `prompt(` (ya da `window.` önekli) çağrısı kalmaz; `askConfirm(` bunlardan değildir."""
    kotu = [
        (m.group(0), _betik().count("\n", 0, m.start()) + 1)
        for m in re.finditer(r"(?<![\w.$])(?:window\s*\.\s*)?(?:confirm|alert|prompt)\s*\(", _betik())
    ]
    assert not kotu, (
        f"başlatıcı tarayıcının yerel kutusunu kullanıyor (METIN-KILAVUZU §6 — kendi modalı `askConfirm`): {kotu}"
    )


def test_KRITIK_indirme_iptali_KENDI_modaliyla_ve_GUVENLI_dugmelerle_sorulur_D6_69():
    b = _betik()
    i = b.find("btnIptal.onclick")
    assert i != -1, "İptal düğmesinin işleyicisi bulunamadı"
    govde = b[i : i + 900]
    assert re.search(r"askConfirm\(\s*t\(\)\.bgCancelTitle\s*,\s*t\(\)\.bgCancelConfirm\s*,", govde), (
        f"indirme iptali kendi onay modalıyla (askConfirm, başlık + kayıp metni) sorulmuyor:\n{govde[:400]}"
    )
    assert "danger: true" in govde and "yesLabel: t().bgCancelYes" in govde and "noLabel: t().bgCancelNo" in govde, (
        "silen onayın düğmeleri ne yaptığını söylemiyor / tehlike biçiminde değil (düğme gerçeği söylesin)"
    )
    # İptalin YAN ETKİSİ yalnız onay geri çağrısının İÇİNDE (onaysız yolda cancel_install çağrılmaz)
    j = govde.find("askConfirm(")
    assert j != -1 and govde.find('invoke("cancel_install")') > j, "cancel_install onay geri çağrısının DIŞINDA"
    for dil in ("tr", "en"):
        for k in ("bgCancelTitle", "bgCancelYes", "bgCancelNo", "bgCancelConfirm"):
            assert ui(dil).get(k), f"ui.{k} ({dil}) boş — düğme / başlık undefined görünür"


def test_KRITIK_guvenlik_duvari_uyarisi_SOZLUKTE_sabit_Turkce_YOK_D6_69():
    govde = _islev_govdesi(_betik(), "firewallKontrol")
    sabit = [s for s in _js_dizgeleri(govde) if TR_HARF.search(s)]
    assert not sabit, f"firewallKontrol'de sözlük dışı Türkçe dize (EN kipte Türkçe görünür): {sabit}"
    for k in ("fwEngel", "fwKuralYok", "fwIzinVer"):
        assert f"t().{k}" in govde, f"firewallKontrol `t().{k}` kullanmıyor"
        assert ui("tr").get(k) and ui("en").get(k) and not TR_HARF.search(ui("en")[k]), f"ui.{k} iki dilde dolu değil"


def test_KARSIT_askConfirm_odagi_GUVENLI_varsayilana_tasir():
    """Kendi modalın üstünlüğü: odak "Vazgeç" / "İndirmeye devam et"te (Enter yanlışlıkla onaylamaz)."""
    govde = _islev_govdesi(_betik(), "askConfirm")
    assert 'openModal("confirm", "confirm-no")' in govde, "askConfirm odağı güvenli varsayılana (confirm-no) taşımıyor"
