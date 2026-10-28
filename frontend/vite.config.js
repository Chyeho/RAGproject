import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 13000,
    proxy: {
      '/api': 'http://localhost:18000'
    }
  }
})
