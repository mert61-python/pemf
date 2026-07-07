// F-5 (prod-readiness): Expo `web.output: "single"` (SPA) modunda `app/+html.tsx` YOK SAYILIR →
// export sonrası üretilen dist/index.html'i düzelt: lang="tr" (UI %100 Türkçe; ekran-okuyucu
// telaffuzu + SEO) + tek-satır description + favicon (backend `/favicon.ico` sunar).
// Kullanım: `npm run export:web` (expo export --platform web && node scripts/postexport-web.js).
const fs = require("fs");
const path = require("path");

const f = path.join("dist", "index.html");
if (!fs.existsSync(f)) {
  console.error("postexport-web: dist/index.html YOK — önce `expo export --platform web`.");
  process.exit(1);
}
let h = fs.readFileSync(f, "utf8");
const before = h;

// 1) lang=tr (Expo varsayılanı "en"; UI Türkçe)
h = h.replace(/<html\s+lang="[a-zA-Z-]+"/, '<html lang="tr"');
if (!/<html\s+lang=/.test(h)) h = h.replace(/<html(\s|>)/, '<html lang="tr"$1');

// 2) description + favicon (yoksa <head> kapanışından önce ekle)
const inject = [];
if (!/name="description"/.test(h))
  inject.push('<meta name="description" content="PEMF Vet — veteriner PEMF terapi cihazı kontrol konsolu.">');
if (!/rel="icon"/.test(h)) inject.push('<link rel="icon" href="/favicon.ico">');
if (inject.length) h = h.replace("</head>", "  " + inject.join("\n  ") + "\n</head>");

if (h !== before) {
  fs.writeFileSync(f, h);
  console.log("postexport-web: lang=tr + description + favicon uygulandı → dist/index.html");
} else {
  console.log("postexport-web: değişiklik gerekmedi (zaten uygulanmış).");
}
