# Author: mertaygn, cglrgrkn
"""Launcher güncelleme ONAY / GERİ-ALMA kararı — DALA PİNLİ statik denetleyiciler. ⚠️ pytest TOPLAMAZ.

(`test_` ön eki yok; `topoloji.py` / `rs_soyucu.py` deseni.)

D1.35 · B-10.46 · B-10.47: `test_runtime_geri_alma_dongusu_bagli` ve `test_saglik_db_kapisi_bagli`
kapıları `main.rs`'te bir dizenin İLK geçtiği yerin ±900/1200 karakterlik penceresine bakıyordu:
  * sağlık kapısı DÜŞTÜĞÜNDE (`start_backend` Err kolu) `geri_almayi_kaydet` silinse — pencere
    dbReady kolundaki kopyayı gördüğü için — YEŞİL kalıyordu (döngü kırıcı ölür);
  * `if backend::db_hazir_mi(port) == Some(false) && false {` yazılsa YEŞİL kalıyordu (DB'yi
    bozan yayın onaylanır, `runtime.old` silinir — D1.37'nin güvenlik ağı).

Bu modül `main.rs`'i YORUMLARI SOYULMUŞ (Rust'a özgü, dize-bilinçli `rs_soyucu`) hâlde okur,
`match flow::start_backend(&root2, &mut on) {` bloğunu süslü-parantez eşlemesiyle bulur ve her
iddiayı DOĞRU KOLUN üst düzeyinde (alt blok içinde değil) TAM İFADE olarak arar.

⚠️ Davranışsal Rust kolu (onay kararını saf fonksiyona çıkarıp app crate testinde ölçmek) bu
oturumda YAPILMADI: Rust/cargo testleri gerçek ProgramData'ya yazıyor (B-8.7 → D5.41).
"""

from __future__ import annotations

import re
from pathlib import Path

from rs_soyucu import blok_sonu, ifade_deseni, rs_soy, ust_duzey_eslesmeler

MAIN_RS = Path(__file__).resolve().parents[1] / "launcher" / "app" / "src" / "main.rs"

ESLESME = "match flow::start_backend(&root2, &mut on) {"
OK_KOLU = "Ok((child, url, port)) => {"
ERR_KOLU = "Err(e) => {"
KAYDET = "flow::geri_almayi_kaydet(&root2, &manifest_raw);"
GERI_AL = "flow::guncellemeyi_geri_al(&root2, &geri)"
DB_KOSULU = "if backend::db_hazir_mi(port) == Some(false) {"
TEARDOWN = "stop_backend_for_teardown(Some((child, port)), &root2, bellek2.clone());"
GERI_ALINDI = "return Ok(GuncellemeSonucu::GeriAlindi {"
ONAYLA = "flow::guncellemeyi_onayla(&root2, &geri);"
SAYAC_SIFIRLA = "install::clear_runtime_attempt(&root2);"


class _Kaynak:
    def __init__(self, src: str):
        self.soy = rs_soy(src)
        self.maske = rs_soy(src, dizeleri_bosalt=True)

    def tek(self, bas: int, son: int, ifade: str, ne: str) -> int:
        es = ust_duzey_eslesmeler(self.soy, self.maske, bas, son, ifade)
        assert len(es) == 1, f"{ne}: `{ifade}` üst düzeyde {len(es)} kez (1 olmalı)"
        return es[0]

    def blok(self, bas_dizin: int, ifade: str) -> tuple[int, int]:
        """`ifade` (sonu '{') bas_dizin'de başlıyor → (gövde başı, kapanış '}' dizini)."""
        m = ifade_deseni(ifade).match(self.soy, bas_dizin)
        assert m, f"`{ifade}` {bas_dizin}'de eşleşmedi"
        ac = m.end() - 1
        return ac + 1, blok_sonu(self.maske, ac)


def start_backend_kollari(src: str):
    """(kaynak, (ok_bas, ok_son), (err_bas, err_son), (eslesme_bas, eslesme_son)) — yorumsuz metinde
    `start_backend` eşlemesinin kolları ve eşleme gövdesi."""
    k = _Kaynak(src)
    es = list(ifade_deseni(ESLESME).finditer(k.soy))
    assert len(es) == 1, f"`{ESLESME}` yorumsuz kaynakta {len(es)} kez (1 olmalı) — main.rs biçimi değişmiş"
    gbas, gson = k.blok(es[0].start(), ESLESME)
    ok = k.blok(k.tek(gbas, gson, OK_KOLU, "start_backend eşlemesi"), OK_KOLU)
    err = k.blok(k.tek(gbas, gson, ERR_KOLU, "start_backend eşlemesi"), ERR_KOLU)
    return k, ok, err, (gbas, gson)


def err_kolu_denetle(src: str) -> None:
    """B-10.46: sağlık kapısı DÜŞÜNCE (Err kolu) deneme sayılır, SONRA eski sürüme dönülür."""
    k, _ok, (bas, son), _g = start_backend_kollari(src)
    kaydet = k.tek(bas, son, KAYDET, "start_backend Err kolu (sağlık kapısı düştü)")
    geri = k.tek(bas, son, GERI_AL, "start_backend Err kolu (sağlık kapısı düştü)")
    assert kaydet < geri, "Err kolunda geri alma deneme sayacından ÖNCE — sayılmadan dönülürse döngü kırıcı ölür"


def db_kapisi_denetle(src: str):
    """B-10.47: Ok kolunda `dbReady == false` → E-stop'lu söküm, deneme sayacı, geri alma, GeriAlindi.
    Dönüş: (kaynak, (ok_bas, ok_son), (if_bas, if_son))."""
    k, (obas, oson), _err, _g = start_backend_kollari(src)
    if_bas, if_son = k.blok(k.tek(obas, oson, DB_KOSULU, "start_backend Ok kolu"), DB_KOSULU)
    ne = "dbReady=false dalı"
    sokum = k.tek(if_bas, if_son, TEARDOWN, ne)
    kaydet = k.tek(if_bas, if_son, KAYDET, ne)
    geri = k.tek(if_bas, if_son, GERI_AL, ne)
    don = k.tek(if_bas, if_son, GERI_ALINDI, ne)
    assert sokum < geri, "yeni sürüm E-stop'lu sökülmeden geri alınıyor (bobinler enerjili kalabilir)"
    assert kaydet < don and geri < don, "dbReady=false dalı sayaç/geri almadan ÖNCE dönüyor"
    return k, (obas, oson), (if_bas, if_son)


def onay_sirasi_denetle(src: str) -> None:
    """Onay (runtime.old SİLİNİR) YALNIZ dbReady denetiminden SONRA ve o dalın DIŞINDA; ardından sayaç sıfırlanır."""
    k, (obas, oson), (_ib, if_son) = db_kapisi_denetle(src)
    onay = k.tek(obas, oson, ONAYLA, "start_backend Ok kolu")
    assert onay > if_son, "güncelleme dbReady denetiminden ÖNCE onaylanıyor — DB'yi bozan yayın onaylanır"
    sifirla = k.tek(obas, oson, SAYAC_SIFIRLA, "start_backend Ok kolu")
    assert sifirla > onay, "deneme sayacı onaydan önce sıfırlanıyor"
    gbas, gson = start_backend_kollari(src)[3]
    toplam = len(list(ifade_deseni(ONAYLA).finditer(k.soy, gbas, gson)))
    assert toplam == 1, f"`{ONAYLA}` start_backend eşlemesinde {toplam} kez (yalnız Ok kolunda 1 olmalı)"
    # 1-B bağımsız inceleme (i2): sayım eşleme gövdesiyle sınırlıydı — `match` ÖNCESİNE eklenen bir onay
    # (`runtime.old` backend başlamadan silinir, geri dönüş imkânsız) kapıda YEŞİLDİ. Dosyanın TAMAMINDA (yorum
    # ve dize dışı) herhangi bir argümanla TEK onay çağrısı olmalı ve o da yukarıdaki konum.
    genel = [m.start() for m in re.finditer(r"\bguncellemeyi_onayla\s*\(", k.maske)]
    assert len(genel) == 1 and onay <= genel[0] < onay + len(ONAYLA), (
        f"`guncellemeyi_onayla(` main.rs genelinde {len(genel)} kez — yalnız Ok kolundaki dbReady sonrası tek çağrı olmalı"
    )
