"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Empresa, nombres, puedeEntrar, Perfil, perfiles, Seccion } from "@/lib/acceso";
import { api, ErrorApi } from "@/lib/api";
import { ErrorVisible, Simulado } from "./compartidos";
import { EppGestion } from "./epp-gestion";
import { SeleccionGestion } from "./seleccion-gestion";
import { CapacitacionesGestion } from "./capacitaciones-gestion";
import { AnaliticaGestion } from "./analitica-gestion";
import { LegajoGestion } from "./legajo-gestion";
import { SaludGestion } from "./salud-gestion";
import { TurnosGestion } from "./turnos-gestion";

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0";
const COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT ?? "local";
function Icono({ nombre }: { nombre: Seccion }) {
  const rutas: Record<Seccion, string> = {
    inicio: "M4 5h16v14H4z M8 9h3v3H8z M14 9h2 M14 13h2 M8 16h8",
    epp: "M7 20v-5a5 5 0 0110 0v5 M9 9V6a3 3 0 016 0v3 M6 10h12v4H6z",
    analitica: "M5 19V9 M12 19V5 M19 19v-7 M3 19h18",
    seleccion: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2 M9 11a4 4 0 100-8 4 4 0 000 8z M19 8v6 M22 11h-6",
    capacitaciones: "M3 5l9-3 9 3-9 3z M7 7v6c3 2 7 2 10 0V7 M21 5v8",
    legajo: "M6 3h9l3 3v15H6z M9 10h6 M9 14h6 M9 18h4",
    salud: "M12 21s-8-4.5-8-11a4 4 0 017-2.6L12 9l1-1.6A4 4 0 0120 10c0 6.5-8 11-8 11z M9 13h6 M12 10v6",
    turnos: "M12 22a10 10 0 110-20 10 10 0 010 20z M12 6v6l4 2",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={rutas[nombre]} /></svg>;
}

function Ingreso({ entrar }: { entrar: (empresa: Empresa, perfil: Perfil) => void }) {
  const [empresa, setEmpresa] = useState<Empresa>("ENAV");
  const [perfil, setPerfil] = useState<Perfil>("RRHH");
  return <main className="ingreso"><section className="ingreso-marca"><span className="isotipo">SJ</span><p>Suite Juviar</p><h1>Gestión interna, en un solo lugar.</h1><p className="bajada">Operaciones de personas, seguridad y producción con trazabilidad.</p></section>
    <form className="tarjeta ingreso-form" onSubmit={(e) => { e.preventDefault(); entrar(empresa, perfil); }}><Simulado /><p className="eyebrow">ACCESO DE PRUEBA</p><h2>Ingresar a Gestión</h2><label>Empresa<select value={empresa} onChange={(e) => setEmpresa(e.target.value as Empresa)}><option>ENAV</option><option>JUBIAR</option></select></label><label>Perfil<select value={perfil} onChange={(e) => setPerfil(e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select></label><p className="ayuda">La identidad aún es simulada. La API continúa siendo responsable de autorizar cada operación.</p><button className="primario">Continuar</button></form></main>;
}

function Encabezado({ titulo, descripcion }: { titulo: string; descripcion: string }) {
  return <header className="encabezado"><div><p className="eyebrow">GESTIÓN INTERNA</p><h1>{titulo}</h1><p>{descripcion}</p></div><Simulado nivel="campo" /></header>;
}

function Inicio({ empresa }: { empresa: Empresa }) {
  return <><Encabezado titulo={`Buen día, ${empresa}`} descripcion="Estado general de las operaciones habilitadas para tu perfil." /><div className="metricas"><article><span>Fuente activa</span><strong>Simulada</strong><small>Bloqueada para producción</small></article><article><span>Empresa</span><strong>{empresa}</strong><small>Contexto aplicado a toda la sesión</small></article><article><span>Integridad</span><strong>API</strong><small>La interfaz no contiene reglas de negocio</small></article></div><section className="tarjeta"><h2>Antes de operar</h2><p>Las franjas rojas señalan datos de muestra. Los cambios sensibles requieren confirmación y las operaciones rechazadas muestran un mensaje legible.</p></section></>;
}

function Epp() {
  return <><Encabezado titulo="Elementos de protección personal" descripcion="Catálogo, matriz, stock, avisos y constancias de entrega." /><EppGestion /></>;
}

function Analitica() {
  return <><Encabezado titulo="Analítica EPP" descripcion="Consumo, duración concluyente y reclamos en proporción, con el tamaño de muestra visible." /><AnaliticaGestion /></>;
}

function Legajo() {
  return <><Encabezado titulo="Legajos" descripcion="Búsqueda, ficha de Nexus en sólo lectura y documentación cifrada." /><LegajoGestion /></>;
}

function Salud() {
  return <><Encabezado titulo="Salud laboral" descripcion="Área separada, auditada y exclusiva del Servicio Médico." /><SaludGestion /></>;
}

function Turnos() {
  return <><Encabezado titulo="Turnos y conciliación" descripcion="Cronogramas versionados, desvíos y propuestas que nunca se imputan solas." /><TurnosGestion /></>;
}

function Seleccion() {
  return <><Encabezado titulo="Selección" descripcion="Búsquedas explicables, ranking revisable y originales siempre conservados." /><SeleccionGestion /></>;
}

function Capacitaciones() {
  return <><Encabezado titulo="Capacitaciones" descripcion="Temas, dictados, convocatorias, asistencia firmada y seguimiento anual." /><CapacitacionesGestion /></>;
}

function Pendiente({ seccion }: { seccion: Seccion }) { return <><Encabezado titulo={nombres[seccion]} descripcion="Módulo incorporado al armazón de Gestión." /><section className="tarjeta"><h2>Integración en curso</h2><p>El dominio existe, pero su API de gestión todavía debe completarse antes de habilitar esta operación. No se simulan reglas en el navegador.</p></section></>; }

function Contenido({ seccion, empresa }: { seccion: Seccion; empresa: Empresa }) {
  if (seccion === "inicio") return <Inicio empresa={empresa} />; if (seccion === "epp") return <Epp />; if (seccion === "analitica") return <Analitica />; if (seccion === "seleccion") return <Seleccion />; if (seccion === "capacitaciones") return <Capacitaciones />; if (seccion === "legajo") return <Legajo />; if (seccion === "salud") return <Salud />; if (seccion === "turnos") return <Turnos />; return <Pendiente seccion={seccion} />;
}

function AccesoDenegado({ perfil, seccion }: { perfil: Perfil; seccion: Seccion }) {
  const [resultadoApi, setResultadoApi] = useState("Verificando autorización con la API…");
  useEffect(() => {
    const sondas: Partial<Record<Seccion, string>> = { salud: "salud/catalogo", capacitaciones: "capacitaciones/temas", analitica: `epp-analitica/tablero?desde=${new Date().getFullYear()}-01-01&hasta=${new Date().toISOString().slice(0, 10)}` };
    const ruta = sondas[seccion];
    if (!ruta) { setResultadoApi("La sección no está habilitada para esta sesión."); return; }
    api(ruta).then(() => setResultadoApi("Advertencia: la API permitió un acceso que la interfaz oculta."))
      .catch((error) => setResultadoApi(error instanceof ErrorApi && error.estado === 403
        ? "API respondió 403: permiso insuficiente."
        : `La API no pudo verificar el permiso: ${error instanceof Error ? error.message : "error desconocido"}`));
  }, [seccion]);
  return <><Encabezado titulo="Acceso denegado" descripcion="Tu perfil no tiene permiso para ingresar a esta sección." /><ErrorVisible mensaje={`El perfil ${perfiles[perfil].nombre} no puede acceder a ${nombres[seccion]}. ${resultadoApi}`} /></>;
}

export default function Gestion({ seccionSolicitada }: { seccionSolicitada: Seccion }) {
  const [sesion, setSesion] = useState<{ empresa: Empresa; perfil: Perfil } | null>(null);
  useEffect(() => { const guardada = sessionStorage.getItem("gestion-sesion"); if (guardada) setSesion(JSON.parse(guardada)); }, []);
  function entrar(empresa: Empresa, perfil: Perfil) { const nueva = { empresa, perfil }; sessionStorage.setItem("gestion-sesion", JSON.stringify(nueva)); setSesion(nueva); }
  if (!sesion) return <Ingreso entrar={entrar} />;
  const valida = Object.hasOwn(nombres, seccionSolicitada) ? seccionSolicitada : "inicio";
  const permitido = puedeEntrar(sesion.perfil, valida);
  return <div className="aplicacion"><aside><div className="marca"><span className="isotipo">SJ</span><div><strong>Suite Juviar</strong><small>Gestión interna</small></div></div><nav aria-label="Secciones">{perfiles[sesion.perfil].secciones.map((s) => <Link key={s} href={s === "inicio" ? "/" : `/${s}`} className={s === valida ? "activo" : ""}><Icono nombre={s} />{nombres[s]}</Link>)}</nav><div className="modo-prueba"><strong>Modo prueba</strong><label>Perfil<select value={sesion.perfil} onChange={(e) => entrar(sesion.empresa, e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select></label></div></aside><div className="principal-contenedor"><div className="franja">DATOS SIMULADOS · SIN VALIDEZ PRODUCTIVA</div><header className="barra"><div><span className="pulso" /> API interna</div><label>Empresa<select value={sesion.empresa} onChange={(e) => entrar(e.target.value as Empresa, sesion.perfil)}><option>ENAV</option><option>JUBIAR</option></select></label><button className="salir" onClick={() => { sessionStorage.removeItem("gestion-sesion"); setSesion(null); }}>Salir</button></header><main>{permitido ? <Contenido key={sesion.perfil} seccion={valida} empresa={sesion.empresa} /> : <AccesoDenegado perfil={sesion.perfil} seccion={valida} />}</main><footer>Suite Juviar Gestión v{VERSION} · commit {COMMIT}</footer></div></div>;
}
