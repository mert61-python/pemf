# PEMF Vet System - Android Mobile App

Native Android uygulaması, PEMF GUI sistemine WebSocket/HTTP API'leri üzerinden bağlanır. Gerçek zamanlı izleme, seans kontrolü ve ESP cihaz yönetimi sağlar.

## Özellikler

- **Ana Ekran**: Bağlantı durumu ve hızlı durum özeti
- **Seans Kontrol**: Bağlı ESP cihazları, PWM durumu, sıcaklık okumaları ve aktif seans detayları
- **İzleme**: Gerçek zamanlı sensör verileri ve grafikler
- **Ayarlar**: Manuel IP girişi, otomatik keşif, bağlantı ayarları

## Teknoloji Stack

- **Dil**: Kotlin
- **Minimum SDK**: Android 10 (API 29)
- **Mimari**: MVVM + Repository Pattern
- **Dependency Injection**: Hilt
- **Networking**: Retrofit, OkHttp, Java-WebSocket
- **Reactive Programming**: Kotlin Coroutines + Flow
- **Charts**: MPAndroidChart
- **UI**: Material Design 3

## Kurulum

1. Android Studio'da projeyi açın
2. Gradle sync yapın
3. Uygulamayı çalıştırın

## Yapılandırma

Uygulama varsayılan olarak otomatik keşif modunda çalışır. Manuel IP girişi için Ayarlar sekmesini kullanın.

## Lisans

Bu proje PEMF Vet System'in bir parçasıdır.

