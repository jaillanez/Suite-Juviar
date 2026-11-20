import type { Metadata, Viewport } from "next";
import Celular from "@/components/celular";

export const metadata: Metadata = { title: "Suite Juviar · Factura" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#174f3b" };

// Administración: foto de la factura del proveedor y controles de ARCA desde el celular.
export default function Pagina() { return <Celular tareaInicial="factura" />; }
