import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Redirige todas las rutas de /api/* al backend legacy, excepto los nuevos route handlers locales
        source: "/api/:path((?!intelligence|fishing-effort|bay-health|conditions|tides).*)",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
