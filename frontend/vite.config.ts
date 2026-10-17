import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Fitness Hub",
        short_name: "Fitness",
        lang: "cs",
        start_url: "/",
        display: "standalone",
        background_color: "#09090b",
        theme_color: "#09090b",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Phones reach the dev server through `tailscale serve` (*.ts.net)
    allowedHosts: [".ts.net"],
    proxy: { "/api": { target: process.env.API_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: true } },
  },
});
