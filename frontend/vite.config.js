import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: { '/api': { target: process.env.CAMPUSBITE_API || 'http://127.0.0.1:8000' } },
  },
})
