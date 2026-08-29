# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AYNI WiFi'DE OTOMATİK BAĞLANMA — saha bildirimi 2026-08-29.

Sahibin bildirimi: "kaldırıp tamamen yeniden kurdum, mobil ve laptop aynı WiFi'de olmasına
rağmen ilk açılışta otomatik bağlanmadı; yeniden denede yine olmadı, üçüncüde bağlandı."
(Telefon hotspot'a DEĞİL, ev WiFi'sine bağlıydı.)

Ölçülen iki AYRI arıza — ikisi de bu dosyada kapıya bağlanır:

── 1) mDNS KESİNTİSİ (keşif) ────────────────────────────────────────────────────
Backend log'u, iki ayrı açılışta birebir aynı zinciri verdi:

    +0 sn   backend başladı, `_pemfvet` mDNS yayında
    +30 sn  hotspot (Windows ICS, 192.168.137.1) arayüzü BELİRDİ
            → arayüz monitörü Zeroconf'u KAPATIP yeniden yarattı
            → mDNS kaydı 2-4 sn ÖLDÜ  (telefonun keşif penceresi de 4 sn)

Hotspot boşta kalınca Windows onu uyutup uyandırıyor: bir günde 21 gel-git, 6 soket hatası.
⚠️ Telefonun hotspot'a bağlı olması GEREKMİYOR — hotspot yalnızca VAR OLMAKLA ana WiFi'deki
keşfi kesiyordu. Bu makinede ESP bobinleri bağlı olmadığı için hotspot sürekli boşta.

İki düzeltme:
  (a) Arayüz KAYBOLMASI artık yeniden bağlanma tetiklemez (kalan soketler çalışıyor).
  (b) Açılış penceresinde monitör SIK bakar → hotspot belirir belirmez iş biter, kullanıcı
      telefonu denemeden önce sistem stabil olur.

── 2) BULUT SIRRI AYRIŞMASI (uzaktan erişim) ────────────────────────────────────
Aynı cihazda iki sır kaynağı farklı değer taşıyordu ve VERİ KÖKÜNDEKİ kazanıyordu. Veri kökü
kaldırmada silinir, makine deposu kalır → cihaz kaldır-kur'dan önce ve sonra buluta BAŞKA
sır gönderir. Bulut ilk sırla TOFU'ya mühürlendiği için ikincisi kalıcı `secret_mismatch`
alır (269 kez ölçüldü). Kalıcı kaynak (makine deposu) artık OTORİTEDİR.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
_ZC = _KOK / "utils" / "zeroconf_singleton.py"
_MDNS = _KOK / "services" / "mdns_service.py"
_SEC = _KOK / "utils" / "secrets_manager.py"


def _govde(dosya: Path, fn_adi: str) -> str:
    """Fonksiyonun gövdesini AST ile çıkarır (düz metin penceresi komşu fonksiyona taşardı)."""
    kaynak = dosya.read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == fn_adi:
            return ast.get_source_segment(kaynak, d) or ""
    raise AssertionError(f"{dosya.name} içinde '{fn_adi}' yok")


def _kodsuz_yorum(s: str) -> str:
    """Yorum satırlarını atar — kapı, gerekçe metnine değil KODA çıpalansın."""
    return "\n".join(x for x in s.splitlines() if not x.strip().startswith("#"))


# ── 1) Arayüz kaybı keşfi kesmemeli ─────────────────────────────────────────


def test_KRITIK_arayuz_KAYBI_zeroconf_u_yeniden_yaratmaz():
    """⚠️ SAHADAKİ KESİNTİNİN YARISI: hotspot her kaybolduğunda mDNS kaydı ölüyordu.

    Kalan arayüzlerin soketleri çalışmaya devam eder; kaybolan arayüzün soketi zararsızca
    ölür. Yeniden yaratmak yalnızca kaydı öldürmeye yarıyordu."""
    govde = _kodsuz_yorum(_govde(_ZC, "ensure_interfaces_current"))
    assert re.search(r"set\(ips\)\s*<\s*set\(_bound_ips\)", govde), (
        "salt-kayıp durumu için erken çıkış yok → hotspot her kaybolduğunda Zeroconf yeniden "
        "yaratılır ve mDNS kaydı 2-4 sn ölür"
    )
    # Erken çıkış, yeniden-yaratmadan ÖNCE gelmeli; sonra gelirse hiçbir şey değişmez.
    i_kayip = govde.find("set(ips) < set(_bound_ips)")
    i_yarat = govde.find("Zeroconf(interfaces=")
    assert i_kayip != -1 and i_yarat != -1 and i_kayip < i_yarat, (
        "salt-kayıp kontrolü yeniden-yaratmadan SONRA → kesinti yine oluşur"
    )


def test_KARSIT_arayuz_EKLENMESI_hala_yeniden_baglanir():
    """Karşıt-kanıt: yeni arayüz gelince ona bind ETMEK ŞART (ESP'ler hotspot'ta `_mqtt` arar).

    Kapı, düzeltmeyi 'hiç yeniden bağlanma' diye aşırıya götüren bir refaktörü yakalar."""
    govde = _kodsuz_yorum(_govde(_ZC, "ensure_interfaces_current"))
    assert "Zeroconf(interfaces=ips)" in govde, "yeniden bağlanma yolu tamamen kaldırılmış"
    assert "_reregister_cbs" in govde or "cbs" in govde, "re-register callback'leri çağrılmıyor"


# ── 2) Açılışta sık kontrol ─────────────────────────────────────────────────


def test_KRITIK_acilis_penceresinde_SIK_kontrol():
    """Hotspot arayüzü açılıştan ~30 sn sonra beliriyor; monitör de 30 sn'de bir bakıyordu →
    kesinti tam kullanıcının telefonu denediği ana denk geliyordu."""
    govde = _kodsuz_yorum(_govde(_MDNS, "_ip_monitor_loop"))
    assert "ACILIS_ARALIGI_SN" in govde, "açılış penceresi için ayrı (sık) aralık yok"
    m = re.search(r"ACILIS_ARALIGI_SN\s*=\s*(\d+)", govde)
    assert m and int(m.group(1)) <= 5, (
        f"açılış aralığı çok uzun ({m.group(1) if m else '?'} sn) — hotspot belirdikten sonra "
        f"kesinti hâlâ kullanıcının deneme anına denk gelir"
    )
    assert re.search(r"sleep\(\s*ACILIS_ARALIGI_SN\s+if\s+", govde), (
        "sabit uyku hâlâ kullanılıyor → açılış penceresi GERÇEKTEN uygulanmıyor"
    )


def test_acilis_penceresi_KALICI_DEGIL():
    """Sürekli 3 sn'de bir arayüz taraması 7/24 açık cihazda gereksiz yük olur."""
    govde = _kodsuz_yorum(_govde(_MDNS, "_ip_monitor_loop"))
    m = re.search(r"ACILIS_PENCERESI_SN\s*=\s*(\d+)", govde)
    assert m and int(m.group(1)) <= 180, "açılış penceresi çok uzun (kalıcı sık tarama)"
    assert re.search(r"NORMAL_ARALIK_SN\s*=\s*(\d+)", govde), "normal tempoya dönüş yok"


# ── 3) Bulut sırrı: kalıcı kaynak otorite ───────────────────────────────────


def test_KRITIK_sir_AYRISMASINDA_makine_deposu_kazanir():
    """⚠️ UZAKTAN ERİŞİMİ KALICI ÖLDÜREN AYRIŞMA.

    Veri kökü kaldırmada silinir, makine deposu kalır. Veri kökündeki değer kazanırsa aynı
    cihaz kaldır-kur'dan önce/sonra buluta FARKLI sır gönderir ve TOFU mührü kalıcı olarak
    kırılır (`secret_mismatch`, 269 kez ölçüldü)."""
    govde = _kodsuz_yorum(_govde(_SEC, "get_secret"))
    assert "_kimlik_deposu_oku()" in govde, "makine deposu hiç okunmuyor"
    assert re.search(r"_makinedeki\s*!=\s*_cozulen", govde) or re.search(r"!=\s*_cozulen", govde), (
        "ayrışma hiç tespit edilmiyor → veri kökündeki sessizce kazanır"
    )
    assert "return _makinedeki" in govde, "ayrışmada makine deposu DÖNDÜRÜLMÜYOR → kaldır-kur sırrı yine değiştirir"


# ── 4) DAVRANIŞSAL: yapısal çıpalar kodun ŞEKLİNİ ölçer, bunlar İŞİNİ ─────────


def test_DAVRANIS_kayipta_ayni_Zeroconf_ornegi_KORUNUR(monkeypatch):
    """Gerçek fonksiyon çağrılır: hotspot kaybolunca örnek DEĞİŞMEMELİ.

    ⚠️ Yapısal kapı 'erken çıkış var mı' der; bu kapı 'kayıt gerçekten ayakta mı' der. Örnek
    değişirse mDNS kaydı ölür — sahadaki kesintinin ta kendisi."""
    from utils import zeroconf_singleton as zs

    sahte = object()
    monkeypatch.setattr(zs, "_zc", sahte, raising=False)
    monkeypatch.setattr(zs, "_bound_ips", ["192.168.1.38", "192.168.137.1"], raising=False)
    # Hotspot kayboldu (salt-kayıp):
    monkeypatch.setattr(zs, "_real_lan_ipv4s", lambda: ["192.168.1.38"])

    rebind = zs.ensure_interfaces_current()

    assert rebind is False, "salt-kayıpta yeniden bağlanma bildirildi"
    assert zs._zc is sahte, "Zeroconf örneği DEĞİŞTİ → mDNS kaydı öldü (sahadaki kesinti)"
    assert zs._bound_ips == ["192.168.1.38"], "takip güncellenmedi → sonraki ekleme kaçırılır"


def test_DAVRANIS_ayni_set_no_op(monkeypatch):
    """Karşıt-kanıt: değişiklik yokken de dokunulmamalı (gereksiz iş/kesinti yok)."""
    from utils import zeroconf_singleton as zs

    sahte = object()
    monkeypatch.setattr(zs, "_zc", sahte, raising=False)
    monkeypatch.setattr(zs, "_bound_ips", ["192.168.1.38"], raising=False)
    monkeypatch.setattr(zs, "_real_lan_ipv4s", lambda: ["192.168.1.38"])

    assert zs.ensure_interfaces_current() is False
    assert zs._zc is sahte


def test_DAVRANIS_sir_ayrismasinda_MAKINE_DEPOSU_donuyor(tmp_path, monkeypatch):
    """Gerçek `get_secret` çağrılır: veri kökü ile makine deposu ayrıştığında hangi değer gider?

    ⚠️ İZOLASYON ŞART: bu test gerçek `C:\\ProgramData` kimlik deposuna DOKUNMAMALI (aynı sınıf
    bir sızıntı 2026-08-28'de gerçek cihazın sırrını bozmuştu)."""
    from utils import secrets_manager as sm

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    (tmp_path / "makine").mkdir(parents=True, exist_ok=True)

    VERI_KOKU_SIRRI = "veri-kokundeki-eski-sir"
    MAKINE_SIRRI = "makine-deposundaki-kalici-sir"

    monkeypatch.setattr(sm, "_load", lambda: {"auto": {"device_registry_secret": VERI_KOKU_SIRRI}})
    monkeypatch.setattr(sm, "_dec", lambda s: s)
    monkeypatch.setattr(sm, "_kimlik_deposu_oku", lambda: MAKINE_SIRRI)

    yazilanlar = []
    monkeypatch.setattr(sm, "_kimlik_deposu_yaz", lambda v: yazilanlar.append(v))

    sonuc = sm.get_secret("device_registry_secret")

    assert sonuc == MAKINE_SIRRI, (
        "veri kökündeki sır kazandı → kaldır-kur'da (veri kökü silinince) gönderilen sır DEĞİŞİR "
        "ve bulut TOFU mührü kalıcı olarak kırılır"
    )
    assert not yazilanlar, "depo doluyken üzerine yazıldı — kalıcı kaynak ezilmemeli"


def test_DAVRANIS_depo_BOSKEN_veri_kokundeki_TASINIR(tmp_path, monkeypatch):
    """Karşıt-kanıt (denetim #02 korunuyor): depo boşsa mevcut sır oraya göç etmeli.

    Bu yol olmadan sahadaki cihazlar ilk kaldır-kur'da sırrını kaybeder."""
    from utils import secrets_manager as sm

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine2"))
    (tmp_path / "makine2").mkdir(parents=True, exist_ok=True)

    MEVCUT = "sahadaki-cihazin-siri"
    monkeypatch.setattr(sm, "_load", lambda: {"auto": {"device_registry_secret": MEVCUT}})
    monkeypatch.setattr(sm, "_dec", lambda s: s)
    monkeypatch.setattr(sm, "_kimlik_deposu_oku", lambda: "")  # depo BOŞ

    yazilanlar = []
    monkeypatch.setattr(sm, "_kimlik_deposu_yaz", lambda v: yazilanlar.append(v))

    sonuc = sm.get_secret("device_registry_secret")

    assert sonuc == MEVCUT, "mevcut sır değişti — sahadaki cihazın bulut mührü kırılırdı"
    assert yazilanlar == [MEVCUT], "sır kalıcı depoya taşınmadı → sonraki kaldır-kur'da kaybolur"


def test_ilk_GOC_hala_calisiyor():
    """Karşıt-kanıt: makine deposu BOŞken veri kökündeki sır oraya taşınmalı (denetim #02).

    Bu yol olmadan sahadaki mevcut cihazlar ilk kaldır-kur'da sırrını kaybeder."""
    govde = _kodsuz_yorum(_govde(_SEC, "get_secret"))
    assert "_kimlik_deposu_yaz(_cozulen)" in govde, "ilk göç yolu kaldırılmış"
    i_yaz = govde.find("_kimlik_deposu_yaz(_cozulen)")
    i_bos = govde.find("if not _makinedeki")
    assert i_bos != -1 and i_bos < i_yaz, "göç, 'depo boş' koşuluna bağlı değil"
