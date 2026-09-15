# Hasta Anahtarı Emaneti — HashiCorp Vault

**Tarih:** 2026-09-13 · **Sahip kararı:** *"mevcut sistem çalışsın, anahtar yedeği Vault'ta olsun;
token verin, disk kaybında token'la DB anahtarını alıp şifreyi açayım."*

---

## 1. Neden var — ölçülmüş risk

Hasta veritabanları **şifreli** (doğru). Ama şifreyi açan anahtar **tek yerdeydi**:

```
C:\ProgramData\PEMF_System\PEMF_GUI\pemf_secrets.json → auto.sqlcipher_key
biçim: "DPAPI:…"  →  Windows DPAPI, MAKİNEYE BAĞLI
```

Ölçüldü (2026-09-13):

- `~/pemf-sirlar.pemfsec` bu anahtarı **taşımıyor** (içindeki 7 kalem ESP `Secrets.h`,
  ESP `config.json`, cloud provision, Android keystore).
- Windows keyring'de de yok, `.sqlcipher_key` dosyası da yok.

**Sonuç:** disk/OS/profil kaybında DPAPI blob'u çözülemez → hasta verisi **kalıcı okunamaz**.
Şifreli `.db` dosyasını yedeklemek kurtarmaz; anahtar olmadan açılmaz.

---

## 2. Ne YAPILDI, ne YAPILMADI

| | |
|---|---|
| ✅ Vault kuruldu (Docker, `hashicorp/vault:1.20`), yalnız `127.0.0.1:8200` | |
| ✅ Anahtarların **yedeği** Vault'a yazıldı | |
| ✅ 10 yıllık, **yalnız-okuma** kurtarma token'ı üretildi | |
| ✅ Kurtarma **uçtan uca kanıtlandı**: token → Vault → anahtar → şifreli DB **açıldı** | |
| ❌ Yerel anahtar **KALDIRILMADI** — uygulama eskisi gibi çalışıyor | sahip kararı |
| ❌ Backend Vault'tan **okumuyor** — açılış yolu değişmedi | sahip kararı |

⚠️ **Backend'i Vault'a bağlamamak bilinçli bir karardır.** Bağlansaydı: Vault her yeniden
başlatmada **mühürlü** gelir, yani biri mührü açmadan hasta kaydı açılmazdı; auto-unseal ise
bulut KMS ister ve *"bu ürün internetsiz çalışır"* değişmezini bozardı. Ayrıca sır kaybolmaz,
**yer değiştirirdi**: unseal anahtarları yeni tek-arıza-noktası olurdu.

---

## 3. Kurtarma — disk kaybı sonrası ne yapacaksınız

Elinizde **iki şey** olmalı; biri eksikse kurtarma olmaz:

1. **Kurtarma token'ı** (parola yöneticinizde) — emaneti okur.
2. **`~/pemf-vault-kurtarma.json`** — Vault'un unseal anahtarları + kök token.
   ⚠️ Bu dosya Vault'un kendisini açar. **Başka bir makinede/USB'de** de durmalı.
3. **`pemf-vault-veri` Docker birimi** — emanetin kendisi. Aynı diskteyse disk kaybında o da
   gider; **kopyasını dışarı alın** (aşağıda).

Adımlar:

```powershell
# 1) Vault'u ayaga kaldir (yeni makinede: vault-veri birimini geri yukleyin)
docker compose -f docker/docker-compose.vault.yml up -d

# 2) Muhuru ac  (Vault her restart'ta MUHURLU baslar — bu normaldir)
python scripts/vault_emanet.py --ac

# 3) Anahtari al  (kurtarma token'i ile)
python scripts/vault_emanet.py --geri-al --token "hvs.…"

# 4) Hedef makinede <veri_koku>/pemf_secrets.json icine DUZ METIN yaz:
#      auto.sqlcipher_key       = <deger>
#      auto.patient_fernet_key  = <deger>
#    ("DPAPI:" oneki OLMADAN — backend ilk aciliste kendi sarar)
```

Sonra şifreli `patients.db` / `pemf_treatment_history.db` dosyalarını yerine koyup uygulamayı
açın.

---

## 4. Günlük kullanım

```powershell
python scripts/vault_emanet.py --durum      # muhurlu mu, emanet var mi
python scripts/vault_emanet.py --ac         # yeniden baslatma sonrasi ac
python scripts/vault_emanet.py --dogrula    # Vault kopyasi yerelle AYNI mi
python scripts/vault_emanet.py --yaz        # anahtar degistiyse emaneti TAZELE
```

⚠️ **`--dogrula`yı ara ara koşturun.** Anahtar bir gün yenilenirse (makine değişimi, sır
dosyası sıfırlanması) Vault'taki kopya **sessizce eskir** ve kurtarma işe yaramaz. Komut
parmak izlerini kıyaslar; anahtarı ekrana yazmaz.

### Emanetin kopyasını makine dışına alma

```powershell
docker run --rm -v pemf-vault-veri:/veri -v "${PWD}:/cikti" alpine `
  tar czf /cikti/pemf-vault-veri.tgz -C /veri .
```

Çıkan `pemf-vault-veri.tgz` + `pemf-vault-kurtarma.json` + kurtarma token'ı = tam kurtarma seti.
**Üçünü de aynı diskte tutmayın.**

---

## 5. Token neyi yapabilir, neyi yapamaz (ölçüldü)

| Deneme | Sonuç |
|---|---|
| Emaneti **okuma** | ✅ 200 — anahtarlar döndü |
| Emaneti **yazma** | ❌ 403 |
| Emaneti **silme** | ❌ 403 |
| `sys/mounts` (Vault'un geri kalanı) | ❌ 403 |

Token yalnız `pemf/data/klinik/hasta-anahtari` yolunu okur (`pemf-kurtarma` politikası),
`no_parent` ile üretildi → kök token iptal edilse bile yaşamaya devam eder.

---

## 6. Doğrulama kaydı (2026-09-13)

- Emanet yazıldı: `auto.sqlcipher_key` parmak `11b716577f0fb771`,
  `auto.patient_fernet_key` parmak `c59451bfe449ead6` — ikisi de yereldekiyle **aynı**.
- **Uçtan uca kurtarma:** kurtarma token'ıyla Vault'tan alınan anahtar, şifreli `patients.db`
  kopyasını **açtı** (`patients: 1 satır`, `patient_search_index: 6 satır`).
- **Karşıt kanıt:** yanlış anahtar `DatabaseError` ile **reddedildi** → test gerçekten ölçüyor.
- Denetim kaydı aktif (`/vault/logs/denetim.log`), konteyner `healthy`.
