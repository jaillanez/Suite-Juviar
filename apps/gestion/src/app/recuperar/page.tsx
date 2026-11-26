import type { Metadata, Viewport } from "next";
import { RecuperarClave } from "@/components/recuperar-clave";

export const metadata: Metadata = { title: "Suite Juviar · Recuperar contraseña", robots: { index: false, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#174f3b" };

export default function Pagina() { return <RecuperarClave />; }
