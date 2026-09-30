import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // Imagen de Docker mínima: solo el servidor y lo que usa.
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // En Docker, Nginx enruta /api al backend. En `npm run dev` fuera de Docker usamos este proxy
  // para mantener el mismo origen (la cookie de refresh es SameSite=Strict).
  async rewrites() {
    if (!isDev) return [];
    const api = process.env.API_URL ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
