# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MULTIPART FORM-ALANI BOYUT LİMİTİ — Starlette'in 1MB varsayılanını yükseltir.

⚠️ SAHA BULGUSU 2026-08-30: Yara Kapanma (scratch) analizinde kullanıcı büyük bir görüntü
seçince "Part exceeded maximum size of 1024KB" (Field exceeded ...) hatası alıyordu ve analiz
başlamıyordu. Kök neden: mobil, görüntüyü `image_base64` FORM ALANI (dosya değil) olarak
gönderiyor; Starlette non-file form alanlarına `max_part_size = 1MB` (varsayılan) uyguluyor.
1MB'dan büyük base64 = hata. (Dosya part'ları diske spool edildiği için bu limitten ETKİLENMEZ;
sorun yalnız base64 gönderen uçlarda — scratch, ses, kamera.)

⚠️ NEDEN `request.form(max_part_size=)` DEĞİL (audit B-2.3'ün yolu ÖLÇÜLDÜ, ÇALIŞMIYOR):
`ai_router._allow_large_upload` router-dependency'si `await request.form(max_part_size=50MB)`
çağırıyordu. TestClient ile ölçüldü: FastAPI'nin File/Form çözümü kendi `request.form()`
çağrısını (varsayılan 1MB) yapıp form'u ÖNCE cache'liyor; dependency'nin büyük-limitli çağrısı
cache dolduğu için etkisiz kalıyor → 400 aynen geliyor. Bu sözde-çözüm sessizce bozuktu.

ÇÖZÜM: `Request.form` metodunun VARSAYILAN `max_part_size`'ını yükselt. `Request.form` PUBLIC,
kararlı bir API (audit B-2.3'ün kaçındığı İÇ sınıf `MultiPartParser` değil) → sürüm-dayanıklı.
Böylece FastAPI'nin varsayılan çağrısı da büyük limiti alır. Üst tavan KORUNUR (RAM DoS): limit
üstü part yine 400 reddedilir; her uç ayrıca kendi boyut kontrolünü yapar (`_MAX_IMAGE_BYTES`=25MB).
"""

from __future__ import annotations

# base64 image girdisi uçlarda 25 MB ile sınırlı (_MAX_IMAGE_BYTES); +pay. RNA/CSV DOSYA part'ı
# olarak gelir (diske spool → bu limitten etkilenmez), o yüzden 50MB'ı burada karşılamak gerekmez.
MAX_FIELD_BYTES = 32 * 1024 * 1024  # 32 MB


def buyuk_form_alani_limitini_uygula() -> bool:
    """`Request.form`'un varsayılan max_part_size'ını MAX_FIELD_BYTES yapar. İdempotent.

    Döner: patch bu çağrıda uygulandıysa True, zaten uygulanmışsa False."""
    from starlette.requests import Request

    if getattr(Request.form, "_pemf_multipart_patched", False):
        return False

    _orig_form = Request.form

    def _patched_form(self, *, max_files=1000, max_fields=1000, max_part_size=MAX_FIELD_BYTES):
        return _orig_form(self, max_files=max_files, max_fields=max_fields, max_part_size=max_part_size)

    _patched_form._pemf_multipart_patched = True
    Request.form = _patched_form
    return True
