# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · Y4 (1-C bağımsız inceleme i1-F1) — "Sıfırla", mandal KURULUYKEN alınmış bir START niyetini DİRİLTEMEZ.

ÖLÇÜLEN KUSUR (c5b3c04, i1 3 koşu × 30/30): `analyze_landmark` (AI (Auto)) sürüş niyetinin neslini istek girişinde
alır; mandal yalnız sürüş anında denetlenir. `estop_mandali.sifirla()` nesli DEĞİŞTİRMİYORDU ("uçuştaki eski niyetler
acil durdurmanın artırdığı nesille zaten bayattır" — bu yalnız E-stop'tan ÖNCE alınmış niyetler için doğru). Mandal
kuruluyken alınan niyetin nesli zaten E-stop SONRASI nesildir → çıkarım sürerken basılan "Sıfırla"dan sonra niyet
"taze" görünür ve YENİ bir START olmadan 7 bobini %31 duty ile 30 dk sürer. Y4 iki yerden çiğnenir: "mandal kuruluyken
hiçbir START kabul edilmez" ve "sıfırlama kendi başına yeniden başlatmaz".

KAPI: GERÇEK `analyze_landmark` → `_drive_landmark_auto` → `start_ai_session` → `start_all_coils` → paket kurucu;
sahte olan yalnız model (çıkarım bir Event'te BLOKLANIR = çıkarım penceresi), FGS (sabit 2) ve istek kaynağının
"yerel" sayılması (TestClient'ın "testclient"ı yerel değil). Sıra: E-stop → landmark `auto_adjust` (mandallı) → çıkarım
sürerken Sıfırla → çıkarım biter. ≥30 deneme; ölçüt donanıma GİDEN duty>0 paket + çalışan bobin + ESP START yayını.
KARŞIT kollar: Sıfırla YOKKEN aynı istek reddedilir; Sıfırla'dan SONRA verilen YENİ istek sürer (aparat sürebiliyor).

⚠️ D1.88 (A-19): taşıyıcı yol (landmark `auto_adjust` → `_drive_landmark_auto`) KALDIRILDI; üç N30 kolu silindi. Özellik
("Sıfırla, mandallıyken alınmış niyeti diriltmez") kalan START yollarında `test_estop_NIYET_nesli_ISTEK_VARISINDA.py`
(tekil / batch / legacy / seans / AI Pro start × N30) ve aşağıdaki birim kolla kilitli; landmark ucu artık START
üretmez (`test_fgs_otonom_biofeedback_AI_Pro_MUHRUNE_bagli_A19.py`).
"""

from __future__ import annotations


def test_KRITIK_sifirla_nesli_ARTIRIR_mandal_yokken_ARTIRMAZ():
    """Birim: mandal kuruluyken Sıfırla nesli artırır (mandallıyken alınmış her niyet bayatlar); mandal yokken
    Sıfırla hiçbir şeyi değiştirmez (boş Sıfırla uçuştaki geçerli niyetleri öldürmesin)."""
    from utils import estop_mandali as em

    em.sifirla("test-onkosul")
    n0 = em.nesil()
    assert em.sifirla("test") is False and em.nesil() == n0, "mandal yokken Sıfırla nesli değiştirdi"
    em.mandalla("test")
    n1 = em.nesil()
    assert n1 == n0 + 1
    assert em.sifirla("test") is True
    assert em.nesil() == n1 + 1, "mandal kuruluyken Sıfırla nesli ARTIRMADI (mandallıyken alınmış niyet diriliyor)"
    assert em.baslatma_engeli(n1) == em.NESIL_MESAJI
    assert em.baslatma_engeli(em.nesil()) == ""
