import type { CapacitorConfig } from "@capacitor/cli";

/**
 * App del celular para Android: abre las pantallas del servidor, no tiene copia propia.
 * Cada vez que se actualiza el servidor, el celular ya ve lo nuevo sin reinstalar.
 *
 *   Gestión            — pantallas simples (/celular): QR de equipos, entrega de EPP y firma de
 *                        asistencia a capacitaciones, según el perfil de quien entra.
 *   Guardia del portón — consola de la fila de camiones de cada bodega.
 */
const config: CapacitorConfig = {
  appId: "ar.com.juviar.celular",
  appName: "Suite Juviar",
  webDir: "www",
  server: {
    androidScheme: "https",
    allowNavigation: ["juviar-gestion.duckdns.org", "juviar-bot.duckdns.org"],
  },
  android: { allowMixedContent: false },
};

export default config;
