import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

export default defineConfig(({ command }) => ({
  // The production admin app is always mounted below /admin by the gateway.
  // Keep the build safe even when a Docker/build environment omits the variable.
  base: process.env.VITE_BASE_PATH || (command === 'build' ? '/admin/' : '/'),
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3100,
    proxy: {
      '/admin-api': {
        target: process.env.VITE_ADMIN_API_TARGET || 'http://127.0.0.1:8100',
        changeOrigin: true,
        rewrite: (sourcePath) => sourcePath.replace(/^\/admin-api/, ''),
      },
    },
  },
}));
