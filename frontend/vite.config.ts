import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { copyFileSync, mkdirSync } from 'fs'

// icon.pngをdist/にコピーするカスタムプラグイン
// publicDir: false のためビルド時にこのプラグインで対応
const copyIconPlugin = () => ({
  name: 'copy-icon',
  closeBundle() {
    try {
      mkdirSync('dist', { recursive: true })
      copyFileSync('public/icon.png', 'dist/icon.png')
      console.log('[copy-icon] icon.png → dist/icon.png')
    } catch (e) {
      console.warn('[copy-icon] failed:', e)
    }
  }
})

export default defineConfig(({ command }) => ({
  plugins: [
    react(),
    tailwindcss(),
    copyIconPlugin(),
  ],
  // build時のみpublicDir無効（icon.pngがdistに入りHTTPサーバー誤動作を防ぐため）
  // dev時は有効にしてicon.pngを /icon.png でアクセス可能にする
  publicDir: command === 'build' ? false : 'public',
}))
