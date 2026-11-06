import type { CapacitorConfig } from "@capacitor/cli";

/**
 * App de tablet para Android: abre las pantallas del servidor, no tiene copia propia.
 * Cada vez que se actualiza el servidor, la tablet ya ve lo nuevo sin reinstalar.
 *
 *   Gestión            — firmas presenciales (capacitaciones, EPP) y lectura de equipos con la cámara.
 *   Guardia del portón — consola de la fila de camiones de cada bodega.
 */
const config: CapacitorConfig = {
  appId: "ar.com.juviar.tablet",
  appName: "Suite Juviar",
  webDir: "www",
  server: {
    androidScheme: "https",
    allowNavigation: ["juviar-gestion.duckdns.org", "juviar-bot.duckdns.org"],
  },
  android: { allowMixedContent: false },
};

export default config;
