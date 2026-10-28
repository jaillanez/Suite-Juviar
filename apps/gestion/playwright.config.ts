import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  use: { baseURL: "http://127.0.0.1:3003", trace: "retain-on-failure" },
  webServer: [
    {
      command: "SJ_ENTORNO=prueba SJ_HMAC_DATOS_PERSONALES=00000000000000000000000000000000 SJ_CLAVE_CIFRADO_DATOS_PERSONALES=00000000000000000000000000000000 ../../.venv/bin/uvicorn suite_juviar.main:app --host 127.0.0.1 --port 8012",
      cwd: "../api", url: "http://127.0.0.1:8012/docs", reuseExistingServer: false,
    },
    { command: "API_INTERNAL_URL=http://127.0.0.1:8012 pnpm exec next dev --hostname 127.0.0.1 --port 3003", url: "http://127.0.0.1:3003", reuseExistingServer: false },
  ],
});
