import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Fixed file names (no hashes) so the VS Code extension can reference assets/index.js and
// assets/index.css from its Webview HTML. scripts/copy-output.mjs copies dist/ into
// core/src/thrubase/web/ and vscode/media/map-view/.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: (info) => {
          const name = info.names?.[0] ?? info.name ?? '';
          if (/\.(woff2?|ttf)$/.test(name)) return 'fonts/[name][extname]';
          return 'assets/[name][extname]';
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: false,
  },
});
