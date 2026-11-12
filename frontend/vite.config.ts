import { defineConfig } from "vite";

const publicDemoPaths = new Set([
  "/api/v1/demo/correlation",
  "/api/v1/demo/investigation",
]);

export default defineConfig({
  plugins: [{
    name: "deny-non-demo-api",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url || "").split("?", 1)[0];
        if (path.startsWith("/api/") && !publicDemoPaths.has(path)) {
          res.statusCode = 404;
          res.setHeader("Cache-Control", "no-store");
          res.end("Not found");
          return;
        }
        if (publicDemoPaths.has(path)) {
          // Public synthetic demos need no caller identity or custom headers.
          // Keep only transport/content negotiation headers for the dev proxy.
          const allowedHeaders = new Set(["host", "accept", "user-agent"]);
          for (const header of Object.keys(req.headers)) {
            if (!allowedHeaders.has(header)) {
              delete req.headers[header];
            }
          }
        }
        next();
      });
    },
  }],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api/v1/demo/investigation": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
      "/api/v1/demo/correlation": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
