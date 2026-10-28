import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// `npm run dev` talks to the API through the SSH tunnel (localhost:8120).
export default defineConfig({
  plugins: [svelte()],
  server: { proxy: { '/api': 'http://localhost:8120' } },
  build: { target: 'es2020', cssCodeSplit: true, assetsInlineLimit: 0 },
});
