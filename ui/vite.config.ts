import path from "path"
import { defineConfig } from "vite"
import react from '@vitejs/plugin-react-swc'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    open: true,
    proxy: {
        "/py": {
            target: "http://localhost:3005",
            changeOrigin: true,
            secure: false,
            rewrite: (path) => path.replace(/^\/py/, ""),
        },
    }
  }
})
