import type { Metadata, Viewport } from "next";
import { RestablecerClave } from "@/components/recuperar-clave";

// referrer: no-referrer para que el código del enlace no salga hacia otros sitios.
export const metadata: Metadata = { title: "Suite Juviar · Contraseña nueva", referrer: "no-referrer", robots: { index: false, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#174f3b" };

export default function Pagina() { return <RestablecerClave />; }
