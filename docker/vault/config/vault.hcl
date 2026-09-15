// HashiCorp Vault — PEMF sır emaneti (escrow) yapılandırması.
//
// ⚠️ Bu Vault, uygulamanın çalışma-anı sır kaynağı DEĞİLDİR; yalnız makine-dışı yedek tutar.
//    Gerekçe: docker/docker-compose.vault.yml başlığı.

// Kalıcı depolama: konteyner durunca emanet KAYBOLMAZ.
// (`-dev` kipi belleğe yazar ve tam da korunmak istediğimiz kaybı üretir.)
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address = "0.0.0.0:8200"

  // ⚠️ TLS KAPALI — BİLİNÇLİ ve YALNIZ bu kullanım için güvenli:
  // compose dosyası portu `127.0.0.1:8200` olarak yayınlar, yani dinleyici konteyner
  // dışına ÇIKMAZ; trafik makinenin loopback'inden geçer. Vault'u ağa açacaksanız
  // (başka makineden yazacaksanız) BURAYI TLS'e çevirmek ZORUNLUDUR.
  tls_disable = 1
}

// Denetim kaydı: emanete kim ne zaman dokundu.
// ⚠️ Vault, denetim hedefi yazılamıyorsa İSTEKLERİ REDDEDER (fail-closed). Bu yüzden
// `vault-log` birimi compose'da tanımlı; kaldırılırsa Vault kullanılamaz hâle gelir.
// (Denetim hedefi başlangıçta OTOMATİK açılmaz — `vault_emanet.py --kur` etkinleştirir.)

ui = true
disable_mlock = false

// ⚠️ KURTARMA TOKEN'I YILLAR SONRA KULLANILACAK.
// Vault'un varsayılan `max_lease_ttl`i 768 saat (32 gün); o sınırla üretilen bir token
// disk kaybı yaşandığında çoktan SÜRESİ DOLMUŞ olurdu — yani emanet tam ihtiyaç anında
// işe yaramazdı. Sahip kararı (2026-09-13): emanet token'ı uzun ömürlü olacak.
// 87600h = 10 yıl. Bu YALNIZ üst sınırdır; her token kendi TTL'ini ayrıca belirtir.
max_lease_ttl     = "87600h"
default_lease_ttl = "87600h"

// Tek düğüm: küme yok, replikasyon yok. Yedekleme = `pemf-vault-veri` biriminin kopyası.
// ⚠️ O birimi AYNI diskte tutmak riski KAPATMAZ — başka bir makineye/USB'ye kopyalayın.
