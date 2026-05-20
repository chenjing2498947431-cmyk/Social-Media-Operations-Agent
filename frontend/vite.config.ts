import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发期通过 proxy 把 /api 转发到 backend_api(8000)，规避浏览器跨域。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
