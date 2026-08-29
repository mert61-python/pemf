# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KURULUM HATASI KULLANICIYA ANLAŞILIR SÖYLENİR — saha bildirimi 2026-08-29.

Klinik ekranında kurulum şu ham metinle düştü:

    indirme aktarımı başarısız: https://…/base-deps.zip: Dns Failed: resolve dns name
    'github.com:443': Bilinen böyle bir ana bilgisayar yok. (os error 11001)

İki kusur:
  1. Cümle kullanıcıya NE YAPACAĞINI söylemiyor (ağını mı kontrol etsin, bekleyip tekrar mı
     denesin, destek mi arasın?).
  2. "indirme aktarımı başarısız" ifadesi sorunu SUNUCUDA sandırıyor — oysa `os error 11001`
     (WSAHOST_NOT_FOUND) neredeyse her zaman YEREL bir sebeple oluşur: Wi-Fi düştü, DNS sunucusu
     yanıtsız, uyanma sonrası çözümleyici geç toparlandı. Ölçüldü: aynı makinede sistem DNS'i
     sağlıklıydı (`github.com -> 140.82.121.3`, curl 200) — yani kalıcı bir arıza değildi.

⚠️ Teknik ayrıntı SİLİNMEZ: ikinci satırda, ikincil ağırlıkta korunur — destek mühendisinin
`os error` koduna ihtiyacı var. Kaybolan tek şey, kullanıcının o metni TEK başına görmesi.

⚠️ Bu sınıf hiç ölçülmüyordu: hata YOLLARI test ediliyordu (hangi hata hangi sınıfa düşer,
yeniden denenir mi) ama kullanıcının GÖRDÜĞÜ CÜMLE hiçbir kapıda yoktu.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NET_RS = _KOK / "launcher" / "core" / "src" / "net.rs"
_FLOW_RS = _KOK / "launcher" / "core" / "src" / "flow.rs"


def _ui() -> str:
    return _UI.read_text(encoding="utf-8")


# ── 1) DNS ayrı bir hata sınıfı ──────────────────────────────────────────────


def test_KRITIK_DNS_ayri_hata_sinifi():
    """`Transport` içinde erirse arayüz doğru cümleyi kuramaz."""
    kaynak = _NET_RS.read_text(encoding="utf-8")
    assert "Dns(String)" in kaynak, "DNS hatası ayrı NetError varyantı değil"
    assert re.search(r'#\[error\("ağ adı çözümlenemedi', kaynak), "DNS varyantının mesajı yok"


def test_KRITIK_DNS_varyanti_GERCEKTEN_URETILIYOR():
    """⚠️ ZAYIF-ÇIPA KORUMASI: varyant TANIMLI olabilir ama hiç ÜRETİLMİYORSA hiçbir şey değişmez.

    Ölçüldü: sınıflandırıcıyı `Transport`a geri döndüren mutasyon, yalnız tanıma bakan kapıyı
    YEŞİL bırakıyordu."""
    kaynak = _NET_RS.read_text(encoding="utf-8")
    i = kaynak.find("fn ureq_hatasi")
    assert i != -1, "sınıflandırıcı yok"
    govde = kaynak[i : kaynak.find("\n}", i)]
    assert "NetError::Dns(" in govde, (
        "sınıflandırıcı DNS varyantını hiç ÜRETMİYOR → hata yine 'aktarım başarısız' diye görünür"
    )
    assert re.search(r'Dns Failed|resolve dns name|dns error', govde), "DNS tespiti için hiçbir imza aranmıyor"


def test_KRITIK_DNS_siniflandirmasi_TEK_YERDE():
    """⚠️ İki çağrı yeri (paket indirme + manifest) aynı sınıflandırıcıyı kullanmalı; ayrışırsa
    manifest hatası ham, indirme hatası anlaşılır olur (ya da tersi)."""
    kaynak = _NET_RS.read_text(encoding="utf-8")
    assert "fn ureq_hatasi" in kaynak, "ortak sınıflandırıcı yok"
    # Ham `ureq::Error::Status` eşlemesi YALNIZ o yardımcıda kalmalı.
    i = kaynak.find("fn ureq_hatasi")
    j = kaynak.find("\n}", i)
    disarida = kaynak[:i] + kaynak[j:]
    assert "ureq::Error::Status" not in disarida, (
        "ureq hatası hâlâ birden çok yerde elle eşleniyor → DNS ayrımı bir yolda kaybolur"
    )


def test_KRITIK_DNS_hatasi_YENIDEN_DENENIR():
    """DNS anlık düşüp toparlanabilir; tek denemede pes etmek kullanıcıyı boşuna düşürür."""
    kaynak = _FLOW_RS.read_text(encoding="utf-8")
    i = kaynak.find("fn is_retriable")
    assert i != -1
    govde = kaynak[i : kaynak.find("\n}", i)]
    assert re.search(r"NetError::Dns\(_\)\s*=>\s*true", govde), (
        "DNS hatası geçici sayılmıyor → anlık bir çözümleme hatası kurulumu tamamen düşürür"
    )


# ── 2) Arayüz: kullanıcı cümlesi + korunan teknik ayrıntı ───────────────────


def test_KRITIK_arayuz_HAM_metni_TEK_BASINA_gostermiyor():
    """`fail()` ham hatayı olduğu gibi basıyorsa bulgu geri gelir."""
    m = _ui()
    assert "function hataCumlesi" in m, "hata çeviri katmanı yok"
    i = m.find("function fail(msg)")
    assert i != -1
    govde = m[i : i + 900]
    assert "hataCumlesi" in govde, "fail() çeviri katmanını kullanmıyor → ham metin gösterilir"


@pytest.mark.parametrize("anahtar", ["errDns", "errTimeout", "errSunucu", "errDisk"])
def test_hata_metinleri_IKI_DILDE(anahtar):
    m = _ui()
    assert m.count(f"{anahtar}:") >= 2, f"'{anahtar}' iki dilde tanımlı değil"


def test_KRITIK_DNS_cumlesi_DOGRU_YERI_isaret_ediyor():
    """Kullanıcı ağını kontrol etmeli; "sunucu hatası" demek yanlış yöne sokar."""
    m = _ui()
    i = m.find("errDns:")
    assert i != -1
    cumle = m[i : i + 320]
    assert re.search(r"Wi-?Fi|ağ bağlantı", cumle, re.I), "DNS mesajı kullanıcıyı ağına yönlendirmiyor"
    assert "sunucu hatası" not in cumle, "DNS hatası 'sunucu hatası' diye sunulmuş (yanlış yön)"


def test_KRITIK_teknik_ayrinti_KORUNUYOR():
    """Destek mühendisi `os error 11001` gibi kodu görebilmeli — sadece ikincil ağırlıkta."""
    m = _ui()
    i = m.find("function fail(msg)")
    govde = m[i : i + 900]
    assert "errdetail" in govde, "teknik ayrıntı tamamen atılmış — destek teşhis edemez"
    assert "String(msg)" in govde, "ham mesaj hiç gösterilmiyor"
    assert "#error .errdetail" in m, "teknik ayrıntı için ikincil stil yok"


def test_KARSIT_KANIT_taninmayan_hata_OLDUGU_GIBI_gosterilir():
    """Bilinmeyen bir hata sınıfı sessizce yutulmamalı: ham metin yine görünür."""
    m = _ui()
    i = m.find("function fail(msg)")
    govde = m[i : i + 900]
    assert "else" in govde and "kutu.textContent = String(msg)" in govde, (
        "tanınmayan hatada ham metin gösterilmiyor → kullanıcı boş kutu görür"
    )
