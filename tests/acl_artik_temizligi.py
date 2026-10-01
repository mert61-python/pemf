# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ACL-KİLİTLİ TEST ARTIĞI TEMİZLİĞİ — ürünün sertleştirdiği düz-metin yedekleri testin kendi tmp'sinde bırakılmaz.

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (`topoloji.py` deseni): adı `test_*` olmadığı için pytest onu TOPLAMAZ.

NEDEN (1-A §7 açık madde 13 / 1-B (iii)): emanet açıkken ürün `.plain.bak`'ı `utils.file_acl.lock_down_file` ile
YALNIZ SYSTEM + Administrators'a kilitler (miras kesik). `test_escrow_ISTENIRSE_hala_saklanir` (ve
`test_KARSIT_KANIT_ACL_TUTARSA_…`) bu dosyayı pytest tmp'sinde bırakıyordu.
ÖLÇÜLEN (2026-10-01): kullanıcı dosyayı OKUYAMAZ; PowerShell `Remove-Item -Recurse -Force` dizini
"Access denied" ile SİLEMEZ (1-A oturum sonu temizliğinin `icacls /reset` gerektirmesinin sebebi). Üst dizin
kullanıcıya tam yetki verdiği için (alt öğe silme hakkı) `os.unlink` / pytest `rm_rf` / MSYS `rm` SİLER —
yani "pytest tmp rotasyonu kilitlenir" öncülü bu ölçümde DOĞRULANMADI; temizlik hijyen içindir (TEMP'te
kullanıcının açamadığı düz-metin-biçimli yedek kalmasın, Remove-Item temelli temizlikler takılmasın).

YALNIZ verilen kökün (testin kendi tmp'si) altında, YALNIZ desenle eşleşen dosyalarda çalışır.
"""

from __future__ import annotations

from pathlib import Path

#: Ürünün kilitlediği düz-metin yedek sınıfı (`*.plain.bak` ve kenara alınmış `*.plain.bak.<zaman>`).
DUZ_METIN_YEDEK_DESENI = "*.plain.bak*"


def acl_kilitli_artiklari_temizle(kok: Path, desen: str = DUZ_METIN_YEDEK_DESENI) -> list[str]:
    """`kok` altındaki desenle eşleşen dosyaları siler; SİLİNEMEYENLERİ döndürür (çağıran görünür kılar)."""
    kalan: list[str] = []
    for p in sorted(Path(kok).rglob(desen)):
        if not p.is_file():
            continue
        try:
            p.unlink()
        except OSError:
            kalan.append(str(p))
    return kalan
