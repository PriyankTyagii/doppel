import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Doppel gets its own port: browser storage (including the Firebase sign-in) is per origin,
// so sharing a port with another local app would share its session.
const port = 5180;

export default defineConfig({
  plugins: [react()],
  server: { port, strictPort: true },
  preview: { port, strictPort: true },
});
