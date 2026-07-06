import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { colors, spacing, typography, rf } from '@/theme/tokens';
import { Wifi, Copy } from 'lucide-react-native';
import { serviceConfig } from '@/services/config';
import { platformAlert } from '@/services/apiClient';

export default function RemoteConnectionPanel() {
  const [tunnelUrl, setTunnelUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const fetchSystemInfo = async () => {
    try {
      // serviceConfig.apiBaseUrl HER çağrıda taze okunur — updateServiceConfig objeyi
      // yeniden ATADIĞINDAN (config.ts), mount'ta yakalanan bir kopya yeniden-bağlanma
      // sonrası ESKİ adrese takılı kalırdı (panel sürekli eski sunucuyu yoklardı).
      const res = await fetch(`${serviceConfig.apiBaseUrl}/system/info`);
      const data = await res.json();
      // Backend artık camelCase 'tunnelUrl' döndürüyor (eski 'tunnel_url' bug'lıydı).
      const url = data.tunnelUrl || data.tunnel_url;
      if (url) {
        setTunnelUrl(url);
      }
    } catch (e) {
      console.warn("Could not fetch tunnel url:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSystemInfo();
    const interval = setInterval(fetchSystemInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const copyToClipboard = async () => {
    if (!tunnelUrl) return;
    // Eskiden navigator.clipboard + alert kullanıyordu → bunlar NATIVE'de (APK) sessizce
    // hiçbir şey yapmıyordu. Web'de panoya kopyala; native'de pano kütüphanesi olmadığından
    // URL'yi platformAlert ile göster (kullanıcı kopyalayabilsin).
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(tunnelUrl);
        platformAlert('Kopyalandı', 'Tünel bağlantısı panoya kopyalandı.');
      } catch {
        platformAlert('Tünel Bağlantısı', tunnelUrl);
      }
    } else {
      platformAlert('Tünel Bağlantısı', `Bu adresi kopyalayın:\n\n${tunnelUrl}`);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Wifi size={20} color={colors.primary} />
        <Text style={styles.title}>Uzaktan Erişim (Mobil Uygulama İçin)</Text>
      </View>

      <View style={styles.content}>
        <View style={styles.infoContainer}>
          <Text style={styles.description}>
            Mobil uygulamadan &quot;Sunucu IP&quot; bölümüne bu adresi girerek uzaktan bağlanabilirsiniz.
          </Text>
          
          {loading ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: 10 }} />
          ) : tunnelUrl ? (
            <TouchableOpacity style={styles.urlBox} onPress={copyToClipboard}>
              <Text style={styles.urlText} numberOfLines={1} ellipsizeMode="middle">
                {tunnelUrl}
              </Text>
              <Copy size={16} color={colors.text} />
            </TouchableOpacity>
          ) : (
            <Text style={styles.waitingText}>Tünel URL&apos;si bekleniyor...</Text>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.panel,
    borderRadius: 12,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
    gap: 8,
  },
  title: {
    fontSize: typography.subtitle,
    fontWeight: 'bold',
    color: colors.text,
  },
  content: {
    flexDirection: 'column',
  },
  infoContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  description: {
    color: colors.textMuted,
    fontSize: typography.small,
    marginBottom: spacing.sm,
    lineHeight: rf(18),
  },
  urlBox: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.05)',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  urlText: {
    color: colors.text,
    fontSize: typography.small,
    fontFamily: 'monospace',
    flex: 1,
    marginRight: 8,
  },
  waitingText: {
    color: colors.warning,
    fontSize: typography.small,
    fontStyle: 'italic',
  }
});
