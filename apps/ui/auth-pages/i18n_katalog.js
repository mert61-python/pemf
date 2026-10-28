// ÜRETİLMİŞ DOSYA — ELLE DÜZENLEMEYİN. Kaynak: apps/ui/src/i18n/{tr,en}/authSayfa.json · Üreteç: scripts/i18n/auth_uret.py
// (katalog / bayrak ile bu dosya ayrışırsa tests/test_i18n_auth_sayfa.py ve `bayrak.py --denetle` kırmızı.)
(function () {
  var K = {
    "en": {
      "authSayfa.ortak.uygulamayaDon": "Back to the App",
      "authSayfa.reset.aciklama": "Enter a new password for your account.",
      "authSayfa.reset.baslik": "Set a New Password",
      "authSayfa.reset.guncelle": "Update Password",
      "authSayfa.reset.guncellendiAciklama": "Go back to the app and sign in with your new password.",
      "authSayfa.reset.guncellendiBaslik": "Your password has been updated ✓",
      "authSayfa.reset.guncelleniyor": "Updating…",
      "authSayfa.reset.hata.ayni": "The new password cannot be the same as the old one.",
      "authSayfa.reset.hata.baglanti": "Connection error. Check your internet connection.",
      "authSayfa.reset.hata.basarisiz": "The operation failed. Please try again.",
      "authSayfa.reset.hata.cokDeneme": "Too many attempts. Wait a bit and try again.",
      "authSayfa.reset.hata.en6": "The password must be at least 8 characters.",
      "authSayfa.reset.hata.eslesmiyor": "Passwords do not match.",
      "authSayfa.reset.hata.kurallar": "The password must be at least 8 characters and include an uppercase letter, a lowercase letter, and a digit.",
      "authSayfa.reset.hata.sureDolmus": "The link has expired. Click the reset link in your email again.",
      "authSayfa.reset.hata.zayif": "The password is too weak — choose a stronger one.",
      "authSayfa.reset.sayfaBasligi": "PEMF Vet — Set a New Password",
      "authSayfa.reset.sifreTekrarYer": "New password (repeat)",
      "authSayfa.reset.sifreYer": "New password (at least 8 characters)",
      "authSayfa.verified.aciklama": "Your account has been verified. You can now go back to the <b>PEMF Vet</b> app and sign in with your email and password.",
      "authSayfa.verified.baslik": "Your email is verified!",
      "authSayfa.verified.kapatabilirsin": "You can safely close this tab.",
      "authSayfa.verified.sayfaBasligi": "PEMF Vet — Email Verified"
    },
    "tr": {
      "authSayfa.ortak.uygulamayaDon": "Uygulamaya Dön",
      "authSayfa.reset.aciklama": "Hesabın için yeni bir şifre gir.",
      "authSayfa.reset.baslik": "Yeni Şifre Belirle",
      "authSayfa.reset.guncelle": "Şifreyi Güncelle",
      "authSayfa.reset.guncellendiAciklama": "Uygulamaya dönüp yeni şifrenle giriş yapabilirsin.",
      "authSayfa.reset.guncellendiBaslik": "Şifren güncellendi ✓",
      "authSayfa.reset.guncelleniyor": "Güncelleniyor…",
      "authSayfa.reset.hata.ayni": "Yeni şifre eskisiyle aynı olamaz.",
      "authSayfa.reset.hata.baglanti": "Bağlantı hatası. İnternetini kontrol et.",
      "authSayfa.reset.hata.basarisiz": "İşlem başarısız. Lütfen tekrar dene.",
      "authSayfa.reset.hata.cokDeneme": "Çok fazla deneme. Biraz bekleyip tekrar dene.",
      "authSayfa.reset.hata.en6": "Şifre en az 8 karakter olmalı.",
      "authSayfa.reset.hata.eslesmiyor": "Şifreler eşleşmiyor.",
      "authSayfa.reset.hata.kurallar": "Şifre en az 8 karakter olmalı; büyük harf, küçük harf ve rakam içermeli.",
      "authSayfa.reset.hata.sureDolmus": "Bağlantı süresi dolmuş. E-postandaki sıfırlama linkine tekrar tıkla.",
      "authSayfa.reset.hata.zayif": "Şifre çok zayıf, daha güçlü bir şifre seç.",
      "authSayfa.reset.sayfaBasligi": "PEMF Vet — Yeni Şifre Belirle",
      "authSayfa.reset.sifreTekrarYer": "Yeni şifre (tekrar)",
      "authSayfa.reset.sifreYer": "Yeni şifre (en az 8 karakter)",
      "authSayfa.verified.aciklama": "Hesabın başarıyla doğrulandı. Artık <b>PEMF Vet</b> uygulamasına geri dönüp e-posta ve şifrenle giriş yapabilirsin.",
      "authSayfa.verified.baslik": "E-postan onaylandı!",
      "authSayfa.verified.kapatabilirsin": "Bu sekmeyi güvenle kapatabilirsin.",
      "authSayfa.verified.sayfaBasligi": "PEMF Vet — E-posta Onaylandı"
    }
  };
  var EN_ACIK = true; // i18n/bayrak.json — scripts/i18n/bayrak.py (elle değiştirmeyin)
  var dil = "tr";
  if (EN_ACIK) {
    var q = "";
    try { q = new URLSearchParams(window.location.search).get("dil") || ""; } catch (e) { q = ""; }
    var d = String(q || window.navigator.language || "tr").toLowerCase();
    dil = d.indexOf("tr") === 0 ? "tr" : "en";
  }
  window.PEMF_DIL = dil;
  window.tf = function (anahtar) {
    return (K[dil] && K[dil][anahtar]) || (K.tr && K.tr[anahtar]) || anahtar;
  };
  window.uygulaDil = function () {
    var kok = window.document;
    kok.documentElement.setAttribute("lang", dil);
    kok.querySelectorAll("[data-i18n]").forEach(function (e) { e.textContent = window.tf(e.getAttribute("data-i18n")); });
    kok.querySelectorAll("[data-i18n-html]").forEach(function (e) { e.innerHTML = window.tf(e.getAttribute("data-i18n-html")); });
    kok.querySelectorAll("[data-i18n-placeholder]").forEach(function (e) { e.setAttribute("placeholder", window.tf(e.getAttribute("data-i18n-placeholder"))); });
  };
})();
