// Author: mertaygn, cglrgrkn
//! İKİNCİ WINDOWS HESABI — PAYLAŞILAN PEMF YEREL GRUBU (Y182 · S-YLI.1, sahip 2026-10-22; Y96 + S-LN.5 ile birlikte).
//!
//! SORUN (YLI-A3.1, ölçüldü 2026-10-22): hasta veri dizini (`%ProgramData%\PEMF_System\PEMF_GUI`) onu kuran hesaba kilitlidir
//! (backend `file_acl.lock_down_dir` kalıtımı kaldırır). İkinci bir Windows hesabı launcher'ı açınca veritabanı AÇILMAZ — görünür
//! arıza, veri bölünmez. Y96'nın paylaşılan grubu (`PEMF_DATA_GROUP_SID`) bugüne dek yalnız ELLE kurulabiliyordu ve adımı kurulum
//! belgesinde yoktu (S-LN.5).
//!
//! ÇÖZÜM (Y182): launcher durumu TESPİT EDER ve kullanıcının AÇIK onayıyla TEK SEFERLİK bir yönetici adımı (UAC) koşar: `GRUP_ADI`
//! yerel grubunu kurar (yoksa), bu hesabı ve veri dizininin SAHİBİ olan (veriyi kuran) hesabı gruba ekler, veri köküne grubun
//! `Değiştir` hakkını verir. Hasta verisi bu bilgisayarda gruptaki hesaplar arasında PAYLAŞILIR — KVKK açısından sahibin bilinçli
//! kararı. Grup üyeliği Windows oturumu yeniden açılınca geçerli olur. Launcher grubu ADIYLA bulur (`install::paylasilan_grup_sid`)
//! ve backend'e verir; backend kilitleri grubu açıkça korur (Y96, `file_acl`).
//!
//! ⚠️ GÜVENLİK — betik YÜKSELTİLMİŞ koşar:
//!   * Kullanıcı etkili HİÇBİR yol betiğe girmez: veri kökünü betik KENDİSİ çözer (`CommonApplicationData`). Launcher'ın
//!     `PROGRAMDATA` değişkeni kullanıcı tarafından değiştirilebilir; yükseltilmiş süreç çağıranın ortamını miras almaz.
//!   * Betiğe yalnız biçimi doğrulanmış hesap SID'i (`S-1-5-21-…`: rakam + tire) ve katalog açıklaması (kaçışlı) girer.
//!   * Ağaçta bağlantı noktası / sembolik bağ / sabit bağ varsa DURUR: yükseltilmiş `icacls /T` bağın HEDEFİNE (ör. sistem
//!     dosyası) grup hakkı yazardı — veri dizininin sahibi (standart hesap) böyle bir bağ yerleştirebilir.
//!   * Geniş gruplara (Users / Authenticated Users / Everyone) hak VERİLMEZ (Y96).
//!
//! Gerçek grup / ACL / UAC denemesi TEZGÂH-GÜNÜ'dür (D3 T-g); testler saf karar + betik metni + salt-okur arama yoludur.
//! #22 (T2Y, 11-11 GERÇEK deneme): backend'in KORUMALI kilitlediği dosyalar (sırlar, kimlik DB'si) dizin izninin kalıtımını ALMAZ —
//! betik dizindeki her öğeye ayrıca açık `Değiştir` verir.

use std::path::{Path, PathBuf};

/// Paylaşılan yerel grubun adı — kimliktir (launcher grubu bu adla bulur); ekranda görünen ACIKLAMA katalogdan gelir.
/// Güvenlik duvarı kural adları gibi ASCII ("PEMF Backend API"): kod sayfası / yerelleştirilmiş Windows farkı adı bozmasın.
pub const GRUP_ADI: &str = "PEMF Data Users";

/// Betiğin çıkış kodları (yükseltilmiş PowerShell) — `hata_anahtari` iletiye çevirir.
pub const KOD_TAMAM: i32 = 0;
pub const KOD_IZIN_VERILEMEDI: i32 = 3;
pub const KOD_BAG_BULUNDU: i32 = 4;
pub const KOD_VERI_YOK: i32 = 5;
/// `ERROR_CANCELLED` — kullanıcı UAC istemini reddetti (çağıran yükseltme sarmalayıcısı verir).
pub const KOD_UAC_REDDEDILDI: i32 = 1223;

/// #22 (T2Y, ÖLÇÜLDÜ 11-11): `New-LocalGroup -Description` en çok 48 karakter kabul eder — aşan metinde PowerShell parametre doğrulaması
/// betiği çıkış 1'e düşürür (paylaşım hiç kurulmaz). Katalog metni sınırın altında tutulur; betik ayrıca kırpar.
pub const ACIKLAMA_AZAMI: usize = 48;

/// Paylaşım durumu.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Durum {
    /// Gerekmez: Windows dışı / makine kökü yok / hasta veri dizini henüz yok (ilk hesap) / bu hesap veriye erişebiliyor.
    Gereksiz,
    /// Hasta veri dizini VAR ama bu hesap ona erişemiyor (başka hesabın) → tek seferlik yönetici adımı önerilir.
    /// `grup_var`: grup zaten kurulu (paylaşım daha önce kurulduysa bu hesap oturumu yenilememiş olabilir).
    Gerekli { grup_var: bool },
    /// #22 (T2Y, Y275): veri dizininin VARLIĞI ya da bu hesabın ERİŞİMİ belirlenemedi (üst dizin listelenemedi / izin dışı G/Ç
    /// hatası). Eskiden üst dizin okunamayınca "veri yok" sayılıp paylaşım hiç önerilmiyordu — arayüz kartı artık "paylaşım gerekli
    /// olabilir" metniyle ve aynı yönetici düğmesiyle gösterir.
    Belirsiz,
}

/// Saf karar (testli).
pub fn durum_karari(veri_var: bool, erisilebilir: bool, grup_var: bool) -> Durum {
    if veri_var && !erisilebilir {
        Durum::Gerekli { grup_var }
    } else {
        Durum::Gereksiz
    }
}

/// Makine-geneli hasta veri dizini (`<kök>\PEMF_GUI`) — backend'in launcher yolundaki veri dizini.
pub fn veri_dizini<F>(getenv: F) -> Option<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    Some(crate::install::machine_data_dir(getenv)?.join("PEMF_GUI"))
}

/// Veri dizini VAR mı — üst dizinin LİSTESİNDEN (erişilemeyen dizinin kendi öznitelikleri okunamayabilir; o zaman "yok" sanılıp
/// paylaşım hiç önerilmezdi). `None` = BELİRLENEMEDİ (#22): üst dizin var ama listelenemiyor (izin / G/Ç) — "yok" SAYILMAZ.
pub fn veri_varligi(dir: &Path) -> Option<bool> {
    let (Some(ust), Some(ad)) = (dir.parent(), dir.file_name()) else { return Some(false) };
    match std::fs::read_dir(ust) {
        Ok(it) => Some(it.flatten().any(|e| e.file_name().eq_ignore_ascii_case(ad))),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Some(false),
        Err(_) => None,
    }
}

/// `veri_varligi` — belirlenemezse `false`.
pub fn veri_var_mi(dir: &Path) -> bool {
    veri_varligi(dir).unwrap_or(false)
}

/// Bu hesap veri dizinini LİSTELEYİP içine YAZABİLİYOR mu (yaz + sil sondası — backend'in açılışta yaptığının özü).
/// `Some(false)`: listeleme İZİN hatası ya da yazılamıyor · `None` = BELİRLENEMEDİ (#22): izin dışı bir G/Ç hatası.
pub fn erisim(dir: &Path) -> Option<bool> {
    match std::fs::read_dir(dir) {
        Ok(_) => Some(crate::install::dizin_yazilabilir_mi(dir)),
        Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => Some(false),
        Err(_) => None,
    }
}

/// `erisim` — belirlenemezse `false`.
pub fn erisilebilir_mi(dir: &Path) -> bool {
    erisim(dir) == Some(true)
}

/// Bu makinedeki durum (dosya sistemi + salt-okur hesap araması).
pub fn durum_icin<F>(getenv: F) -> Durum
where
    F: Fn(&str) -> Option<String>,
{
    if !cfg!(windows) {
        return Durum::Gereksiz;
    }
    let Some(dir) = veri_dizini(&getenv) else { return Durum::Gereksiz };
    match veri_varligi(&dir) {
        None => Durum::Belirsiz,
        Some(false) => Durum::Gereksiz,
        Some(true) => match erisim(&dir) {
            None => Durum::Belirsiz,
            Some(erisilebilir) => durum_karari(true, erisilebilir, crate::install::grup_adindan_sid(GRUP_ADI).is_some()),
        },
    }
}

/// Arayüze (`paylasim_durumu` komutu) giden yanıt — `index.html` `paylasimKontrol` bu alanları okur. Komut görevi çökerse kabuk
/// `belirsiz_yaniti`nı verir (#22: kart susmaz).
pub fn arayuz_yaniti(d: Durum) -> serde_json::Value {
    match d {
        Durum::Gereksiz => serde_json::json!({ "gerekli": false }),
        Durum::Gerekli { grup_var } => serde_json::json!({ "gerekli": true, "grup_var": grup_var }),
        Durum::Belirsiz => serde_json::json!({ "belirsiz": true }),
    }
}

/// Durum yoklanamadı (komut görevi çöktü) — arayüz "paylaşım gerekli olabilir" kartını gösterir.
pub fn belirsiz_yaniti() -> serde_json::Value {
    arayuz_yaniti(Durum::Belirsiz)
}

/// Hesap SID'i biçimi: yerel / etki alanı hesabı (`S-1-5-21-<a>-<b>-<c>-<RID>`, yalnız rakam + tire). İş / okul (Azure AD,
/// `S-1-12-1-…`) ve yerleşik hesaplar REDDEDİLİR — betiğe başka hiçbir şey girmesin.
pub fn hesap_sid_bicimi_mi(sid: &str) -> bool {
    crate::install::ozel_grup_sid_bicimi_mi(sid)
}

/// Yükseltilmiş kurma betiği (PowerShell 5.1). `kullanici_sid`: launcher'ı çalıştıran (YÜKSELTİLMEMİŞ) hesap — yükseltilmiş süreç
/// başka bir yönetici hesabıyla da açılabilir, kimliği oradan okunmaz. Biçim tutmazsa `None` (betik üretilmez).
pub fn kurma_betigi(kullanici_sid: &str, aciklama: &str) -> Option<String> {
    if !hesap_sid_bicimi_mi(kullanici_sid) {
        return None;
    }
    let ad = crate::firewall::ps_kacis(GRUP_ADI);
    let kisa: String = aciklama.chars().take(ACIKLAMA_AZAMI).collect(); // #22: New-LocalGroup -Description <= 48 karakter
    let aciklama = crate::firewall::ps_kacis(&kisa);
    Some(format!(
        "$ErrorActionPreference='Stop'; \
         $kok = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'PEMF_System'; \
         $gui = Join-Path $kok 'PEMF_GUI'; \
         if (-not (Test-Path -LiteralPath $gui -PathType Container)) {{ exit {veri_yok} }}; \
         $yigin = New-Object System.Collections.Stack; $yigin.Push((Get-Item -LiteralPath $kok -Force)); \
         while ($yigin.Count -gt 0) {{ \
           $o = $yigin.Pop(); \
           if (($o.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $o.LinkType) {{ exit {bag} }}; \
           if ($o -is [IO.DirectoryInfo]) {{ foreach ($c in $o.GetFileSystemInfos()) {{ $yigin.Push($c) }} }} }}; \
         $g = Get-LocalGroup -Name '{ad}' -ErrorAction SilentlyContinue; \
         if (-not $g) {{ $g = New-LocalGroup -Name '{ad}' -Description '{aciklama}' }}; \
         $uyeler = @('{kullanici_sid}'); \
         $sahip = [IO.Directory]::GetAccessControl($gui).GetOwner([Security.Principal.SecurityIdentifier]).Value; \
         if ($sahip -match '^S-1-5-21-\\d+-\\d+-\\d+-\\d+$') {{ $uyeler += $sahip }}; \
         foreach ($s in ($uyeler | Select-Object -Unique)) {{ \
           try {{ Add-LocalGroupMember -SID $g.SID -Member $s -ErrorAction Stop }} \
           catch {{ if ($_.FullyQualifiedErrorId -notlike 'MemberExists*') {{ throw }} }} }}; \
         & icacls.exe $gui /grant ('*' + $g.SID.Value + ':(OI)(CI)M') /T /C /Q | Out-Null; \
         if ($LASTEXITCODE -ne 0) {{ exit {izin} }}; \
         if (@(Get-ChildItem -LiteralPath $gui -Force).Count -gt 0) {{ \
           & icacls.exe (Join-Path $gui '*') /grant ('*' + $g.SID.Value + ':M') /T /C /Q | Out-Null; \
           if ($LASTEXITCODE -ne 0) {{ exit {izin} }} }}; \
         exit {tamam}",
        veri_yok = KOD_VERI_YOK,
        bag = KOD_BAG_BULUNDU,
        izin = KOD_IZIN_VERILEMEDI,
        tamam = KOD_TAMAM,
    ))
}

/// Betik / yükseltme çıkış kodu → katalog anahtarı (TAMAM dışındaki her kod bir HATA iletisidir).
pub fn hata_anahtari(kod: i32) -> &'static str {
    match kod {
        KOD_UAC_REDDEDILDI => "rust.hata.yoneticiIzniVerilmedi",
        KOD_IZIN_VERILEMEDI => "rust.hata.paylasimIzinVerilemedi",
        KOD_BAG_BULUNDU => "rust.hata.paylasimBagBulundu",
        KOD_VERI_YOK => "rust.hata.paylasimVeriYok",
        _ => "rust.hata.paylasimBasarisiz",
    }
}

/// Bu SÜRECİN hesabının SID'i (`OpenProcessToken` + `TokenUser`) — salt-okur. Okunamazsa `None`.
#[cfg(windows)]
pub fn surec_hesabi_sid() -> Option<String> {
    use windows_sys::Win32::Foundation::{CloseHandle, LocalFree, HANDLE};
    use windows_sys::Win32::Security::Authorization::ConvertSidToStringSidW;
    use windows_sys::Win32::Security::{GetTokenInformation, TokenUser, TOKEN_QUERY, TOKEN_USER};
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};
    // SAFETY: belirteç tutamağı kapatılır; tampon `TOKEN_USER`'ı ve ardındaki SID'i taşıyacak boyutta (u64 hizalı) verilir;
    // ConvertSidToStringSidW'nin ayırdığı dize LocalFree ile bırakılır.
    unsafe {
        let mut belirtec: HANDLE = std::ptr::null_mut();
        if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut belirtec) == 0 {
            return None;
        }
        let mut tampon = [0u64; 64];
        let mut boy = 0u32;
        let ok = GetTokenInformation(
            belirtec,
            TokenUser,
            tampon.as_mut_ptr().cast(),
            std::mem::size_of_val(&tampon) as u32,
            &mut boy,
        ) != 0;
        CloseHandle(belirtec);
        if !ok {
            return None;
        }
        let kullanici = &*(tampon.as_ptr() as *const TOKEN_USER);
        let mut dize: windows_sys::core::PWSTR = std::ptr::null_mut();
        if ConvertSidToStringSidW(kullanici.User.Sid, &mut dize) == 0 || dize.is_null() {
            return None;
        }
        let mut n = 0usize;
        while *dize.add(n) != 0 {
            n += 1;
        }
        let s = String::from_utf16_lossy(std::slice::from_raw_parts(dize, n));
        LocalFree(dize as _);
        Some(s)
    }
}

#[cfg(not(windows))]
pub fn surec_hesabi_sid() -> Option<String> {
    None
}

#[allow(non_snake_case)]
#[cfg(test)]
mod tests {
    use super::*;

    const SID: &str = "S-1-5-21-1111111111-2222222222-3333333333-1001";

    fn betik() -> String {
        kurma_betigi(SID, "PEMF Vet: hesaplar").expect("geçerli SID'le betik üretilmeli")
    }

    /// T-g (Y182) ÖNCE-KIRMIZI: veri dizini VAR ama bu hesap erişemiyor → paylaşım GEREKLİ; ilk hesap / erişen hesap / veri yok → sus.
    #[test]
    fn KRITIK_T_g_erisemeyen_hesapta_paylasim_GEREKLI_der() {
        assert_eq!(durum_karari(true, false, false), Durum::Gerekli { grup_var: false });
        assert_eq!(durum_karari(true, false, true), Durum::Gerekli { grup_var: true });
        assert_eq!(durum_karari(true, true, true), Durum::Gereksiz, "erişen hesaba gereksiz yönetici istemi");
        assert_eq!(durum_karari(false, false, false), Durum::Gereksiz, "veri yokken (ilk hesap / yeni kurulum) istem");
    }

    /// T-g: betik kullanıcı etkili YOL ALMAZ — veri kökünü yükseltilmiş süreç kendisi çözer.
    #[test]
    fn KRITIK_T_g_betik_YOL_ALMAZ_koku_kendisi_cozer() {
        let s = betik();
        assert!(s.contains("[Environment]::GetFolderPath('CommonApplicationData')"), "kök betikte çözülmüyor: {s}");
        assert!(!s.to_ascii_lowercase().contains("$env:"), "betik ortam değişkeni okuyor (kullanıcı etkili)");
        assert!(!s.contains(":\\"), "betiğe mutlak yol girdi");
    }

    /// T-g: grup yoksa kurulur; bu hesap + veriyi kuran hesap (dizin SAHİBİ) üye olur; veri dizinine (`PEMF_GUI`) grubun `Değiştir` hakkı
    /// ağaçta verilir — D3I-A2.9 · Y182: kök (`PEMF_System`: broker yapılandırması, görev dosyaları) DEĞİL.
    #[test]
    fn KRITIK_T_g_betik_grubu_kurar_hesabi_ve_SAHIBI_ekler_DEGISTIR_verir() {
        let s = betik();
        let kur = s.find("New-LocalGroup -Name 'PEMF Data Users'").expect("grup kurulmuyor");
        assert!(s[..kur].contains("Get-LocalGroup -Name 'PEMF Data Users'"), "grup varken yeniden kurulmaya çalışılıyor");
        assert!(s.contains(&format!("$uyeler = @('{SID}')")), "bu hesap eklenmiyor");
        assert!(s.contains("GetOwner([Security.Principal.SecurityIdentifier])") && s.contains("$uyeler += $sahip"), "sahip eklenmiyor");
        assert!(s.contains("Add-LocalGroupMember -SID $g.SID -Member $s"));
        assert!(s.contains("'MemberExists*'"), "zaten üye olan hesap adımı düşürür");
        assert!(s.contains("icacls.exe $gui /grant ('*' + $g.SID.Value + ':(OI)(CI)M') /T"), "veri dizinine grup Değiştir hakkı yok");
        assert!(!s.contains("icacls.exe $kok"), "D3I-A2.9: kök (broker / görev dosyaları) gruba açılmaz — Y182: yalnız PEMF_GUI");
        assert!(s.contains("$gui = Join-Path $kok 'PEMF_GUI';"), "D3I-A2.9: hak hedefi `$gui` veri dizini (PEMF_GUI) değil — kök yeniden açılır");
        assert!(s.contains(&format!("exit {KOD_IZIN_VERILEMEDI}")), "icacls hatası yutuluyor");
    }

    /// T-g: Y96 — geniş gruplara hak VERİLMEZ; sahip yalnız oluşturulmuş hesapsa eklenir (Administrators sahip olabilir).
    #[test]
    fn KRITIK_T_g_betik_genis_gruplara_HAK_VERMEZ() {
        let s = betik();
        for yasak in ["S-1-5-32-545", "S-1-5-11", "S-1-1-0", "S-1-5-4", "Everyone", "*Users", "Authenticated"] {
            assert!(!s.contains(yasak), "betik geniş gruba dokunuyor: {yasak}");
        }
        assert!(s.contains("if ($sahip -match '^S-1-5-21-\\d+-\\d+-\\d+-\\d+$')"), "sahip süzülmüyor");
    }

    /// T-g: ağaçta bağ (bağlantı noktası / sembolik / sabit) varsa icacls'tan ÖNCE durur.
    #[test]
    fn KRITIK_T_g_agacta_BAG_varsa_hak_YAZMADAN_durur() {
        let s = betik();
        let bag = s.find(&format!("exit {KOD_BAG_BULUNDU}")).expect("bağ denetimi yok");
        assert!(s[..bag].contains("ReparsePoint") && s[..bag].contains("$o.LinkType"), "bağ türleri denetlenmiyor");
        assert!(bag < s.find("icacls.exe").expect("icacls yok"), "bağ denetimi hak yazımından SONRA");
        assert!(bag < s.find("New-LocalGroup").expect("grup yok"), "bağ varken grup kuruluyor");
    }

    /// T-g: betiğe YALNIZ biçimi tutan hesap SID'i girer.
    #[test]
    fn KRITIK_T_g_gecersiz_hesap_SID_ile_betik_URETILMEZ() {
        for kotu in [
            "",
            "S-1-5-32-545",
            "S-1-5-18",
            "S-1-12-1-111-222-333-444",
            "S-1-5-21-1-2-3",
            "S-1-5-21-1-2-3-4'; Remove-Item C:\\ -Recurse; '",
            "S-1-5-21-1-2-3-4\u{2019}; calc; \u{2019}",
        ] {
            assert!(kurma_betigi(kotu, "x").is_none(), "geçersiz SID kabul edildi: {kotu:?}");
        }
    }

    /// T-g: açıklama (katalog) tek tırnak ve AKILLI tırnaklarla dizeyi kapatamaz.
    #[test]
    fn T_g_aciklama_KACISLANIR() {
        let s = kurma_betigi(SID, "a'b\u{2019}c").unwrap();
        assert!(s.contains("-Description 'a''b\u{2019}\u{2019}c'"), "{s}");
    }

    /// #22 (T2Y, ÖLÇÜLDÜ 11-11 ikinci hesapta, paylaşım kurulduktan SONRA): backend sır / kimlik dosyalarını kalıtımı KAPATARAK kilitler
    /// (`file_acl.lock_down_file` → `pemf_secrets.json`, `.pemf_key`, `auth_users.db`). Dizine `(OI)(CI)` izni + `/T` bu KORUMALI
    /// dosyalara izin EKLEMEDİ (ACL ölçüldü: yalnız SYSTEM / Administrators / kuran hesap) → ikinci hesap sırları okuyamadı, DB'ler
    /// açılmadı. Betik dizindeki her öğeye AYRICA açık `M` verir (joker + `/T`); hata → çıkış 3; bağ denetiminden SONRA.
    #[test]
    fn KRITIK_IH22_korumali_dosyalara_da_grup_izni_ACIKCA_verilir() {
        let s = betik();
        let dizin = s.find("icacls.exe $gui /grant ('*' + $g.SID.Value + ':(OI)(CI)M') /T").expect("dizin izni yok");
        let oge = s.find("icacls.exe (Join-Path $gui '*') /grant ('*' + $g.SID.Value + ':M') /T /C /Q").expect("korumalı dosyalara açık izin yok");
        assert!(dizin < oge, "öğe izni dizin izninden önce");
        assert!(s[oge..].contains(&format!("if ($LASTEXITCODE -ne 0) {{ exit {KOD_IZIN_VERILEMEDI} }}")), "öğe izni hatası yutuluyor");
        assert!(s.find(&format!("exit {KOD_BAG_BULUNDU}")).unwrap() < oge, "bağ denetimi öğe izninden SONRA");
        assert!(s[..oge].contains("Get-ChildItem -LiteralPath $gui -Force"), "boş dizinde joker icacls hata verir — öğe varlığı denetlenmiyor");
    }

    /// #22 (T2Y, ÖLÇÜLDÜ 11-11 ikinci hesapta): `New-LocalGroup -Description` en çok 48 karakter — 67 karakterlik katalog metniyle
    /// betik `ParameterBindingValidationException` ile çıkış 1'e düşüyor, paylaşım HİÇ kurulamıyordu ("Paylaşım kurulamadı (kod 1)").
    /// Her dilin katalog metni sınırın altında VE betik uzun metni kırpar (gelecekteki çeviri sınırı aşsa da adım düşmez).
    #[test]
    fn KRITIK_IH22_grup_aciklamasi_48_karakteri_ASMAZ_katalog_ve_betik() {
        use crate::dil::{katalog, Dil};
        for d in [Dil::Tr, Dil::En] {
            let m = katalog(d).get("rust.paylasim.grupAciklamasi").expect("katalogda yok");
            assert!(m.chars().count() <= ACIKLAMA_AZAMI, "{d:?} grup açıklaması {} karakter: {m}", m.chars().count());
        }
        let uzun = format!("{}'{}", "ş".repeat(40), "x".repeat(40));
        let s = kurma_betigi(SID, &uzun).unwrap();
        let bas = s.find("-Description '").expect("açıklama yok") + "-Description '".len();
        let son = bas + s[bas..].find("' }").expect("açıklama sonu yok");
        let gercek = s[bas..son].replace("''", "'");
        assert_eq!(gercek.chars().count(), ACIKLAMA_AZAMI, "betikteki açıklama kırpılmadı: {gercek}");
        assert!(uzun.starts_with(&gercek));
    }

    /// T-g: her çıkış kodu eyleme dönük bir iletiye gider; iletiler iki dilde katalogda.
    #[test]
    fn T_g_hata_kodlari_KATALOG_iletisine_gider() {
        assert_eq!(hata_anahtari(KOD_UAC_REDDEDILDI), "rust.hata.yoneticiIzniVerilmedi");
        let mut anahtarlar = vec!["rust.paylasim.grupAciklamasi", "rust.hata.paylasimHesapOkunamadi", "rust.hata.paylasimHesapTuru"];
        for kod in [KOD_IZIN_VERILEMEDI, KOD_BAG_BULUNDU, KOD_VERI_YOK, 1, 7] {
            anahtarlar.push(hata_anahtari(kod));
        }
        assert_ne!(hata_anahtari(KOD_BAG_BULUNDU), hata_anahtari(1));
        for a in anahtarlar {
            // `t` katalogda olmayan anahtarda testte paniğe düşer.
            assert!(!crate::dil::t(a).is_empty(), "{a}");
        }
    }

    /// T-g: veri yok → gereksiz; veri var + erişilebilir → gereksiz (GERÇEK dosya sistemi; erişilemeyen dal saf kararda — gerçek ACL YOK).
    #[test]
    fn T_g_veri_dizini_sondasi_GERCEK_dosya_sistemi() {
        let kok = tempfile::tempdir().unwrap();
        let gui = kok.path().join("PEMF_GUI");
        assert!(!veri_var_mi(&gui));
        std::fs::create_dir(&gui).unwrap();
        assert!(veri_var_mi(&gui) && veri_var_mi(&kok.path().join("pemf_gui")), "liste karşılaştırması harf duyarlı");
        assert!(erisilebilir_mi(&gui));
        assert_eq!(std::fs::read_dir(&gui).unwrap().count(), 0, "erişim sondası artık bıraktı");
        let pd = kok.path().to_string_lossy().into_owned();
        let getenv = |k: &str| (k == "PROGRAMDATA").then(|| pd.clone());
        if cfg!(windows) {
            assert_eq!(veri_dizini(getenv), Some(kok.path().join("PEMF_System").join("PEMF_GUI")));
        }
    }

    /// T-g: GERÇEK arama yolu — salt-okur (grup KURULMAZ): olmayan grup bulunmaz; sürecin hesabı okunur.
    #[cfg(windows)]
    #[test]
    fn T_g_GERCEK_hesap_aramasi_salt_okur() {
        assert_eq!(crate::install::grup_adindan_sid("PEMF Data Users T-g yok 7f3c"), None);
        let sid = surec_hesabi_sid().expect("sürecin hesabı okunamadı");
        assert!(sid.starts_with("S-1-") && sid.bytes().all(|b| b.is_ascii_digit() || b == b'-' || b == b'S'), "{sid}");
    }

    // ═══ KP-3 C · `durum_icin` veri kökünü ENJEKTE edilen ortamdan çözer (gerçek ProgramData'ya bakmaz) ═══
    /// Makine kökü yoksa sus · veri dizini yoksa (ilk hesap) sus · veri var ve bu hesap erişebiliyorsa sus — yönetici istemi YOK.
    #[test]
    fn kp3_durum_icin_enjekte_kokten_karar_verir_erisen_hesaba_istem_yok() {
        assert_eq!(durum_icin(|_| None), Durum::Gereksiz, "makine kökü yokken paylaşım istendi");
        let d = tempfile::tempdir().unwrap();
        let pd = d.path().to_string_lossy().to_string();
        let ortam = |k: &str| (k == "PROGRAMDATA").then(|| pd.clone());
        assert_eq!(durum_icin(ortam), Durum::Gereksiz, "veri dizini yokken (ilk hesap) paylaşım istendi");
        let veri = veri_dizini(ortam).unwrap();
        assert!(veri.starts_with(d.path()), "veri dizini enjekte kökten çözülmedi: {}", veri.display());
        std::fs::create_dir_all(&veri).unwrap();
        assert!(veri_var_mi(&veri));
        assert_eq!(durum_icin(ortam), Durum::Gereksiz, "erişilebilen veri dizini için yönetici istemi");
    }

    // ═══ #22 (T2Y, Y275) · ikinci Windows hesabı: GERÇEK ACL ile — bu hesabın kendi geçici dizininde, test sonunda geri alınır ═══

    /// Geçici dizinde bu sürecin hesabına `(OI)(CI)` RET (oku + yaz) koyar; `Drop` reddi kaldırır (tempdir silinebilsin).
    #[cfg(windows)]
    struct Ret(PathBuf, String);
    #[cfg(windows)]
    impl Ret {
        fn koy(dir: &Path) -> Ret {
            let sid = format!("*{}", surec_hesabi_sid().expect("sürecin hesabı okunamadı"));
            let c = std::process::Command::new("icacls")
                .arg(dir)
                .args(["/deny", &format!("{sid}:(OI)(CI)(RX,W)"), "/C", "/Q"])
                .output()
                .expect("icacls başlatılamadı");
            assert!(c.status.success(), "ret konamadı: {}", String::from_utf8_lossy(&c.stderr));
            Ret(dir.to_path_buf(), sid)
        }
    }
    #[cfg(windows)]
    impl Drop for Ret {
        fn drop(&mut self) {
            let _ = std::process::Command::new("icacls").arg(&self.0).args(["/remove:d", &self.1, "/C", "/Q"]).output();
        }
    }

    #[cfg(windows)]
    fn veri_koku() -> (tempfile::TempDir, String, PathBuf) {
        let d = tempfile::tempdir().unwrap();
        let pd = d.path().to_string_lossy().into_owned();
        let gui = d.path().join("PEMF_System").join("PEMF_GUI");
        std::fs::create_dir_all(&gui).unwrap();
        std::fs::write(gui.join("pemf_secrets.json"), b"{}").unwrap();
        (d, pd, gui)
    }

    /// #22 ÖLÇÜLEN durum (Şükrü): veri dizini VAR, bu hesap onu listeleyemiyor + yazamıyor (GERÇEK ACL) → GEREKLİ ve arayüz yanıtı
    /// `gerekli: true`. (Kartın çıkmamasının nedeni bu karar DEĞİL — arayüz kartı siliyordu; bkz. tests/test_IH_22_*.)
    #[cfg(windows)]
    #[test]
    fn KRITIK_IH22_GERCEK_ACL_erisemeyen_hesapta_GEREKLI_ve_arayuz_yaniti() {
        let (_d, pd, gui) = veri_koku();
        let _ret = Ret::koy(&gui);
        assert!(std::fs::read_dir(&gui).is_err(), "ret uygulanmadı — ölçüm geçersiz");
        assert_eq!(erisim(&gui), Some(false), "izin hatası 'belirlenemedi' sayıldı");
        let ortam = |k: &str| (k == "PROGRAMDATA").then(|| pd.clone());
        let d = durum_icin(ortam);
        assert!(matches!(d, Durum::Gerekli { .. }), "erişemeyen hesapta {d:?}");
        assert_eq!(arayuz_yaniti(d)["gerekli"], serde_json::json!(true));
    }

    /// #22: üst dizin (`PEMF_System`) LİSTELENEMİYORSA veri "yok" SAYILMAZ (eskiden Gereksiz → kart hiç yok) → BELİRSİZ.
    #[cfg(windows)]
    #[test]
    fn KRITIK_IH22_GERCEK_ACL_ust_dizin_listelenemezse_BELIRSIZ_gereksiz_DEGIL() {
        let (_d, pd, gui) = veri_koku();
        let _ret = Ret::koy(gui.parent().unwrap());
        assert_eq!(veri_varligi(&gui), None);
        assert!(!veri_var_mi(&gui));
        let ortam = |k: &str| (k == "PROGRAMDATA").then(|| pd.clone());
        assert_eq!(durum_icin(ortam), Durum::Belirsiz);
    }

    /// #22: izin DIŞI hata (üst "dizin" aslında dosya) → belirlenemedi; üst dizin YOK → veri yok (ilk hesap, istem YOK).
    #[test]
    fn IH22_veri_varligi_ust_yoksa_YOK_ust_okunamazsa_BELIRLENEMEDI() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(veri_varligi(&d.path().join("yok").join("PEMF_GUI")), Some(false));
        let dosya = d.path().join("PEMF_System");
        std::fs::write(&dosya, b"x").unwrap();
        assert_eq!(veri_varligi(&dosya.join("PEMF_GUI")), None, "okunamayan üst dizin 'veri yok' sayıldı");
        assert_eq!(erisim(&dosya), None, "dizin olmayan yol 'erişilebilir / erişilemez' diye karara bağlandı");
        std::fs::create_dir(d.path().join("PEMF_GUI")).unwrap();
        assert_eq!(erisim(&d.path().join("PEMF_GUI")), Some(true));
    }

    /// #22: arayüz yanıtı — üç durum ayrı; görev çöküşü BELİRSİZ (eskiden `{}` → kart yok).
    #[test]
    fn KRITIK_IH22_arayuz_yaniti_uc_durum_ve_COKUS_belirsiz() {
        assert_eq!(arayuz_yaniti(Durum::Gereksiz), serde_json::json!({ "gerekli": false }));
        assert_eq!(arayuz_yaniti(Durum::Gerekli { grup_var: true }), serde_json::json!({ "gerekli": true, "grup_var": true }));
        assert_eq!(arayuz_yaniti(Durum::Belirsiz), serde_json::json!({ "belirsiz": true }));
        assert_eq!(belirsiz_yaniti(), serde_json::json!({ "belirsiz": true }));
    }
}
