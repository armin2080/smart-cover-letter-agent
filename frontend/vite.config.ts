import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { fileURLToPath } from "node:url"
import path from "node:path"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Vite config — https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: parseInt(process.env.PORT || "5173"),
    // Forward API + auth calls to the Django dev server. This keeps the
    // browser on a single origin, so no CORS configuration is needed locally.
    proxy: {
      "/api": {
        target: process.env.DJANGO_URL || "http://localhost:8000",
        changeOrigin: true,
      },
      "/media": {
        target: process.env.DJANGO_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})
