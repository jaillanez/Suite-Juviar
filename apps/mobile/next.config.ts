import type { NextConfig } from "next";

const backend = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

export default config;
