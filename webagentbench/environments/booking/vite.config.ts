import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/env/booking/",
  optimizeDeps: {
    exclude: ["@webagentbench/shared", "@webagentbench/booking"],
  },
  build: {
    outDir: "../../static/envs/booking",
    emptyOutDir: true,
  },
  server: {
    port: 4178,
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/manifest": "http://127.0.0.1:8080",
      "/static": "http://127.0.0.1:8080",
      "/launch": "http://127.0.0.1:8080",
    },
  },
});
