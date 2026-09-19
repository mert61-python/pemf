# Author: mertaygn, cglrgrkn
"""KABİN CV — iki araştırma profilinin PAYLAŞTIĞI kod (A2, 2026-09-19).

NE OLDU. `inference_em_fantom/phantom_cv/` ile `inference_petri_dish/petri_cv/`
altındaki üç dosya kopyaydı:

    coord_transform.py   326 satır  — MD5 BİREBİR aynı
    mqtt_publish.py      144 satır  — MD5 BİREBİR aynı
    cabin_config.py      367 satır  — 366'sı aynı, tek fark `mqtt_client_id` varsayılanı

`coord_transform` = **bobin/hedef geometrisi**. Bir taraftaki düzeltme diğerinde kalmazdı.
Depo bunu biliyordu ve kaldırmak yerine bir teste bağlamıştı — o kapı yalnız *unutulunca*
kırılıyordu, yani arızayı önlemiyor, haber veriyordu.

⚠️ 2026-09-19'da ölçüldü: **henüz ayrışmamışlardı** (iki dosya hâlâ bayt-birebir). Yani
birleştirme temiz yapılabildi; bir hafta sonra olsaydı önce ayrışma çözülecekti.

KAPSAM DAR TUTULDU — ölçülerek. İki pakette `pipeline.py` (498 satır fark),
`color_segment.py` (590), `render.py` (357), `cli.py` (198), `api.py` (8) de var ama
bunlar **gerçek profil-başına uygulamalar**, kopya değil. `inference_cat_organ/lib/
cabin_config.py` de (185 satır) ayrı bir modül — adı benzer, içeriği değil.

PROFİL KİMLİĞİ KORUNDU: her profilin `cabin_config.py`'si ince bir kabuk olarak kaldı ve
yalnız kendi `VARSAYILAN_CLIENT_ID`'sini geçiriyor. Böylece tek uygulama + profil farkı.
"""

from __future__ import annotations

__all__: list[str] = []
