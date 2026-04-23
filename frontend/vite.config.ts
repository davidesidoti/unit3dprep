import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Output straight into unit3dprep/web/dist so FastAPI serves it.
// Use relative base so the SPA works under any U3DP_ROOT_PATH (e.g. /unit3dprep).
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: path.resolve(__dirname, '../unit3dprep/web/dist'),
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
