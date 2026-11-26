import type { Metadata, Viewport } from "next";
import SubirFactura from "@/components/subir-factura";

export const metadata: Metadata = { title: "Suite Juviar · Subir facturas", referrer: "no-referrer", robots: { index: false, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#174f3b" };

// Link personal + PIN: sólo foto de la factura y sus controles de ARCA, nada más de Gestión.
export default function Pagina() { return <SubirFactura />; }
