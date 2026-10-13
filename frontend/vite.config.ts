import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwindcss()],server:{strictPort:true,proxy:{'/api':process.env.BACKEND_PROXY_URL || 'http://127.0.0.1:8000'}}});
