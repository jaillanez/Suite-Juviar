import type { Metadata, Viewport } from "next";
import Celular from "@/components/celular";

export const metadata: Metadata = { title: "Suite Juviar" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#174f3b" };

export default function Pagina() { return <Celular />; }
