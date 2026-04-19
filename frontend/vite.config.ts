import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Output straight into itatorrents/web/dist so FastAPI serves it.
// Use relative base so the SPA works under any ITA_ROOT_PATH (e.g. /itatorrents).
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: path.resolve(__dirname, '../itatorrents/web/dist'),
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/assets': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
});
