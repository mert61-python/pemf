# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI ÇIKARIMI ZAMAN AŞIMI — tek kaynak + anlaşılır iptal mesajı (saha hatası 2026-08-12).

ARIZA: Ev kullanıcısı profilinde fps + hastalık + ses analizleri PEŞ PEŞE başlatıldı. İlk ikisi
sonuç döndürdü, ses analizi `AbortError: signal is aborted without reason` ile düştü ve bu ham
DOM metni kullanıcıya olduğu gibi gösterildi. Hemen ardından ses analizi TEK BAŞINA denendiğinde
ANINDA sonuçlandı.

SEBEP: `cat_sound` ilk çağrıda numba/librosa JIT derlemesi yapar — projenin kendi ölçümü
(`apiClient.ts`): `/ai/sound/cat` ilk çağrı **28,0 sn**, sonraki **0,06 sn**. Üç analiz aynı anda
koştuğunda CPU çekişmesi bu süreyi çağrı yerinde ELLE YAZILMIŞ 60 sn'lik sınırın üstüne çıkarıyor
→ `AbortController` isteği iptal ediyor. Kuyruk suçlu DEĞİL: `ai_queue_gate` yalnız
`PEMF_TIER_ENFORCED` açıkken çalışır ve varsayılan KAPALI, yani üç istek gerçekten eşzamanlı.

⚠️ AYNI ARIZA 2026-08-06'da `/ai/disease` için bildirilmiş ve `AI_TIMEOUT_MS` ile düzeltilmişti —
ama YALNIZ `apiPost` yolunda. Ham `fetch` kullanan 10 modül (ses, CT, patoloji, petri, fantom,
RNA, landmark, organ) atlandığı için hata ses modülünde AYNEN tekrarladı. Bu dosyanın varlık
sebebi budur: düzeltmenin TÜM çağrı yerlerini kapsadığını kilitler, tek tek değil.

Kilitlenen değişmezler:
  1) Tek-seferlik AI çıkarımı çağrılarında zaman aşımı `AI_TIMEOUT_MS`ten gelir; elle yazılmış
     sayı YASAK. İstisna yalnız CANLI KAMERA döngüleridir (uzun sınır kamera akışını kilitler)
     ve açıkça `CANLI-DONGU` ile işaretlenmelidir — istisna sessiz olamaz.
  2) İptal (`AbortError`) kullanıcıya HAM DOM METNİ olarak gösterilmez; zaman aşımı ile ağ
     hatası ayrılır. Ayrım işlevseldir: zaman aşımında TEKRAR DENEMEK işe yarar (model artık
     bellekte), ağ hatasında yaramaz. Kullanıcı bunu ayırt edemezse ürünü bozuk sanır.
"""

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))  # `tests` paket değil (conftest tabanlı toplama)
import capraz  # noqa: E402  — `pf/` bu depoda izlenmez; yoksa atla (zorunlu kipte düşür)

EKRAN = "pf/src/screens/AiHubScreen.tsx"

#: `setTimeout(() => ctrl.abort(), <X>)` — X sayı ise elle yazılmış sınır demektir.
_IPTAL_DESENI = re.compile(r"ctrl\.abort\(\),\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*\)")


def _iptal_sinirlari(src: str):
    """(satır_no, değer) listesi döndürür."""
    out = []
    for i, satir in enumerate(src.splitlines(), start=1):
        m = _IPTAL_DESENI.search(satir)
        if m:
            out.append((i, m.group(1)))
    return out


def test_KRITIK_cikarim_zaman_asimi_TEK_KAYNAKTAN():
    """Elle yazılmış sınır, tek bir modülü sessizce eski değerde bırakır — arızanın kök sebebi."""
    src = capraz.oku(EKRAN)
    satirlar = src.splitlines()
    sayisal = []
    for no, deger in _iptal_sinirlari(src):
        if not deger.isdigit():
            continue
        # İstisna: canlı kamera döngüsü — hemen ÜSTÜNDE açıkça işaretlenmiş olmalı.
        onceki = satirlar[no - 2] if no >= 2 else ""
        if "CANLI-DONGU" in onceki:
            continue
        sayisal.append((no, deger))
    assert not sayisal, (
        "AI cagrisinda ELLE YAZILMIS zaman asimi var (AI_TIMEOUT_MS kullanilmali): "
        + repr(sayisal)
        + " — canli kamera dongusu ise ustune `// CANLI-DONGU:` isareti koyun."
    )


def test_KRITIK_cikarim_cagrilari_AI_TIMEOUT_MS_kullanir():
    """Pozitif taraf: sabit gerçekten kullanılıyor mu (hepsi silinip sorun 'çözülmüş' görünmesin)."""
    src = capraz.oku(EKRAN)
    kullanan = [no for no, d in _iptal_sinirlari(src) if d == "AI_TIMEOUT_MS"]
    assert len(kullanan) >= 10, (
        f"AI_TIMEOUT_MS kullanan cagri sayisi beklenenden az ({len(kullanan)}) — "
        "cikarim cagrilarindan biri tek kaynaktan koparilmis olabilir"
    )
    assert "AI_TIMEOUT_MS" in src.split("\n")[0] or "AI_TIMEOUT_MS" in src, "sabit import edilmemis"


def test_KRITIK_canli_dongu_KISA_kalir():
    """Ters yön: canlı kamera döngüsüne 2 dakikalık sınır konursa akış kilitlenir. İstisnalar
    işaretli DURMALI — yani `CANLI-DONGU` işareti hem gerekli hem yeterli olmalı."""
    src = capraz.oku(EKRAN)
    satirlar = src.splitlines()
    isaretli = [(no, d) for no, d in _iptal_sinirlari(src) if no >= 2 and "CANLI-DONGU" in satirlar[no - 2]]
    assert isaretli, "canli-dongu istisnasi kayboldu — desen degistiyse test guncellenmeli"
    for no, d in isaretli:
        assert d.isdigit() and int(d) <= 30000, (
            f"satir {no}: canli kamera dongusu sinirlari kisa kalmali (<=30sn), bulunan {d}"
        )


def _kod(src: str) -> str:
    """Yorum SATIRLARINI eler; geriye kod kalır.

    ⚠️ İKİ KEZ hata yapıldı, ikisi de burada kayıtlı:
      1. İlk yazımda `"AbortError" in src` deniyordu → mutasyon turunda kontrolü `if (false)`
         yapmak testi GEÇTİ, çünkü "AbortError" kelimesi bu dosyanın KENDİ AÇIKLAMA BLOĞUNDA
         da geçiyor. Kaynak-metin iddiası kodu belgeden AYIRT ETMELİ (aynı tuzağa
         `test_hotspot_autostart` SSID testinde de düşülmüştü).
      2. Düzeltirken `re.sub(r"/\\*.*?\\*/", ...)` kullanıldı → TSX'te JSX içi `{/* … */}`
         parçaları yüzünden eşleşme KOD BÖLGELERİNİ de yuttu: 10 çağrının 7'si kayboldu ve
         test bu kez yanlış-KIRMIZI verdi. Blok regex'i bu dosyada güvenilir değil.
    Bu yüzden ayıklama SATIR TABANLI ve öngörülebilir: yorum olduğu belli satırlar atılır,
    kod satırlarına dokunulmaz.
    """
    out = []
    for satir in src.splitlines():
        t = satir.lstrip()
        if t.startswith("//") or t.startswith("*") or t.startswith("/*"):
            continue
        out.append(satir)
    return "\n".join(out)


def test_KRITIK_iptal_HAM_DOM_METNI_gostermez():
    """`AbortError: signal is aborted without reason` kullanıcıya gösterilmemeli — saha hatası."""
    src = capraz.oku(EKRAN)
    kod = _kod(src)
    # ⚠️ "kodda bir yerde `=== \"AbortError\"` geçiyor mu" YETMEZ: mutasyon turunda yardımcının
    # kontrolü `if (false)` yapıldı ve test GEÇTİ, çünkü BAŞKA iki modülde satır-içi kontroller
    # vardı. (Onlar da bu düzeltmede `aiHataMesaji`ye devredildi; ama iddia yine de yere
    # BAĞLI olmalı, yoksa aynı boşluk tekrar açılır.) Kontrol YARDIMCININ İÇİNDE aranır.
    i = kod.find("function aiHataMesaji")
    assert i >= 0, "aiHataMesaji yardimcisi yok → iptal ayrimi yapilamaz"
    govde = kod[i : kod.find("\n}", i) + 2]
    assert re.search(r'===\s*"AbortError"', govde), (
        "aiHataMesaji ICINDE AbortError kontrolu yok → ham DOM metni "
        '("signal is aborted without reason") kullaniciya gosterilir'
    )
    assert "AI_ZAMAN_ASIMI_MESAJI" in govde, "yardimci zaman asimi mesajini DONDURMUYOR"
    # Yardımcı GERÇEKTEN kullanılmalı; tanımlı ama çağrılmayan bir fonksiyon boş güvencedir.
    #
    # ⚠️ TAM SAYI aranır, `>=` DEĞİL. İlk yazımda `>= 10` idi ve mutasyon turunda bir çağrıyı
    # eski sabit metne geri çevirmek testi GEÇTİ (11 hâlâ ≥ 10). Gevşek eşik, tek bir modülün
    # sessizce kopmasına izin verir — arızanın kök sebebi zaten tam olarak buydu.
    # 12 = 1 tanım + 11 çağrı (AI modüllerinin `catch` blokları). Yeni bir AI modülü
    # eklenince bu sayı BİLİNÇLİ güncellenmeli; `/simulator` rota sözleşmesiyle aynı mantık.
    BEKLENEN_GECIS = 13  # 2026-08-26: +1 ScratchModule (Yara Kapanma) — tek-kaynak aiHataMesaji kullanır
    kullanim = len(re.findall(r"aiHataMesaji\(", kod))
    assert kullanim == BEKLENEN_GECIS, (
        f"aiHataMesaji gecis sayisi {kullanim}, beklenen {BEKLENEN_GECIS} — bir AI modulu "
        "tek kaynaktan KOPMUS ya da yeni modul eklenmis olabilir (bilerekse sayiyi guncelle)"
    )


def test_zaman_asimi_mesaji_TEKRAR_DENEMEYI_soyler():
    """Zaman aşımında tekrar denemek İŞE YARAR (model artık bellekte). Kullanıcı bunu bilmeli;
    aksi hâlde ürünü bozuk sanıp vazgeçer — asıl şikâyet buydu."""
    src = capraz.oku(EKRAN)
    # ⚠️ `(.+?);` KULLANMAYIN: mesaj çok satırlı `"..." + "..."` birleştirmesidir ve non-greedy
    # eşleşme ilk satırda kesiliyordu (test yanlış-kırmızı verdi). Sabitten sonraki pencereye bak.
    kod = _kod(src)
    i = kod.find("AI_ZAMAN_ASIMI_MESAJI")
    assert i >= 0, "AI_ZAMAN_ASIMI_MESAJI sabiti bulunamadi"
    mesaj = kod[i : i + 500]
    assert "zaman aşımı" in mesaj.lower(), "mesaj ne oldugunu SOYLEMIYOR"
    assert "Tekrar deneyin" in mesaj, "mesaj kullaniciya NE YAPACAGINI soylemiyor"
