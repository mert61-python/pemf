import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QTextDocument, QPageLayout, QPageSize
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtCore import QMarginsF

def generate_manual():
    # Use existing QApplication instance if available, otherwise create new one
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # HTML Content for the User Manual - Optimized for Qt PDF rendering
    html_content = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                line-height: 1.8; 
                color: #333; 
                margin: 20px; 
                padding: 10px;
                font-size: 12pt;
            }
            h1 { 
                color: #2d185a; 
                text-align: center; 
                border-bottom: 3px solid #6c2b8f; 
                padding-bottom: 15px; 
                margin-bottom: 25px; 
                font-size: 22pt;
            }
            h2 { 
                color: #6c2b8f; 
                margin-top: 30px; 
                border-bottom: 2px solid #ddd; 
                padding-bottom: 10px; 
                font-size: 16pt;
                page-break-before: always;
            }
            h3 { 
                color: #4a90e2; 
                margin-top: 20px; 
                font-size: 13pt;
            }
            h4 { 
                color: #555; 
                margin-top: 15px; 
                font-size: 12pt;
                font-weight: bold;
            }
            p { 
                margin-bottom: 12px; 
                font-size: 12pt;
                line-height: 1.8;
            }
            ul, ol { 
                margin-bottom: 15px; 
                padding-left: 25px;
                line-height: 1.8;
            }
            li { 
                margin-bottom: 8px; 
                font-size: 12pt;
            }
            .note { 
                background-color: #e3f2fd; 
                border-left: 4px solid #2196f3; 
                padding: 15px; 
                margin: 20px 0;
                border-radius: 4px;
            }
            .warning { 
                background-color: #fff9e6; 
                border-left: 4px solid #ff9800; 
                padding: 15px; 
                margin: 20px 0;
                border-radius: 4px;
            }
            .success { 
                background-color: #e8f5e9; 
                border-left: 4px solid #4caf50; 
                padding: 15px; 
                margin: 20px 0;
                border-radius: 4px;
            }
            .info { 
                background-color: #f0f4f8; 
                border-left: 4px solid #607d8b; 
                padding: 15px; 
                margin: 20px 0;
                border-radius: 4px;
            }
            .footer { 
                text-align: center; 
                font-size: 10pt; 
                color: #888; 
                margin-top: 50px; 
                border-top: 1px solid #ddd; 
                padding-top: 20px;
            }
            .highlight { 
                color: #d32f2f; 
                font-weight: bold;
            }
            .step-box { 
                background-color: #fafafa; 
                border: 2px solid #6c2b8f; 
                padding: 15px; 
                margin: 15px 0;
                border-radius: 5px;
            }
            .step-number { 
                display: inline-block; 
                background-color: #6c2b8f; 
                color: white; 
                width: 32px; 
                height: 32px; 
                text-align: center; 
                font-weight: bold; 
                margin-right: 10px;
                padding-top: 6px;
                border-radius: 50%;
            }
            .feature-box { 
                background-color: #f5f9ff; 
                border: 1px solid #90caf9; 
                padding: 12px; 
                margin: 12px 0;
                border-radius: 4px;
            }
            table { 
                border-collapse: collapse; 
                width: 100%; 
                margin: 20px 0; 
                font-size: 11pt;
            }
            th { 
                background-color: #6c2b8f; 
                color: white; 
                padding: 10px; 
                text-align: left;
                font-weight: bold;
            }
            td { 
                border: 1px solid #ddd; 
                padding: 8px;
                vertical-align: top;
            }
            tr:nth-child(even) { 
                background-color: #f9f9f9;
            }
            .toc { 
                background-color: #f5f5f5; 
                padding: 20px; 
                margin: 20px 0;
                border: 2px solid #ddd;
                border-radius: 5px;
            }
            .toc-item { 
                margin: 8px 0;
                font-size: 12pt;
                line-height: 1.8;
            }
            strong {
                font-weight: bold;
                color: #2d185a;
            }
            em {
                font-style: italic;
            }
        </style>
    </head>
    <body>
        <h1>PEMF Veteriner Tedavi Sistemi<br/>Kullanım Kılavuzu</h1>
        
        <p style="text-align: center; font-size: 14pt;"><strong>Veteriner Hekimler İçin Basitleştirilmiş Rehber</strong></p>
        <p style="text-align: center; font-size: 11pt; color: #666;">Sürüm 1.0</p>
        
        <div class="toc">
            <h3>İçindekiler</h3>
            <div class="toc-item"><strong>1.</strong> PEMF Tedavisi Nedir?</div>
            <div class="toc-item"><strong>2.</strong> Sistem Nasıl Çalışır?</div>
            <div class="toc-item"><strong>3.</strong> Tedavi Modları ve AI Sekmeleri</div>
            <div class="toc-item"><strong>4.</strong> İlk Kurulum (5 Dakikada)</div>
            <div class="toc-item"><strong>5.</strong> Tedavi Başlatma (Adım Adım)</div>
            <div class="toc-item"><strong>6.</strong> Akıllı AI Tedavisi</div>
            <div class="toc-item"><strong>7.</strong> Klinik Protokoller</div>
            <div class="toc-item"><strong>8.</strong> Sık Sorulan Sorular</div>
            <div class="toc-item"><strong>9.</strong> Güvenlik Bilgileri</div>
        </div>
        
        <h2>1. PEMF Tedavisi Nedir?</h2>
        
        <div class="info">
            <h4>Basit Anlatımla PEMF</h4>
            <p><strong>PEMF (Nabızlı Elektromanyetik Alan)</strong> tedavisi, düşük frekanslı manyetik dalgalar kullanarak:</p>
            <ul>
                <li>Hücreleri uyarır ve yenilenmeyi destekler</li>
                <li>Ağrı ve iltihabı azaltır</li>
                <li>Doku iyileşmesini hızlandırır</li>
                <li>İğne ve ilaç kullanmadan uygula

(non-invaziv)</li>
            </ul>
        </div>
        
        <h3>Ne İçin Kullanılır?</h3>
        <ul>
            <li><strong>Eklem ağrıları:</strong> Yaşlı köpeklerde artrit, kalça displazisi</li>
            <li><strong>Ameliyat sonrası:</strong> Dikiş iyileşmesi, ödem azaltma</li>
            <li><strong>Kas problemleri:</strong> Spazm, gerginlik, sportif yaralanmalar</li>
            <li><strong>Kronik ağrı:</strong> Uzun süreli rahatsızlıklarda destek tedavi</li>
            <li><strong>Genel sağlık:</strong> Yaşlı hayvanlarda yaşam kalitesi artırma</li>
        </ul>
        
        <h3>Sistem Özellikleri</h3>
        
        <div class="feature-box">
            <strong>8 Adet Kablosuz Bobin</strong><br/>
            WiFi ile çalışır. Hastanın farklı bölgelerine yerleştirin.
        </div>
        
        <div class="feature-box">
            <strong>Akıllı AI Önerileri</strong><br/>
            Hasta bilgilerini girin, yapay zeka sizin için en uygun tedavi ayarlarını hesaplar.
        </div>
        
        <div class="feature-box">
            <strong>Canlı Görüntüleme</strong><br/>
            Tedavi sırasında manyetik alan ve sıcaklık değerlerini grafikle izleyin.
        </div>
        
        <div class="feature-box">
            <strong>Hasta Takibi</strong><br/>
            Tüm tedaviler otomatik kaydedilir. Geçmiş seansları kolayca görüntüleyin.
        </div>
        <h2>2. Sistem Nasıl Çalışır?</h2>
        
        <h3>Ekran Bölümleri</h3>
        
        <div class="step-box">
            <h4>Üst Bar</h4>
            <ul>
                <li><strong>Saat:</strong> Sistem saati</li>
                <li><strong>Sessiz Mod:</strong> Sesleri aç/kapat</li>
                <li><strong>Kılavuz:</strong> Bu yardım dökümanı</li>
                <li><strong>ACİL DURDUR (Kırmızı):</strong> Tüm bobinleri anında durdurur</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4>Sol Panel</h4>
            
            <p><strong>Bobin Durumu:</strong></p>
            <ul>
                <li>🟢 Yeşil = Bobin bağlı ve hazır</li>
                <li>🔴 Kırmızı = Bobin bağlı değil</li>
            </ul>
            
            <p><strong>Hasta Kaydı:</strong></p>
            <ul>
                <li>Hasta adı, tür, ırk</li>
                <li>Yaş ve kilo (AI için önemli)</li>
                <li>Cinsiyet ve notlar</li>
            </ul>
            
            <p><strong>Aktif Seans:</strong></p>
            <ul>
                <li>Tedavi modu ve parametreler</li>
                <li>Kalan süre</li>
                <li>İlerleme çubuğu</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4>Orta Panel</h4>
            
            <p><strong>Canlı Grafik:</strong></p>
            <ul>
                <li>Yeşil çizgiler: Manyetik alan gücü</li>
                <li>Turuncu çizgiler: Bobin sıcaklığı</li>
                <li>Her saniye güncellenir</li>
            </ul>
            
            <p><strong>Bobin Butonları (1-8):</strong></p>
            <ul>
                <li>Gri: Bağlı değil</li>
                <li>Mavi: Bağlı ve seçili</li>
                <li>Yeşil: Aktif tedavi uyguluyor</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4>Alt Menü</h4>
            <ul>
                <li><strong>Sensör Verisi:</strong> Detaylı ölçüm değerleri</li>
                <li><strong>Birleşik Kontrol:</strong> Tedavi modları ve özel AI servisleri</li>
                <li><strong>Seans Geçmişi:</strong> Eski tedavileri görüntüle</li>
            </ul>
        </div>

        <h2>3. Tedavi Modları ve AI Sekmeleri</h2>
        
        <div class="info">
            <p><strong>Birleşik Kontrol</strong> ekranında aşağıdaki gelişmiş tedavi ve analiz sekmeleri bulunur:</p>
            <ul>
                <li><strong>Otomatik Mod:</strong> Belirlenen hazır protokollere göre tedavi uygular.</li>
                <li><strong>Manuel Mod:</strong> Hekimin parametreleri manuel ayarlamasını sağlar.</li>
                <li><strong>PEMF AI Mod:</strong> Hasta türü, kilosu ve yaşına göre tedavi önerisi sunar.</li>
                <li><strong>AI Pro:</strong> Bulut tabanlı gelişmiş Büyük Dil Modeli (LLM) aracılığıyla veteriner asistanlığı ve derin analizler sunar.</li>
                <li><strong>Kedi Hastalık Analizi:</strong> Kedi hastalar için semptom ve verilerden olası hastalık tahmini yapar.</li>
                <li><strong>Kedi Retikülosit Sayımı:</strong> Kan yayması veya numune görüntüleri üzerinden otomatik retikülosit hücre sayımı yapar.</li>
                <li><strong>Kedi Görüntü Analizi:</strong> Görüntü üzerinden kedi anatomisi tespiti ve hastalık sınıflandırması gerçekleştirir. (Landmark, Segmentasyon, Termal Analiz desteklidir)</li>
            </ul>
        </div>

        <h2>4. İlk Kurulum (5 Dakikada)</h2>
        
        <div class="success">
            <h4>Hazırlık</h4>
            <ul>
                <li>Bobinleri prize takın</li>
                <li>WiFi şifrenizi hazır bulundurun</li>
                <li>Android telefonunuzda "PEMF Vet Mobil" uygulaması yüklü olsun</li>
            </ul>
        </div>
        
        <h3>Bobin Kurulumu</h3>
        
        <div class="step-box">
            <h4><span class="step-number">1</span> Bobini Açın</h4>
            <p>Bobini prize takın ve güç düğmesine basın. LED yanıp sönmeye başlayacak.</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">2</span> Android Uygulamasını Açın</h4>
            <p>"PEMF Vet Mobil" uygulamasını açın → Ayarlar (⚙️) → "PEMF Cihazı WiFi Yardımcısı"</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">3</span> Cihazı Bulun</h4>
            <p>"PEMF Cihazlarını Tara" butonuna basın. Bobin listede görünecektir.</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">4</span> WiFi Ayarlarını Girin</h4>
            <p>Bobinin yanındaki "Bağlan" butonuna basın:</p>
            <ul>
                <li>WiFi ağınızı seçin</li>
                <li>Şifrenizi girin</li>
                <li>"Ayarları Gönder" butonuna basın</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">5</span> Bağlantıyı Doğrulayın</h4>
            <p>10-15 saniye sonra bobin LED'i 🟢 yeşil yanacaktır. Masaüstü uygulamasında da yeşil görünmelidir.</p>
        </div>
        
        <div class="success">
            <p><strong>Tamamlandı!</strong> Bobin kullanıma hazır. Diğer bobinler için 1-5 arası adımları tekrarlayın.</p>
        </div>
        
        <h3>Sorun Giderme</h3>
        
        <table>
            <tr>
                <th>Problem</th>
                <th>Çözüm</th>
            </tr>
            <tr>
                <td>Bobin listede yok</td>
                <td>Telefonun WiFi'si açık mı? Bobini yeniden başlatın</td>
            </tr>
            <tr>
                <td>Şifre kabul edilmiyor</td>
                <td>Büyük/küçük harfe dikkat edin. WiFi 2.4 GHz olmalı (5 GHz değil)</td>
            </tr>
            <tr>
                <td>Yeşil yanmıyor</td>
                <td>30-60 saniye bekleyin. Hala yanmazsa kurulumu tekrarlayın</td>
            </tr>
        </table>

        <h2>5. Tedavi Başlatma (Adım Adım)</h2>
        
        <div class="success">
            <h4>Başlamadan Önce Kontrol</h4>
            <ul>
                <li>En az 1 bobin 🟢 yeşil yanıyor mu?</li>
                <li>Hasta bilgileri kaydedildi mi?</li>
                <li>Hasta rahat pozisyonda mı?</li>
                <li>Bobinler doğru yere yerleştirildi mi?</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">1</span> Bağlantı Kontrolü</h4>
            <p>Sol panelde "Bobin Durumu" bölümünü kontrol edin:</p>
            <ul>
                <li>🟢 Yeşil = Hazır</li>
                <li>🔴 Kırmızı = Bobin bağlı değil (Bölüm 4'e dönün)</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">2</span> Hasta Bilgilerini Girin</h4>
            <p>Sol panelde "Hasta Kaydı" formunu doldurun:</p>
            <ul>
                <li><strong>Ad:</strong> Hayvanın adı (Max, Minnoş, vb.)</li>
                <li><strong>Tür:</strong> Köpek / Kedi / At / Diğer</li>
                <li><strong>Irk:</strong> Golden Retriever, Tekir, vb.</li>
                <li><strong>Yaş:</strong> Yıl cinsinden (örn: 3)</li>
                <li><strong>Kilo:</strong> Kg cinsinden (örn: 25.5) - <span class="highlight">AI için çok önemli!</span></li>
                <li><strong>Cinsiyet:</strong> Erkek / Dişi</li>
                <li><strong>Notlar:</strong> İsteğe bağlı</li>
            </ul>
            <p>"Hastayı Kaydet" butonuna basın.</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">3</span> Tedavi Modunu Seçin</h4>
            <p>Alt menüden "Birleşik Kontrol" butonuna basın. 3 mod göreceksiniz:</p>
            
            <h4>MANUEL MOD</h4>
            <p>Kendiniz ayarlamak istiyorsanız:</p>
            <ul>
                <li><strong>Frekans:</strong> 50-150 Hz (Düşük = rahatlama, Yüksek = ağrı)</li>
                <li><strong>Yoğunluk:</strong> %0-100 (Küçük hayvan = düşük, Büyük hayvan = yüksek)</li>
                <li><strong>Süre:</strong> 5-60 dakika</li>
                <li><strong>Bobin Seçimi:</strong> Kullanmak istediğiniz bobinleri işaretleyin</li>
            </ul>
            <p>"▶️ Manuel Tedavi Başlat" butonuna basın</p>
            
            <h4>OTONOM MOD</h4>
            <p>Hazır protokol kullanmak istiyorsanız:</p>
            <ul>
                <li>Menüden protokol seçin (Artrit, Kas Ağrısı, İyileşme, vb.)</li>
                <li>Parametreler otomatik ayarlanır</li>
                <li>Bobinleri seçin</li>
            </ul>
            <p>"▶️ Otonom Tedavi Başlat" butonuna basın</p>
            
            <h4>AI MOD (ÖNERİLEN)</h4>
            <p>Akıllı öneri almak istiyorsanız:</p>
            <ul>
                <li>Tedavi hedefini seçin</li>
                <li>"AI Önerisi Al" butonuna basın</li>
                <li>1-2 saniyede öneriler hazırlanır</li>
                <li>İsterseniz önerileri düzenleyin</li>
            </ul>
            <p>"▶️ AI Tedavi Başlat" butonuna basın</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">4</span> Tedavi İzleme</h4>
            <p>Tedavi başladıktan sonra:</p>
            <ul>
                <li><strong>Grafik:</strong> Yeşil çizgiler (manyetik alan), Turuncu çizgiler (sıcaklık)</li>
                <li><strong>Sol Panel:</strong> Kalan süre, ilerleme çubuğu</li>
                <li><strong>Sıcaklık:</strong> 40°C'yi geçmemeli</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">5</span> Tedavi Bitişi</h4>
            <p><strong>Otomatik:</strong> Süre bitince sistem otomatik durur, rapor gösterilir</p>
            <p><strong>Manuel:</strong> Erken bitirmek için "Bobin Kapat" butonuna basın</p>
            <p><strong>Acil:</strong> Üst bardaki KIRMIZI butona basın (sadece acil durumlarda!)</p>
        </div>
        
        <div class="note">
            <h4>İpuçları</h4>
            <ul>
                <li>İlk tedavilerde düşük yoğunluk tercih edin</li>
                <li>Hastayı tedavi sırasında gözlemleyin</li>
                <li>Seansları "Seans Geçmişi" menüsünden görebilirsiniz</li>
            </ul>
        </div>

        <h2>6. Akıllı AI Tedavisi</h2>
        
        <div class="success">
            <h4>AI Neden Kullanılmalı?</h4>
            <ul>
                <li>Hasta bilgilerine özel tedavi önerir</li>
                <li>1-2 saniyede hesaplama yapar</li>
                <li>Veteriner literatürüne dayalı protokoller kullanır</li>
                <li>Güvenli sınırlar içinde çalışır (50-150 Hz)</li>
            </ul>
        </div>
        
        <h3>AI Nasıl Çalışır?</h3>
        <p>Sistem şunları dikkate alır:</p>
        <ul>
            <li><strong>Tür:</strong> Köpek metabolizması kediden farklı</li>
            <li><strong>Yaş:</strong> Genç hızlı iyileşir, yaşlıda düşük yoğunluk</li>
            <li><strong>Kilo:</strong> 5 kg kedi ile 30 kg köpek farklı doz</li>
            <li><strong>Tedavi Hedefi:</strong> Artrit için 75 Hz, akut ağrı için 125 Hz</li>
        </ul>
        
        <h3>AI Tedavi Başlatma</h3>
        
        <div class="step-box">
            <h4><span class="step-number">1</span> Hasta Bilgilerini Girin</h4>
            <p><span class="highlight">Mutlaka doldurun:</span> Tür, Yaş, Kilo</p>
            <p>Kilo bilgisi yoksa AI çalışmaz!</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">2</span> AI Modunu Açın</h4>
            <p>"Birleşik Kontrol" → "AI Mod" sekmesi</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">3</span> Tedavi Hedefini Seçin</h4>
            <ul>
                <li>Osteoartrit (Eklem ağrısı)</li>
                <li>Kas Ağrısı (Spazm, gerginlik)</li>
                <li>Doku İyileşmesi (Ameliyat sonrası)</li>
                <li>Ödem Azaltma (Şişlik)</li>
                <li>Ağrı Yönetimi (Kronik/akut)</li>
                <li>Genel Rahatlama (Stres azaltma)</li>
            </ul>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">4</span> Öneri Alın</h4>
            <p>"AI Önerisi Al" butonuna basın. Örnek:</p>
            <div class="info">
                <p><strong>Hasta:</strong> Max (Köpek, 8 yaş, 32 kg)<br>
                <strong>Hedef:</strong> Osteoartrit<br>
                <strong>Öneri:</strong> 75 Hz, %65 yoğunluk, 30 dk</p>
            </div>
            <p>Önerileri isterseniz düzenleyebilirsiniz.</p>
        </div>
        
        <div class="step-box">
            <h4><span class="step-number">5</span> Tedavi Başlat</h4>
            <p>Bobinleri seçin → "▶️ AI Tedavi Başlat"</p>
        </div>
        
        <h3>Öneri Tablosu</h3>
        <table>
            <tr>
                <th>Durum</th>
                <th>Frekans</th>
                <th>Yoğunluk</th>
                <th>Süre</th>
            </tr>
            <tr>
                <td>Eklem ağrısı</td>
                <td>70-80 Hz</td>
                <td>%55-75</td>
                <td>25-35 dk</td>
            </tr>
            <tr>
                <td>Kas ağrısı</td>
                <td>90-110 Hz</td>
                <td>%60-80</td>
                <td>20-30 dk</td>
            </tr>
            <tr>
                <td>İyileşme</td>
                <td>110-130 Hz</td>
                <td>%70-90</td>
                <td>30-40 dk</td>
            </tr>
            <tr>
                <td>Ödem</td>
                <td>90-110 Hz</td>
                <td>%55-70</td>
                <td>20-30 dk</td>
            </tr>
        </table>
        
        <div class="warning">
            <h4>Önemli</h4>
            <p>AI önerileri destek amaçlıdır. Veteriner hekim:</p>
            <ul>
                <li>Önerileri kontrol etmelidir</li>
                <li>Parametreleri değiştirebilir</li>
                <li>Hastayı tedavi sırasında izlemelidir</li>
            </ul>
        </div>

        <h2>7. Klinik Protokoller</h2>
        
        <h3>Yaygın Durumlar İçin Ayarlar</h3>
        
        <table>
            <tr>
                <th>Durum</th>
                <th>Frekans</th>
                <th>Yoğunluk</th>
                <th>Süre</th>
                <th>Sıklık</th>
            </tr>
            <tr>
                <td><strong>Eklem Ağrısı/Artrit</strong></td>
                <td>70-80 Hz</td>
                <td>%50-75</td>
                <td>25-35 dk</td>
                <td>Haftada 3-5 kez</td>
            </tr>
            <tr>
                <td><strong>Kas Ağrısı/Spazm</strong></td>
                <td>90-110 Hz</td>
                <td>%60-80</td>
                <td>20-30 dk</td>
                <td>Günlük (akut), 3x/hafta (kronik)</td>
            </tr>
            <tr>
                <td><strong>Ameliyat Sonrası İyileşme</strong></td>
                <td>110-130 Hz</td>
                <td>%70-90</td>
                <td>30-40 dk</td>
                <td>Günlük (ilk hafta), sonra gün aşırı</td>
            </tr>
            <tr>
                <td><strong>Ödem/Şişlik</strong></td>
                <td>90-110 Hz</td>
                <td>%55-70</td>
                <td>20-30 dk</td>
                <td>Günde 2 kez (akut), günlük (kronik)</td>
            </tr>
            <tr>
                <td><strong>Akut Ağrı</strong></td>
                <td>115-135 Hz</td>
                <td>%70-85</td>
                <td>20-25 dk</td>
                <td>İhtiyaca göre</td>
            </tr>
            <tr>
                <td><strong>Kronik Ağrı</strong></td>
                <td>90-110 Hz</td>
                <td>%60-75</td>
                <td>30-35 dk</td>
                <td>Gün aşırı</td>
            </tr>
            <tr>
                <td><strong>Rahatlama/Stres</strong></td>
                <td>50-60 Hz</td>
                <td>%40-60</td>
                <td>15-25 dk</td>
                <td>Haftada 2-3 kez</td>
            </tr>
        </table>
        
        <h3>Hayvan Türüne Göre Yoğunluk</h3>
        
        <table>
            <tr>
                <th>Tür/Boyut</th>
                <th>Yoğunluk</th>
                <th>Seans Süresi</th>
            </tr>
            <tr>
                <td>Küçük köpek (< 10 kg)</td>
                <td>%40-60</td>
                <td>15-20 dk</td>
            </tr>
            <tr>
                <td>Orta köpek (10-25 kg)</td>
                <td>%50-70</td>
                <td>20-30 dk</td>
            </tr>
            <tr>
                <td>Büyük köpek (25-45 kg)</td>
                <td>%60-80</td>
                <td>30-40 dk</td>
            </tr>
            <tr>
                <td>Dev köpek (> 45 kg)</td>
                <td>%70-90</td>
                <td>35-45 dk</td>
            </tr>
            <tr>
                <td>Kedi (tüm boyutlar)</td>
                <td>%35-55</td>
                <td>15-20 dk</td>
            </tr>
            <tr>
                <td>At</td>
                <td>%75-95</td>
                <td>40-60 dk</td>
            </tr>
            <tr>
                <td>Küçük memeli (tavşan vb.)</td>
                <td>%30-45</td>
                <td>10-15 dk</td>
            </tr>
        </table>
        
        <h3>Pratik İpuçları</h3>
        
        <div class="feature-box">
            <strong>Bobin Yerleştirme:</strong><br/>
            • Eklem sorunları: Eklemin çevresine<br/>
            • Ameliyat bölgesi: Dikişin etrafına (üzerine değil)<br/>
            • Ödem: Şişliğin çevresinden başlayın
        </div>
        
        <div class="feature-box">
            <strong>Tedavi Zamanlaması:</strong><br/>
            • Akut durumlar: İlk 2-3 hafta yoğun (günlük/gün aşırı)<br/>
            • Kronik durumlar: Haftada 2-3 kez bakım seansı<br/>
            • İlk iyileşme: Genellikle 3-5 seans sonrası görülür
        </div>
        
        <div class="info">
            <h4>Önemli Notlar</h4>
            <ul>
                <li>İlk tedavilerde düşük yoğunlukla başlayın</li>
                <li>Yaşlı ve hassas hayvanlarda daha dikkatli olun</li>
                <li>Hastayı tedavi sırasında sürekli gözlemleyin</li>
                <li>Sıcaklık 40°C'yi geçmemeli</li>
                <li>Tedavi sonrası 30 dk istirahat ettirin</li>
            </ul>
        </div>

        <h2>8. Sık Sorulan Sorular</h2>
        
        <h3>Bağlantı Sorunları</h3>
        
        <table>
            <tr>
                <th>Sorun</th>
                <th>Çözüm</th>
            </tr>
            <tr>
                <td>Bobin kırmızı (bağlı değil)</td>
                <td>• Güç kablosunu kontrol edin<br>
                • WiFi modemi çalışıyor mu?<br>
                • Bobini yeniden başlatın (güç tuşu 5 sn)<br>
                • Android uygulamasından yeniden kur</td>
            </tr>
            <tr>
                <td>Bobin aniden kopuyor</td>
                <td>• WiFi sinyali zayıf olabilir<br>
                • Modeme yaklaştırın<br>
                • 30-60 sn bekleyin (otomatik bağlanır)<br>
                • Modemi yeniden başlatın</td>
            </tr>
            <tr>
                <td>Grafikte veri yok</td>
                <td>• Bobin butonu seçili mi?<br>
                • Tedavi başlatıldı mı?<br>
                • Bobin yeşil yanıyor mu?</td>
            </tr>
            <tr>
                <td>Grafik donuyor</td>
                <td>• Çok fazla bobin aktif (6+ bobin)<br>
                • Bilgisayar performansı düşük<br>
                • Uygulamayı yeniden başlatın</td>
            </tr>
        </table>
        
        <h3>Sıcaklık Uyarıları</h3>
        
        <table>
            <tr>
                <th>Sorun</th>
                <th>Çözüm</th>
            </tr>
            <tr>
                <td>"Yüksek Sıcaklık" uyarısı</td>
                <td>• Bobin 40°C'yi geçti<br>
                • Havalandırmayı artırın<br>
                • Bobin üzerine örtü koymayın<br>
                • Oda sıcaklığı 25°C altında olsun</td>
            </tr>
            <tr>
                <td>Bobin çalışmıyor</td>
                <td>• Tedavi başlatıldı mı?<br>
                • Bobin seçili mi?<br>
                • Yoğunluk %0'da mı?<br>
                • Aşırı ısınma modu aktif mi?</td>
            </tr>
        </table>
        
        <h3>Yazılım Sorunları</h3>
        
        <table>
            <tr>
                <th>Sorun</th>
                <th>Çözüm</th>
            </tr>
            <tr>
                <td>Uygulama açılmıyor</td>
                <td>• Uygulamayı tam kapatıp yeniden açın<br>
                • Bilgisayarı yeniden başlatın<br>
                • Antivirüsü kontrol edin<br>
                • Yönetici olarak çalıştırın</td>
            </tr>
            <tr>
                <td>"Hasta kaydedilemedi"</td>
                <td>• Tüm alanlar dolduruldu mu?<br>
                • Yaş ve kilo sayı mı?<br>
                • Disk dolu olabilir</td>
            </tr>
            <tr>
                <td>"AI önerisi alınamadı"</td>
                <td>• Hasta bilgileri tam mı?<br>
                • Kilo 0'dan büyük mü?<br>
                • Tedavi hedefi seçildi mi?</td>
            </tr>
        </table>
        
        <div class="warning">
            <h4>Acil Durum</h4>
            <p>Hasta tehlikede veya yangın/duman varsa:</p>
            <ul>
                <li>Üst bardaki KIRMIZI "ACİL DURDUR" butonuna basın</li>
                <li>Güç kablolarını çekin</li>
                <li>Hastayı güvenli alana alın</li>
                <li>Gerekirse 112'yi arayın</li>
            </ul>
        </div>

        <h2>9. Güvenlik Bilgileri</h2>
        
        <div class="warning">
            <h3>KULLANILMAMALI (Kontrendikasyonlar)</h3>
            <ul>
                <li><strong>Kalp pili:</strong> Kesinlikle kullanmayın</li>
                <li><strong>Hamile hayvan:</strong> Özellikle ilk 3 ay</li>
                <li><strong>Aktif kanama:</strong> İç kanama veya kanama bozukluğu</li>
                <li><strong>Yüksek ateş:</strong> 39.5°C üzeri ateş</li>
                <li><strong>Tümör bölgesi:</strong> Bilinen tümöre direkt uygulama yapmayın</li>
                <li><strong>Epilepsi:</strong> Aktif nöbet geçmişinde dikkatli olun</li>
            </ul>
        </div>
        
        <div class="warning">
            <h3>Elektrik Güvenliği</h3>
            <ul>
                <li>Nemli ortamda kullanmayın</li>
                <li>Kablo hasarlı olmamalı</li>
                <li>Topraklı priz kullanın</li>
                <li>Sıvılardan uzak tutun</li>
                <li>Hasarlı bobini kullanmayın</li>
            </ul>
        </div>
        
        <div class="success">
            <h3>Güvenli Kullanım</h3>
            <ul>
                <li>Bobinleri her tedaviden önce kontrol edin</li>
                <li>İlk tedavilerde düşük yoğunluk kullanın</li>
                <li>Günde maksimum 2 seans (6 saat arayla)</li>
                <li>Hastayı tedavi sırasında izleyin</li>
                <li>Tedavi öncesi ve sonrası su verin</li>
                <li>Tedavi sonrası 30 dk istirahat</li>
            </ul>
        </div>
        
        <div class="info">
            <h3>Veteriner Hekim Sorumluluğu</h3>
            <p>Bu sistem <strong>sadece lisanslı veteriner hekimler</strong> tarafından kullanılmalıdır.</p>
            <p>Veteriner hekim:</p>
            <ul>
                <li>Hastayı muayene etmeli</li>
                <li>Kontrendikasyonları değerlendirmeli</li>
                <li>Tedavi protokolünü belirlemeli</li>
                <li>Tedavi sırasında izlemeli</li>
                <li>İstenmeyen etkileri kaydetmeli</li>
                <li>Hasta sahibini bilgilendirmeli</li>
            </ul>
        </div>
                <li>Hasta sahibinden bilgilendirilmiş onam alın</li>
                <li>Tedavi öncesi ve sonrası fotoğraf çekin (ilerleme takibi için)</li>
                <li>Düzenli olarak tedavi etkinliğini değerlendirin</li>
                <li>Sistemin bakımını düzenli yapın</li>
                <li>Yazılımı güncel tutun</li>
                <li>Personeli düzenli eğitin</li>
            </ul>
        </div>
        
        <div class="footer">
            <p><strong>PEMF Vet Sistemi - Kullanım Kılavuzu</strong></p>
            <p>&copy; 2025 PEMF Veterinary Technologies. Tüm hakları saklıdır.</p>
            <p>Bu kılavuz, cihazın güvenli ve etkili kullanımı için hazırlanmıştır.</p>
            <p><strong>Versiyon:</strong> 1.0 | <strong>Son Güncelleme:</strong> Aralık 2025</p>
            <p><strong>İletişim:</strong> info@pemfvet.com | <strong>Web:</strong> www.pemfvet.com</p>
            <p><em>Veteriner hekimlerin sağlığı için teknolojik çözümler.</em></p>
        </div>
    </body>
    </html>
    """

    doc = QTextDocument()
    doc.setHtml(html_content)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    
    # Determine output path
    base_path = Path(__file__).parent
    resources_path = base_path / "pemf_gui" / "resources"
    
    # Create directories if they don't exist
    docs_path = resources_path / "docs"
    docs_path.mkdir(parents=True, exist_ok=True)
    
    output_file = docs_path / "Kullanim_Klavuzu.pdf"
    printer.setOutputFileName(str(output_file))
    
    # Set page size (A4)
    page_layout = QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait,
        QMarginsF(15, 15, 15, 15),
        QPageLayout.Unit.Millimeter
    )
    printer.setPageLayout(page_layout)

    doc.print(printer)
    print(f"PDF Generated successfully at: {output_file}")
    return str(output_file)

if __name__ == "__main__":
    generate_manual()

