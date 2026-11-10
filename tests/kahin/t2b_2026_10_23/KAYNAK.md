# T2B tezgâh kareleri (2026-10-23) — KD sabit düzlem kapısı aparatı

Kaynak: `C:\Users\merta\Desktop\DENETIM\t2b\foto\` (Tezgâh-2B, rapor `DENETIM\TEZGAH-2B.md`). Kamera Pusat "FHD Camera" (`VID_1BCF&PID_28C4`),
1920×1080, tavan camının üstünde; kabin içi (taban camı, yeşil bobin halkaları, 24'lük pembe plaka, 10 cm ArUco işareti). Kişisel içerik YOK.
Depoya JPEG (kalite 88, OpenCV 4.11 `imencode`) olarak alındı — boyut için; özgün PNG'ler değişmedi.

| dosya | özgün PNG SHA-256 | JPEG SHA-256 | içerik |
|---|---|---|---|
| `son_01.jpg` | c5d5bdb12267e4b7cd2894e6a8cd2e9db7fda58015b93eb0284cc27da42be664 | 287be514ca98e0d4037fbb307018ef86b09a562375e94fa089c8f258fdc41cd9 | deney yeri; kamera eğimi ~15,3° (kalibrasyon karesi) |
| `son_02.jpg` | df919ed41d88e41a4e5c93bfd898084db3d61f832e14c6b437f4d57a747b2c9a | 0dc83e962a4201f56963157e2d236994261a79e7347c652cbef1b2cfa4de5e9f | aynı kamera, aynı yer (fantom YOK) |
| `k2_01.jpg` | e12d9e22e14133858bcf9b481a14535a9e0050b6448e038ad1359b2d2ad9adcd | 5dce5aefe2f3b83ae0a17ec17d23bc037845fe4139388db841ce42f3bae36702 | kamera eğimi ~12,8° (2,5° farklı), plaka konum 2 |

Ölçülen (KD): `son_01` referansına göre sabit sahne kayması `son_02` 0,14 px, `k2_01` 29,3 px. Fantom hattı `son_02`'de (fantomsuz) eskiden
16–25 "sürülebilir" tümör; sabit düzlem kipinde bulunan "fantom" 499 × 312 mm (ayar 104 × 65) → hedef YOK.
