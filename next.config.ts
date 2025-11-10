import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  
  async rewrites() {
    const isDevelopment = process.env.NODE_ENV === "development";
    
    if (isDevelopment) {
      // Development: proxy to local FastAPI
      return [
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:8000/backend/:path*",
        },
        {
          source: "/docs",
          destination: "http://127.0.0.1:8000/backend/docs",
        },
      ];
    }
    
    // Production: proxy to production FastAPI
    return [
      {
        source: "/api/:path*",
        destination: "https://insightingtool.maricoapps.biz/backend/:path*",
      },
      {
        source: "/docs",
        destination: "https://insightingtool.maricoapps.biz/backend/docs",
      },
    ];
  },
};

export default nextConfig;