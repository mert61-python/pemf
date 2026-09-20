# Author: mertaygn, cglrgrkn
r"""SESSİZ `except: pass` TEHLİKELİ BİR İŞİ YUTMASIN (triyaj, 2026-09-20).

NE ÖLÇÜLDÜ. `apps/backend` altında **911 except handler**'ın **188'inin** gövdesi tek
`pass`tı (%21). Çıplak sayı bir ölçüt DEĞİL: bir `conn.close()`u yutmak zararsızdır,
bir `shutil.move`u yutmak bu depoda **gerçek veri kaybına** yol açtı.

ÖLÇÜT — "sessiz yutma tehlikeli mi?" iki koşulun KESİŞİMİ:
  1. `try` gövdesi **durum değiştiren** bir iş mi yapıyor (yazma/taşıma/silme/ACL/DB/yayın)?
  2. Başarısızlık **başka türlü görünür mü**?

Triyaj 188'i dörde ayırdı: **8 tehlikeli** · 49 şüpheli · 104 belirsiz · 27 zararsız.
Sekizi tek tek okundu; **dördü gerçek** çıktı ve düzeltildi (akış değişmedi, yalnız
başarısızlık loga düşer oldu):

    sqlcipher_util  ACL kilidi yutuluyordu       → ŞİFRELEME ANAHTARI dosyası Users'a
                                                   açık kalabilir, hiçbir yer söylemezdi
    sqlcipher_util  anahtar dosyası yazımı       → sebebi kayboluyordu; keyring tek kopya
                                                   kalırsa veri KALICI OKUNAMAZ
    sqlcipher_util  WAL/SHM temizliği            → kodun KENDİ yorumu "açık handle/çakışma
                                                   → BOZULMA önle" diyor, hatası sessizdi
    backend_service sır dosyası ACL döngüsü      → istisna ile "zaten kilitli" ayırt
                                                   edilemiyordu

⚠️ BU KAPI TOPLU DÜZELTME DAYATMAZ. Amaç "sıfır `except: pass`" değil — meşru temizlik
vardır. Amaç: **durum değiştiren bir işin riskli bir bağlamda sessizce yutulması yeni
eklenemesin.** Yeni bir tane gerekiyorsa aşağıdaki listeye GEREKÇESİYLE yazılır.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

#: Durum değiştiren işler — başarısızlığı ürünün davranışını değiştirir.
YIKICI = frozenset(
    {
        "move",
        "copy",
        "copy2",
        "copyfile",
        "remove",
        "unlink",
        "rename",
        "replace",
        "rmtree",
        "mkdir",
        "makedirs",
        "write_text",
        "write_bytes",
        "write",
        "chmod",
        "lock_down_file",
        "_kilidi_gevset",
        "icacls",
        "commit",
        "execute",
        "executemany",
        "executescript",
        "publish",
        "post",
        "put",
        "send",
        "connect",
        "start",
        "terminate",
        "kill",
    }
)
#: Kaynak bırakma — yutulması zararsız.
ZARARSIZ = frozenset(
    {
        "close",
        "join",
        "shutdown",
        "stop",
        "disconnect",
        "loop_stop",
        "cancel",
        "flush",
        "unregister",
        "removeHandler",
        "clear",
        "collect",
        "release",
    }
)
#: Fonksiyon adı bunları taşıyorsa bağlam RİSKLİ (veri/kurtarma/güvenlik yolu).
RISKLI_BAGLAM = (
    "goc",
    "migrate",
    "karantina",
    "kurtar",
    "yedek",
    "backup",
    "escrow",
    "emanet",
    "acl",
    "sir",
    "secret",
    "anahtar",
    "key",
    "estop",
    "stop",
    "seans",
    "session",
    "toparla",
    "restore",
)

#: ⚠️ MUAFİYETLER — her biri OKUNARAK meşru bulundu. Yeni satır GEREKÇE ister.
#: Biçim: (dosya, fonksiyon) -> neden meşru
#: ⚠️ SAYAÇLI MUAFİYET — bir mutasyonla (S1) ortaya çıktı. İlk hâl yalnız
#: `(dosya, fonksiyon)` çiftini muaf tutuyordu; o fonksiyona **YENİ** bir tehlikeli
#: yutma eklense de kapı görmüyordu. Artık SAYI da pinli: fazlası KIRMIZI.
MUAF: dict[tuple[str, str], tuple[int, str]] = {
    (
        "apps/backend/database/sqlcipher_util.py",
        "migrate_to_encrypted_if_needed",
    ): (
        2,
        "(a) PROB: 'şifreli açılıyor mu' denemesi — başarısızlık BEKLENEN sinyaldir "
        "(açılmadı → göç et). (b) geri-alma sonrası `.enc.tmp` temizliği — sonraki göç "
        "onu `_kilit_direncli_sil` ile zaten siler",
    ),
    (
        "apps/backend/servers/ai_router.py",
        "analyze_histopath",
    ): (
        1,
        "geçici dosya `unlink`i `finally` içinde; kalması yalnız disk sızdırır, analiz sonucunu etkilemez",
    ),
    (
        "apps/backend/services/headless_db_maintenance.py",
        "_cleanup_backups",
    ): (
        1,
        "retention dışı ESKİ yedeklerin silinmesi; başarısızlık yedeklerin BİRİKMESİ "
        "demektir (veri kaybı değil) ve dıştaki handler zaten loglar",
    ),
}


# ═════════════════════════════════════════════════════════════════════════════════════════
# SINIFLANDIRICI
# ═════════════════════════════════════════════════════════════════════════════════════════


def _sessiz_mi(h: ast.ExceptHandler) -> bool:
    return len(h.body) == 1 and isinstance(h.body[0], ast.Pass)


def _cagrilar(govde: list[ast.stmt]) -> list[str]:
    """Gövdedeki çağrılar — AMA kendi (sessiz olmayan) handler'ı olan iç `try`lar HARİÇ.

    ⚠️ BU AYRIM BİR YANLIŞ-POZİTİFLE DOĞDU: `path_utils._kullanicidan_makineye_gocur`
    dıştan sessiz görünüyor ama içerideki `copy2` hatası zaten `exc_info` ile loglanıyor.
    Ayrım olmadan kapı meşru kodu tehlikeli sayar ve güveni kaybeder.
    """
    modul = ast.Module(body=govde, type_ignores=[])
    ele_alinmis: set[int] = set()
    for d in ast.walk(modul):
        if isinstance(d, ast.Try) and any(not _sessiz_mi(h) for h in d.handlers):
            for alt in ast.walk(ast.Module(body=d.body, type_ignores=[])):
                ele_alinmis.add(id(alt))
    out = []
    for d in ast.walk(modul):
        if isinstance(d, ast.Call) and id(d) not in ele_alinmis:
            f = d.func
            if isinstance(f, ast.Attribute):
                out.append(f.attr)
            elif isinstance(f, ast.Name):
                out.append(f.id)
    return out


def siniflandir(govde: list[ast.stmt], fn_adi: str) -> str:
    if govde and all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in govde):
        return "ZARARSIZ"
    c = _cagrilar(govde)
    if c and all(x in ZARARSIZ for x in c):
        return "ZARARSIZ"
    if any(x in YIKICI for x in c):
        return "TEHLIKELI" if any(k in fn_adi.lower() for k in RISKLI_BAGLAM) else "SUPHELI"
    return "BELIRSIZ"


def tara(kaynak: str, rel: str) -> list[tuple[str, str, int, str]]:
    """[(dosya, fonksiyon, satır, sınıf)]

    ⚠️ `SyntaxError` SESSİZCE ATLANMAZ — bir mutasyonla ölçüldü (S1, 2026-09-20).
    İlk hâl `except SyntaxError: return []` yapıyordu; ayrıştırılamayan dosya taramadan
    **sessizce düşüyor** ve kapı o dosya için sonsuza dek yeşil kalıyordu. Bu depoda
    aynı sınıf (`kapı çözülemeyeni sessizce düşürüyordu`) daha önce yarım kapsamla
    yeşil kalmaya yol açtı.
    """
    try:
        agac = ast.parse(kaynak)
    except SyntaxError as e:
        raise AssertionError(f"{rel} ayrıştırılamadı ({e}) — kapı o dosyayı TARAYAMAZ") from e
    ad: dict[int, str] = {}
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for alt in ast.walk(d):
                ad.setdefault(id(alt), d.name)
    out = []
    for d in ast.walk(agac):
        if not isinstance(d, ast.Try):
            continue
        for h in d.handlers:
            if _sessiz_mi(h):
                fn = ad.get(id(h), "<modul>")
                out.append((rel, fn, h.lineno, siniflandir(d.body, fn)))
    return out


def _backend_dosyalari() -> list[str]:
    ch = subprocess.run(
        ["git", "ls-files", "apps/backend/*.py"],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    return [a for a in ch.stdout.splitlines() if a]


# ═════════════════════════════════════════════════════════════════════════════════════════
# 1. ASIL SÖZLEŞME
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_riskli_baglamda_SESSIZ_yutma_YOK():
    """🔴 Durum değiştiren bir iş, veri/kurtarma/güvenlik bağlamında sessizce yutulmasın."""
    dosyalar = _backend_dosyalari()
    assert len(dosyalar) > 50, f"tarama çok dar ({len(dosyalar)}) — kapı boş dönüyor olabilir"

    hepsi = []
    for rel in dosyalar:
        try:
            hepsi += tara((KOK / rel).read_text(encoding="utf-8", errors="replace"), rel)
        except OSError:
            continue
    # ⚠️ VAKUM KAPISI: sınıflandırıcı bozulursa hiç handler bulamaz ve sonsuza dek yeşil kalır.
    assert len(hepsi) > 100, f"yalnız {len(hepsi)} sessiz handler bulundu — tarayıcı körelmiş olabilir"

    tehlikeli = [(f, fn, n) for f, fn, n, s in hepsi if s == "TEHLIKELI"]

    # 1) Muaf OLMAYAN her tehlikeli yutma ihlaldir.
    ihlal = [t for t in tehlikeli if (t[0], t[1]) not in MUAF]
    assert not ihlal, (
        "Riskli bağlamda SESSİZ yutma:\n"
        + "\n".join(f"  {f}:{n}  {fn}()" for f, fn, n in ihlal)
        + "\nÇözüm: akışı değiştirme — başarısızlığı LOGLA. Meşruysa `MUAF`a GEREKÇESİYLE yaz."
    )

    # 2) ⚠️ Muaf fonksiyonda SAYI da pinli — yoksa o fonksiyona yeni bir tehlikeli
    #    yutma eklenir ve kapı görmez (mutasyon S1 tam bunu gösterdi).
    from collections import Counter

    say = Counter((f, fn) for f, fn, _ in tehlikeli)
    for anahtar, (beklenen, _gerekce) in MUAF.items():
        bulunan = say.get(anahtar, 0)
        assert bulunan == beklenen, (
            f"{anahtar[0]}  {anahtar[1]}(): {bulunan} tehlikeli sessiz yutma var, "
            f"muafiyet {beklenen} diyor. Arttıysa YENİ bir tane eklenmiş — okuyup ya düzeltin "
            "ya da sayıyı GEREKÇEYLE güncelleyin. Azaldıysa sayıyı düşürün (muafiyet bayatlar)."
        )


def test_KRITIK_muafiyetler_GERCEKTEN_var_ve_gerekceli():
    """Muafiyet listesi bayatlarsa kapı sessizce genişler."""
    dosyalar = set(_backend_dosyalari())
    for (f, fn), (adet, gerekce) in MUAF.items():
        assert f in dosyalar, f"muaf dosya artık yok: {f} — listeyi temizleyin"
        assert adet >= 1, f"{f}:{fn} muafiyeti 0 adet — satırı SİLİN"
        assert len(gerekce) > 40, f"{f}:{fn} muafiyeti gerekçesiz (kısa) — neden meşru?"
    assert len(MUAF) <= 6, f"muafiyet listesi şişmiş ({len(MUAF)}) — her satır okunarak eklenmeli"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 2. KARŞIT-KANITLAR — sınıflandırıcı gerçekten ayırıyor mu
# ═════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("kaynak", "beklenen", "aciklama"),
    [
        (
            "\n".join(
                ["def goc_yap():", "    try:", "        shutil.move(a, b)", "    except Exception:", "        pass"]
            ),
            "TEHLIKELI",
            "veri taşıma + göç bağlamı (bu depoda GERÇEKTEN yaşandı)",
        ),
        (
            "\n".join(["def temizle():", "    try:", "        conn.close()", "    except Exception:", "        pass"]),
            "ZARARSIZ",
            "kaynak bırakma",
        ),
        (
            "\n".join(["try:", "    import paho.mqtt.client as mqtt", "except ImportError:", "    pass"]),
            "ZARARSIZ",
            "opsiyonel import",
        ),
        (
            "\n".join(["def bir_sey():", "    try:", "        os.remove(f)", "    except Exception:", "        pass"]),
            "SUPHELI",
            "durum değiştiren ama bağlam nötr",
        ),
        (
            "\n".join(
                [
                    "def goc_yap():",
                    "    try:",
                    "        try:",
                    "            shutil.copy2(a, b)",
                    "        except Exception:",
                    "            log.warning(1)",
                    "    except Exception:",
                    "        pass",
                ]
            ),
            "BELIRSIZ",
            "İÇ handler ele alıyor → dış sessizlik tehlikeli DEĞİL",
        ),
    ],
    ids=["tehlikeli", "kaynak_birakma", "opsiyonel_import", "notr_baglam", "ic_handler_var"],
)
def test_KARSIT_KANIT_siniflandirici_AYIRIYOR(kaynak: str, beklenen: str, aciklama: str):
    """Kapının tamamı bu ayrıma dayanıyor; ayrım bozulursa kapı ya kör ya da gürültü olur."""
    b = tara(kaynak, "<sinav>")
    assert b, f"sessiz handler bulunamadı: {aciklama}"
    assert b[0][3] == beklenen, f"{aciklama}: beklenen {beklenen}, bulunan {b[0][3]}"


def test_KARSIT_KANIT_DUZELTILEN_dortu_artik_sessiz_DEGIL():
    """2026-09-20'de düzeltilen dört nokta geri `pass`e dönerse yakalansın.

    ⚠️ Çıpa KODA pinli: her birinin `except` dalında artık bir `logger` çağrısı var.
    """
    hedefler = {
        "apps/backend/database/sqlcipher_util.py": [
            "ACL kilidi UYGULANAMADI",
            "anahtar dosyasi YAZILAMADI",
            "temizlenemedi",
        ],
        "apps/backend/backend_service.py": [
            "ACL kilidi uygulanamadi",
        ],
    }
    for rel, izler in hedefler.items():
        metin = (KOK / rel).read_text(encoding="utf-8")
        for iz in izler:
            assert iz in metin, f"{rel}: '{iz}' log'u kaybolmuş — sessiz yutma geri gelmiş olabilir"
