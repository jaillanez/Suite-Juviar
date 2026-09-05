import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Una sola app instalada, tres perfiles adentro. El perfil se resuelve por el
 * legajo de Nexus al iniciar sesión, no lo elige el usuario: un capataz no ve
 * la pantalla de báscula ni la de depósito.
 *
 *   campo    — capataz: fichaje y tareaje en el cuartel, sin señal.
 *   deposito — entrega de EPP con firma en tablet.
 *   bascula  — apertura y cierre de romaneos en la playa de descarga.
 *
 * Los tres funcionan offline y sincronizan al recuperar red (regla 7 de
 * construcción). En depósito, báscula y viña la red se cae; el módulo espera y
 * reintenta, o avisa, pero nunca pierde el registro en silencio.
 */
const config: CapacitorConfig = {
  appId: "ar.com.juviar.suite",
  appName: "Suite Juviar",
  webDir: "out",
  android: { allowMixedContent: false },
  plugins: {
    CapacitorHttp: { enabled: true },
  },
};

export default config;
