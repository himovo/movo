import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

const productExtensionPath = process.env.MOVO_ADMIN_PRODUCT_UI_EXTENSION
  ? path.resolve(process.env.MOVO_ADMIN_PRODUCT_UI_EXTENSION)
  : path.resolve(__dirname, './src/product/community.ts');

export default defineConfig(({ command }) => ({
  // The production admin app is always mounted below /admin by the gateway.
  // Keep the build safe even when a Docker/build environment omits the variable.
  base: process.env.VITE_BASE_PATH || (command === 'build' ? '/admin/' : '/'),
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@movo-admin-product-extension': productExtensionPath,
      '@movo-admin-web': path.resolve(__dirname, './src'),
      'vue': path.resolve(__dirname, './node_modules/vue'),
      'naive-ui': path.resolve(__dirname, './node_modules/naive-ui'),
      'axios': path.resolve(__dirname, './node_modules/axios'),
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
