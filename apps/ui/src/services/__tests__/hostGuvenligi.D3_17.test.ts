// Author: mertaygn, cglrgrkn
/**
 * D3.17 (B-6.2 · B-6.3) — host güvenliği yüklemi TEK kaynak: `isPrivateHost` baştaki sıfırlı oktetleri BAĞLANILACAK adresle
 * (inet_aton sekizliği) sınıflar; keşfin LAN yükseltmesi kendi ön-ek regex'i yerine aynı kaynağı kullanır.
 *
 * Ölçülen (HEAD): `isPrivateHost("010.0.0.1")` true (gerçekte 8.0.0.1, genel IP → jeton dışarı), `("172.016.0.1")` true (172.14.0.1);
 * keşif `/^(10\.|192\.168\.|172\.…)/` ön-ek regex'i `10.evil.com`'u LAN sayıyordu (adres + jeton kalıcı değişir). GERÇEK modüller.
 */
import { ipv4Oktetleri, isPrivateHost } from "@/services/apiClient";
import { lanYukseltmesiUygunMu } from "@/services/discovery";

test("KRİTİK B-6.2: baştaki sıfırlı oktet SEKİZLİK okunur — genel adres özel ağ sayılmaz", () => {
  expect(isPrivateHost("010.0.0.1")).toBe(false); // 8.0.0.1
  expect(isPrivateHost("172.016.0.1")).toBe(false); // 172.14.0.1
  expect(isPrivateHost("192.168.001.010")).toBe(true); // 192.168.1.8
  expect(isPrivateHost("10.0.0.08")).toBe(false); // geçersiz sekizlik
  expect(ipv4Oktetleri("192.168.001.010")).toEqual([192, 168, 1, 8]);
});

test("KARŞIT: düz yazımlı özel / genel adresler aynı", () => {
  for (const h of ["10.0.0.1", "192.168.1.20", "172.16.0.1", "172.31.255.255", "127.0.0.1", "localhost"]) expect(isPrivateHost(h)).toBe(true);
  for (const h of ["8.8.8.8", "172.15.0.1", "172.32.0.1", "10.evil.com", "1.2.3.256"]) expect(isPrivateHost(h)).toBe(false);
});

test("KRİTİK B-6.3: keşif LAN yükseltmesi tek kaynaktan — alan adı / sekizlik genel IP / döngü yükseltilmez", () => {
  for (const ip of ["10.evil.com", "192.168.attacker.net", "010.0.0.1", "172.016.0.1", "127.0.0.1", "0177.0.0.1", "localhost", ""]) {
    expect(lanYukseltmesiUygunMu(ip)).toBe(false);
  }
  for (const ip of ["192.168.137.1", "10.0.0.5", "172.20.1.2", "192.168.001.010"]) expect(lanYukseltmesiUygunMu(ip)).toBe(true);
});
