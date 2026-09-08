import Gestion from "@/components/gestion";
import type { Seccion } from "@/lib/acceso";

export default async function Pagina({ params }: { params: Promise<{ ruta?: string[] }> }) {
  const { ruta } = await params;
  return <Gestion seccionSolicitada={(ruta?.[0] ?? "inicio") as Seccion} />;
}
