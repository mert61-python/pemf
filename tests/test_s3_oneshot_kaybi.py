# Author: mertaygn, cglrgrkn
"""[5.12] S3 TEK-ATIMLIK OLAY KAYBI — statusQueue doluyken (sahip onayı 2026-08-20).

Ölçülen kusur: Control görevi tek-atımlık olayları (thermalStopEvent, selfTestCompleted, ACK)
`consume*` ile YIKICI tüketip statusQueue'ya 0-timeout `xQueueSend` ile veriyordu; kuyruk doluysa
mesaj düşer ve tüketilmiş olay bir daha ÜRETİLMEZ — termal-kesme olayı operatöre hiç ulaşmayabilir,
E-stop ACK'i kaybolursa backend sahte "onay gelmedi" alarmı üretir (fail-safe ama gürültü).
Yorumdaki "overwrite yapmayı deneriz" vaadi hiç gerçeklenmemişti. Pencere dar (mdns 2000 ms bloğu,
5 dk'da bir) ama termal-kesme tam da olağanüstü anlarda üretilir — pencereyle çakışması olasıdır.

DÜZELTME: (a) durum mesajı gönderilemezse tek-atımlık olaylar CoilController'a GERİ KURULUR
(`restore*` — bir sonraki 200 ms turunda yeniden denenir); (b) ACK gönderimi 0 yerine SINIRLI
bekleme (pdMS_TO_TICKS) kullanır — kontrol döngüsü 200 ms periyotludur, kısa blok güvenlidir.
Karşıt-kanıt: restore YALNIZ başarısızlık dalında — normal yolda tek tüketim (çift yayın yok).

⚠️ C bu makinede derlenemez — kapılar yorum-soyulmuş yapısal; REFLASH zaten planlı (15-16. parti).
"""

from __future__ import annotations

import re
from pathlib import Path

from c_soyucu import c_soy as _c_soy  # 17. parti: string-bilinçli soyucu

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"


def _basarisizlik_blogu(ino: str) -> str:
    """`if (xQueueSend(statusQueue, &status, ...) != pdTRUE) { ... }` bloğunun İÇİ — küme-ayrıştırmalı.

    17. parti sertleştirmesi (adversaryal test-gaming bulgusu): eski 500-karakter penceresi kontrol
    akışına KÖRDÜ — restore çağrıları erişilmez bir ölü dala taşındığında test yeşil kalıyordu
    (ampirik kanıtlandı). Artık restore'lar TAM OLARAK başarısızlık bloğunun içinde aranır."""
    m = re.search(r"if\s*\(\s*xQueueSend\(statusQueue,\s*&status,[^)]*\)\s*!=\s*pdTRUE\s*\)\s*\{", ino)
    assert m, "durum-gönderimi başarısızlık dalı bulunamadı (yapı değişti mi?)"
    i = m.end()
    derinlik = 1
    j = i
    while j < len(ino) and derinlik > 0:
        if ino[j] == "{":
            derinlik += 1
        elif ino[j] == "}":
            derinlik -= 1
        j += 1
    return ino[i : j - 1]


def test_KRITIK_5_12_durum_gonderilemezse_olaylar_GERI_KURULUR():
    ino = _c_soy((S3 / "esps3_pemf_coil.ino").read_text(encoding="utf-8", errors="replace"))
    dal = _basarisizlik_blogu(ino)
    assert "restoreThermalStopEvent" in dal, (
        "durum kuyruğa sığmayınca TÜKETİLMİŞ termal-kesme olayı BAŞARISIZLIK DALINDA geri "
        "kurulmuyor — olay sonsuza dek kaybolur, operatör termal kesmeyi hiç görmeyebilir (bulgu [5.12])"
    )
    assert "restoreSelfTestEvent" in dal, "self-test olayı da başarısızlık dalında geri kurulmalı"


def test_KRITIK_5_12_ack_gonderimi_SINIRLI_bekler():
    ino = _c_soy((S3 / "esps3_pemf_coil.ino").read_text(encoding="utf-8", errors="replace"))
    m = re.search(r"xQueueSend\(statusQueue,\s*&ackMsg,\s*([^)]*\))\s*\)", ino)
    assert m, "ACK gönderimi bulunamadı"
    # 17. parti: makro ADI yetmez — `pdMS_TO_TICKS(0)` özgün 0-timeout kusurunu birebir geri
    # getirirdi ve eski kapı yeşil kalıyordu (ampirik kanıtlandı). Pozitif tick ŞART.
    assert re.search(r"pdMS_TO_TICKS\(\s*[1-9][0-9]*\s*\)", m.group(1)), (
        f"ACK sınırlı-POZİTİF bekleme kullanmıyor ({m.group(1).strip()!r}) — kuyruk dolu "
        "penceresinde E-stop ACK'i düşer, backend sahte 'onay gelmedi' alarmı üretir (bulgu [5.12])"
    )


def test_KARSIT_KANIT_restore_yalniz_basarisizlik_dalinda():
    """Aşırı-düzeltme koruması: restore çağrıları TEK yerde ve o yer BAŞARISIZLIK DALI — normal
    yolda çift tüketim/çift yayın üretmemeli. consume* çağrıları da tekil kalmalı."""
    ino = _c_soy((S3 / "esps3_pemf_coil.ino").read_text(encoding="utf-8", errors="replace"))
    assert ino.count("restoreThermalStopEvent") == 1, "restoreThermalStopEvent birden çok yerde"
    assert ino.count("restoreSelfTestEvent") == 1, "restoreSelfTestEvent birden çok yerde"
    assert ino.count("consumeThermalStopEvent") == 1, "termal olay birden çok yerde tüketiliyor"
    assert ino.count("consumeSelfTestEvent") == 1, "self-test olayı birden çok yerde tüketiliyor"


def test_KARSIT_KANIT_restore_metodlari_dogru_bayraklari_kurar():
    """CoilController restore metodları gerçekten pending bayraklarını geri kurmalı (boş gövde
    kapıyı kandırmasın)."""
    cc = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    i = cc.index("restoreThermalStopEvent")
    assert "_thermalStopPendingEvent = true" in cc[i : i + 200], "restoreThermalStopEvent bayrağı kurmuyor"
    j = cc.index("restoreSelfTestEvent")
    blok = cc[j : j + 260]
    assert "_selfTestCompletedPendingEvent = true" in blok and "_selfTestPassed" in blok, (
        "restoreSelfTestEvent sonucu ve bayrağı geri kurmuyor"
    )
