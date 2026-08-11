// Author: mertaygn, cglrgrkn
//! BOZUK İNDİRME → TEK SEFERLİK TEMİZ YENİDEN-DENEME.
//!
//! SAHA ŞİKÂYETİ (2026-08-11): kullanıcı güncellemede
//!   "SHA256 UYUŞMADI — dosya bozuk ya da değiştirilmiş"
//! gördü ve güncelleme DURDU. Oysa hem yayındaki paket hem sonradan inen kopya DOĞRUYDU
//! (ikisi de manifest sha'sıyla birebir ölçüldü) → bozulma indirme sırasında oluşan GEÇİCİ
//! bir durumdu.
//!
//! KUSUR: `ensure_package`'in 6-denemeli retry'ı YALNIZ ağ hatalarını kapsıyordu. "İndi ama
//! sha tutmadı" hâli döngünün DIŞINDAydı → kullanıcı elle tekrar denemek zorundaydı. Mesaj
//! ayrıca "değiştirilmiş" diyerek güvenlik olayı ima ediyordu.
//!
//! ⚠️ KAPSAM DÜRÜSTLÜĞÜ: uçtan uca (gerçek indirme) test EDİLEMİYOR — `net` katmanı yalnız
//! HTTPS + pinlenmiş host kabul eder (`NotHttps`), yerel test sunucusu reddedilir. Bu güvenlik
//! kontrolünü test için gevşetmek, korumayı testin hatırına zayıflatmak olurdu. Bu yüzden
//! burada telafinin ÇALIŞMASINI değil, **doğru davranmasını mümkün kılan değişmezler** ölçülür;
//! en kritiği `.part` adının tek kaynaktan gelmesidir (aşağıdaki ilk test).

use std::path::Path;

use pemf_launcher_core::net;

#[test]
fn KRITIK_part_adi_TEK_KAYNAK() {
    // Telafi kolu, temiz yeniden indirmeden önce `.part`'ı SİLER. Silinecek ad `net`in
    // kullandığıyla BİREBİR aynı olmalı; değilse yarım/bozuk `.part` diskte kalır, "temiz"
    // deneme yine Range ile onun üzerine ekler ve İKİNCİ deneme de kaçınılmaz başarısız olur
    // (yani düzeltme sessizce hiçbir şey yapmaz).
    //
    // Bu test, `flow`un kendi kopyasını tutmasını engellemek için var: ilk yazımda kopya
    // vardı ve KISA sha kolunda `net`ten FARKLI ad üretiyordu.
    let dest = Path::new("C:/onbellek/base-deps.zip");

    let uzun = net::part_path(dest, "b789896c2aa4e42966d302a953d46a90f689c36c");
    assert_eq!(
        uzun.file_name().unwrap().to_string_lossy(),
        "base-deps.b789896c2aa4.part",
        "uzun-sha `.part` adi degismis"
    );

    // Kısa sha (savunma kolu) — burada ayrışma olmuştu.
    let kisa = net::part_path(dest, "abc");
    assert_eq!(
        kisa.file_name().unwrap().to_string_lossy(),
        "base-deps.part",
        "kisa-sha kolunda ad ayrismis → yanlis dosya silinir"
    );

    // Farklı sha → farklı `.part`: sürüm değişince eski yarım dosya devam noktası SANILMAZ.
    assert_ne!(
        net::part_path(dest, "aaaaaaaaaaaa1111"),
        net::part_path(dest, "bbbbbbbbbbbb2222"),
        "farkli icerik ayni .part adini paylasiyor → melez dosya riski"
    );
}

#[test]
fn KRITIK_telafi_kolu_KODDA_var() {
    // Kaynak denetimi: sha uyuşmazlığından sonra yeniden indirme kolu duruyor mu?
    // (Uçtan uca test HTTPS pini yüzünden mümkün değil — bkz. modül notu.)
    let src = std::fs::read_to_string(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("src").join("flow.rs"),
    )
    .unwrap();

    let i = src.find("on(Progress::Verifying").expect("dogrulama adimi bulunamadi");
    let kuyruk = &src[i..];
    assert!(
        kuyruk.contains("temiz_yeniden_indirilebilir"),
        "sha uyusmazliginda TEK SEFERLIK temiz yeniden-indirme kolu kaldirilmis → kullanici \
         yine elle tekrar denemek zorunda kalir"
    );
    assert!(
        kuyruk.contains("net::part_path"),
        "temiz deneme `.part`i silmiyor → Range ile ayni bozuk baytlarin uzerine eklenir"
    );
    // Doğrulama İKİNCİ denemeden sonra da yapılmalı — yoksa telafi, sha kontrolünü atlatır.
    assert!(
        kuyruk.matches("verify::verify_file").count() >= 2,
        "ikinci denemeden sonra dogrulama yok → telafi sha kontrolunu ZAYIFLATIR"
    );
}

#[test]
fn KRITIK_iptal_duraklat_telafiyi_ENGELLER() {
    // Kullanıcı iptal/duraklat dediyse sessizce yeniden indirmeye başlamak, açık talimatı
    // yok saymak ve ölçülen indirme baytlarını şişirmektir.
    let src = std::fs::read_to_string(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("src").join("flow.rs"),
    )
    .unwrap();
    let i = src.find("fn temiz_yeniden_indirilebilir").expect("kapi fonksiyonu yok");
    let govde = &src[i..(i + 400).min(src.len())];
    assert!(
        govde.contains("Control::Continue"),
        "telafi kapisi Pause/Cancel'i dikkate almiyor"
    );
}
