// Frontend test yapılandırması (audit B-3.2: sıfır test → Jest + jest-expo).
// Servis/mantık testleri (apiClient, config, wsClient) için jest-expo preset (RN transform)
// + AsyncStorage mock + '@/' path alias. Component render testleri (RNTL) ayrı bir aşama.
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testMatch: ["**/__tests__/**/*.test.ts", "**/__tests__/**/*.test.tsx"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@react-native-async-storage/.*|lucide-react-native))",
  ],
};
