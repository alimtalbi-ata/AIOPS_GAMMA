import { defineConfig } from "vite";

export default defineConfig({
  plugins: [{
    name: "deny-all-api",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url || "").split("?", 1)[0];
        if (path === "/api" || path.startsWith("/api/")) {
          res.statusCode = 404;
          res.setHeader("Cache-Control", "no-store");
          res.end("Not found");
          return;
        }
        next();
      });
    },
  }],
  server: { host: "127.0.0.1" },
});
