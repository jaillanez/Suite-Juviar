import type { NextConfig } from "next";

const backend = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
const exportar = process.env.SJ_GESTION_EXPORT === "1";

const config: NextConfig = {
  ...(exportar ? { output: "export" as const, trailingSlash: true } : {}),
  ...(exportar ? {} : {
    async rewrites() {
      return [{ source: "/backend/:path*", destination: `${backend}/api/v1/:path*` }];
    },
  }),
};

export default config;
