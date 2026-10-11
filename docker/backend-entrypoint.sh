#!/bin/sh
# =============================================================================
# PEMF backend konteyner giriş betiği — D4.12 (B-3.49): KALICI makine kimliği.
#
# secrets_manager kritik anahtarları (sqlcipher_key, patient_fernet_key) Linux'ta makine kimliğinden
# türetilen anahtarla sarar (MKEY:); kimlik yoksa fail-closed RuntimeError verir (doğru davranış).
# python:slim imajında /etc/machine-id YOKTU → backend import'ta ölüyor, konteyner yeniden başlatma
# döngüsüne giriyordu. Kimlik İLK açılışta üretilir ve compose'un bağladığı ADLI birimde (/var/lib/dbus)
# kalıcıdır; imajda /etc/machine-id ona bağlıdır.
# ⚠️ Kimlik birimini veri birimi (/data) olmadan SİLMEYİN: kayıtlı kritik sırlar çözülemez — ürün yeni
#    anahtar ÜRETMEZ (fail-closed, Karar 6). Birim /data'dan AYRIDIR: yalnız /data yedeği sırları açmaz.
# Kapı: tests/test_docker_KALICI_makine_kimligi_D412.py
# =============================================================================
set -eu
KIMLIK=/var/lib/dbus/machine-id
if [ ! -s "$KIMLIK" ]; then
    umask 077
    od -An -N16 -tx1 /dev/urandom | tr -d ' \n' > "$KIMLIK.tmp"
    # Rastgele kaynak okunamazsa boş/yarım kimlik KALICI birime yazılmaz ve backend başlatılmaz.
    if [ "$(wc -c < "$KIMLIK.tmp" | tr -d ' ')" != "32" ]; then
        rm -f "$KIMLIK.tmp"
        echo "HATA: makine kimligi uretilemedi — backend baslatilmadi" >&2
        exit 1
    fi
    mv "$KIMLIK.tmp" "$KIMLIK"
fi
exec "$@"
