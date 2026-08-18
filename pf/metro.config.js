const { getDefaultConfig } = require('expo/metro-config');

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

// Web platformu (expo-sqlite vb. kutuphaneler) icin .wasm dosyalarinin islenmesine izin ver
config.resolver.assetExts.push('wasm');

module.exports = config;
