// PEMF frontend ESLint (audit B-10.1). Flat config (ESLint 9+/10) + eslint-config-expo + prettier.
// Kademeli benimseme: mevcut kodda hata YAKALAR ama stil/any borcunu UYARI olarak gösterir → CI kırmaz,
// yeni kodda temizlik teşvik eder. `npm run lint` (raporla) | `npm run lint -- --fix` (düzelt).
const expoConfig = require("eslint-config-expo/flat");
const eslintConfigPrettier = require("eslint-config-prettier");

module.exports = [
  ...expoConfig,
  eslintConfigPrettier,
  {
    ignores: ["node_modules/", "dist/", ".expo/", "coverage/", "web-build/", "*.config.js"],
  },
  {
    rules: {
      // `any` borcu (audit B-2.4) UYARI — build kırmaz, görünür kalır. Kademeli error'a çekilebilir.
      "@typescript-eslint/no-explicit-any": "warn",
      // Kullanılmayan değişkenler UYARI. caughtErrors:none → `catch (e)` idiomatik (e okunmasa da geçerli).
      // Ölü import'lar/değişkenler temizlendi (B-10.1); kalan birkaç kopya-yapıştır dead-var UYARI (kademeli).
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" }],
      // Kademeli benimseme (audit B-10.1): yeni react-hooks kuralları (bleeding-edge plugin) mevcut
      // GEÇERLİ ama ideal-olmayan desenleri (ref-erişimi, effect'te setState) hata sayıyor → CI'yı
      // kırmasın diye UYARI (kademeli düzeltme).
      "react-hooks/refs": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn",
      // audit B-10.1: aşağıdaki 3 kural TAMAMEN temizlendi → ERROR'a yükseltildi (regresyon kilidi).
      "react/no-unescaped-entities": "error",
      "@typescript-eslint/array-type": "error",
      "import/no-duplicates": "error",
    },
  },
  {
    // Test dosyaları: jest globalleri + esnek kurallar.
    files: ["**/__tests__/**", "**/*.test.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "react-hooks/refs": "off",
      // jest.mock() hoisting gereği import'lardan ÖNCE gelir → import/first test'lerde geçersiz.
      "import/first": "off",
    },
  },
];
