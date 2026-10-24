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

/// Paylaşım durumu.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Durum {
    /// Gerekmez: Windows dışı / makine kökü yok / hasta veri dizini henüz yok (ilk hesap) / bu hesap veriye erişebiliyor.
    Gereksiz,
    /// Hasta veri dizini VAR ama bu hesap ona erişemiyor (başka hesabın) → tek seferlik yönetici adımı önerilir.
    /// `grup_var`: grup zaten kurulu (paylaşım daha önce kurulduysa bu hesap oturumu yenilememiş olabilir).
    Gerekli { grup_var: bool },
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
/// paylaşım hiç önerilmezdi).
pub fn veri_var_mi(dir: &Path) -> bool {
    let (Some(ust), Some(ad)) = (dir.parent(), dir.file_name()) else { return false };
    std::fs::read_dir(ust)
        .map(|it| it.flatten().any(|e| e.file_name().eq_ignore_ascii_case(ad)))
        .unwrap_or(false)
}

/// Bu hesap veri dizinini LİSTELEYİP içine YAZABİLİYOR mu (yaz + sil sondası — backend'in açılışta yaptığının özü).
pub fn erisilebilir_mi(dir: &Path) -> bool {
    std::fs::read_dir(dir).is_ok() && crate::install::dizin_yazilabilir_mi(dir)
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
    let veri_var = veri_var_mi(&dir);
    durum_karari(veri_var, veri_var && erisilebilir_mi(&dir), crate::install::grup_adindan_sid(GRUP_ADI).is_some())
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
    let aciklama = crate::firewall::ps_kacis(aciklama);
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
         & icacls.exe $kok /grant ('*' + $g.SID.Value + ':(OI)(CI)M') /T /C /Q | Out-Null; \
         if ($LASTEXITCODE -ne 0) {{ exit {izin} }}; \
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

    /// T-g: grup yoksa kurulur; bu hesap + veriyi kuran hesap (dizin SAHİBİ) üye olur; köke grubun `Değiştir` hakkı ağaçta verilir.
    #[test]
    fn KRITIK_T_g_betik_grubu_kurar_hesabi_ve_SAHIBI_ekler_DEGISTIR_verir() {
        let s = betik();
        let kur = s.find("New-LocalGroup -Name 'PEMF Data Users'").expect("grup kurulmuyor");
        assert!(s[..kur].contains("Get-LocalGroup -Name 'PEMF Data Users'"), "grup varken yeniden kurulmaya çalışılıyor");
        assert!(s.contains(&format!("$uyeler = @('{SID}')")), "bu hesap eklenmiyor");
        assert!(s.contains("GetOwner([Security.Principal.SecurityIdentifier])") && s.contains("$uyeler += $sahip"), "sahip eklenmiyor");
        assert!(s.contains("Add-LocalGroupMember -SID $g.SID -Member $s"));
        assert!(s.contains("'MemberExists*'"), "zaten üye olan hesap adımı düşürür");
        assert!(s.contains("icacls.exe $kok /grant ('*' + $g.SID.Value + ':(OI)(CI)M') /T"), "köke grup Değiştir hakkı yok");
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
}
