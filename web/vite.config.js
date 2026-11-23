import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs separately (`make serve PORT=xxxx`); proxy /funds to it.
const apiPort = process.env.API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/funds": `http://localhost:${apiPort}` },
  },
});
