"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Empresa, gruposMenu, nombres, puedeEntrar, Perfil, perfiles, Seccion } from "@/lib/acceso";
import { api, ErrorApi } from "@/lib/api";
import { UsuariosGestion } from "./usuarios-gestion";
import { ErrorVisible } from "./compartidos";
import { EppGestion } from "./epp-gestion";
import { SeleccionGestion } from "./seleccion-gestion";
import { CapacitacionesGestion } from "./capacitaciones-gestion";
import { AnaliticaGestion } from "./analitica-gestion";
import { LegajoGestion } from "./legajo-gestion";
import { SaludGestion } from "./salud-gestion";
import { TurnosGestion } from "./turnos-gestion";
import { ContactosGestion } from "./contactos-gestion";
import { ProduccionGestion } from "./produccion-gestion";

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0";
const COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT ?? "local";
function Icono({ nombre }: { nombre: Seccion }) {
  const rutas: Record<Seccion, string> = {
    inicio: "M4 5h16v14H4z M8 9h3v3H8z M14 9h2 M14 13h2 M8 16h8",
    produccion: "M3 20h18 M5 20V9l5 3V9l5 3V5h4v15 M8 16h2 M14 16h2",
    fila: "M3 16h13V7H3z M16 10h3l2 3v3h-5z M6 19a2 2 0 100-4 2 2 0 000 4z M18 19a2 2 0 100-4 2 2 0 000 4z",
    bot: "M5 7h14v10H5z M9 11h.01 M15 11h.01 M9 15h6 M12 7V4 M10 4h4",
    epp: "M7 20v-5a5 5 0 0110 0v5 M9 9V6a3 3 0 016 0v3 M6 10h12v4H6z",
    analitica: "M5 19V9 M12 19V5 M19 19v-7 M3 19h18",
    seleccion: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2 M9 11a4 4 0 100-8 4 4 0 000 8z M19 8v6 M22 11h-6",
    capacitaciones: "M3 5l9-3 9 3-9 3z M7 7v6c3 2 7 2 10 0V7 M21 5v8",
    legajo: "M6 3h9l3 3v15H6z M9 10h6 M9 14h6 M9 18h4",
    salud: "M12 21s-8-4.5-8-11a4 4 0 017-2.6L12 9l1-1.6A4 4 0 0120 10c0 6.5-8 11-8 11z M9 13h6 M12 10v6",
    turnos: "M12 22a10 10 0 110-20 10 10 0 010 20z M12 6v6l4 2",
    contactos: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2 M9 11a4 4 0 100-8 4 4 0 000 8z M19 8v6 M22 11h-6",
    usuarios: "M12 12a4 4 0 100-8 4 4 0 000 8z M4 21v-1a6 6 0 0112 0v1 M17 11l2 2 4-4",
    configuracion: "M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7z M19.4 15a1.7 1.7 0 00.34 1.88l.06.06-2 3.46-.08-.02a1.7 1.7 0 00-1.8.27l-.4.23a1.7 1.7 0 00-.86 1.68V22h-4v-.1a1.7 1.7 0 00-.86-1.68l-.4-.23a1.7 1.7 0 00-1.8-.27l-.08.02-2-3.46.06-.06A1.7 1.7 0 004.6 15v-.46a1.7 1.7 0 00-1.2-1.61l-.08-.03v-4l.08-.03a1.7 1.7 0 001.2-1.61V6.8l2-3.46.08.02a1.7 1.7 0 001.8-.27l.4-.23A1.7 1.7 0 009.74 1.2V1h4v.1a1.7 1.7 0 00.86 1.68l.4.23a1.7 1.7 0 001.8.27l.08-.02 2 3.46-.06.06a1.7 1.7 0 00-.34 1.88v.46a1.7 1.7 0 001.2 1.61l.08.03v4l-.08.03A1.7 1.7 0 0019.4 15z",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={rutas[nombre]} /></svg>;
}

function Ingreso({ entrar }: { entrar: (empresa: Empresa, perfil: Perfil) => void }) {
  const [empresa, setEmpresa] = useState<Empresa>("ENAV");
  const [perfil, setPerfil] = useState<Perfil>("SUPERADMIN");
  return <main className="ingreso"><section className="ingreso-marca"><span className="isotipo">SJ</span><p>Suite Juviar</p><h1>Gestión interna, en un solo lugar.</h1><p className="bajada">Operaciones de personas, seguridad y producción con trazabilidad.</p></section>
    <form className="tarjeta ingreso-form" onSubmit={(e) => { e.preventDefault(); entrar(empresa, perfil); }}><h2>Ingresar a Gestión</h2><label>Empresa<select value={empresa} onChange={(e) => setEmpresa(e.target.value as Empresa)}><option>ENAV</option><option>JUBIAR</option></select></label><label>Perfil<select value={perfil} onChange={(e) => setPerfil(e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select></label><button className="primario">Continuar</button></form></main>;
}

type SesionGestion = { empresa: Empresa; perfil: Perfil; real?: boolean; nombre?: string; email?: string };
type Yo = { nombre: string; email: string; perfil: Perfil; empresa_sesion: Empresa; debe_cambiar_clave: boolean };

function sesionDesde(yo: Yo): SesionGestion {
  return { empresa: yo.empresa_sesion, perfil: yo.perfil, real: true, nombre: yo.nombre, email: yo.email };
}

function IngresoReal({ entrar }: { entrar: (yo: Yo) => void }) {
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [verClave, setVerClave] = useState(false);
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setEnviando(true);
    const f = new FormData(e.currentTarget);
    try { entrar(await api<Yo>("ingreso", { method: "POST", body: JSON.stringify({ email: f.get("email"), clave: f.get("clave") }) })); }
    catch (x) { setError(x instanceof Error ? x.message : "No pudimos ingresar."); }
    finally { setEnviando(false); }
  }
  return <main className="ingreso"><section className="ingreso-marca"><span className="isotipo">SJ</span><p>Suite Juviar</p><h1>Gestión interna, en un solo lugar.</h1><p className="bajada">Operaciones de personas, seguridad y producción con trazabilidad.</p></section>
    <form className="tarjeta ingreso-form" onSubmit={enviar}><h2>Ingresar a Gestión</h2>{error && <ErrorVisible mensaje={error} />}<label>Correo<input name="email" type="email" required autoComplete="username" autoFocus /></label><label>Contraseña<span className="con-ojo"><input name="clave" type={verClave ? "text" : "password"} required autoComplete="current-password" /><button type="button" className="ojo" aria-label={verClave ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={verClave} onClick={() => setVerClave(!verClave)}><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button></span></label><button className="primario" disabled={enviando}>{enviando ? "Ingresando…" : "Ingresar"}</button><p className="ayuda">¿No tenés usuario o te olvidaste la contraseña? Pedíselo al administrador del sistema.</p></form></main>;
}

function FormularioClave({ listo, titulo }: { listo: (yo: Yo) => void; titulo: string }) {
  const [error, setError] = useState("");
  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError("");
    const form = e.currentTarget; const f = new FormData(form);
    if (f.get("nueva") !== f.get("repetir")) { setError("Las contraseñas nuevas no coinciden."); return; }
    try { const yo = await api<Yo>("ingreso/clave", { method: "POST", body: JSON.stringify({ actual: f.get("actual"), nueva: f.get("nueva") }) }); form.reset(); listo(yo); }
    catch (x) { setError(x instanceof Error ? x.message : "No pudimos cambiar la contraseña."); }
  }
  return <form className="tarjeta ingreso-form" onSubmit={enviar}><h2>{titulo}</h2>{error && <ErrorVisible mensaje={error} />}<label>Contraseña actual<input name="actual" type="password" required autoComplete="current-password" /></label><label>Contraseña nueva<input name="nueva" type="password" required minLength={10} autoComplete="new-password" placeholder="Al menos 10 caracteres" /></label><label>Repetí la contraseña nueva<input name="repetir" type="password" required minLength={10} autoComplete="new-password" /></label><button className="primario">Guardar contraseña</button></form>;
}

function PrimerIngreso({ listo }: { listo: (yo: Yo) => void }) {
  return <main className="ingreso"><section className="ingreso-marca"><span className="isotipo">SJ</span><p>Suite Juviar</p><h1>Elegí tu contraseña.</h1><p className="bajada">Es tu primer ingreso: reemplazá la contraseña que te dieron por una que sólo sepas vos.</p></section><FormularioClave titulo="Contraseña nueva" listo={listo} /></main>;
}

function Encabezado({ titulo, descripcion }: { titulo: string; descripcion: string }) {
  return <header className="encabezado"><div><h1>{titulo}</h1><p>{descripcion}</p></div></header>;
}

function Inicio({ empresa, nombre }: { empresa: Empresa; nombre?: string }) {
  return <><Encabezado titulo={`Buen día, ${nombre ? nombre.split(" ")[0] : empresa}`} descripcion="Estado general de las operaciones habilitadas para tu perfil." /><div className="metricas"><article><span>Empresa</span><strong>{empresa}</strong><small>Contexto aplicado a toda la sesión</small></article><article><span>Conexión</span><strong>Activa</strong><small>API interna disponible</small></article><article><span>Perfil</span><strong>Habilitado</strong><small>Permisos aplicados a la sesión</small></article></div></>;
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

function Contactos() {
  return <><Encabezado titulo="Contactos de productores" descripcion="Permisos, reemplazos e historial con trazabilidad completa." /><ContactosGestion /></>;
}

function Produccion({ area }: { area: "recepcion" | "fila" | "bot" }) {
  const textos = {
    recepcion: ["Recepción", "Ingreso de camiones y apertura de romaneos."],
    fila: ["Fila de camiones", "Llamados, confirmaciones y pantalla de espera del portón."],
    bot: ["Consultas de productores", "Estadísticas, reportes y simulador del bot."],
  } as const;
  return <><Encabezado titulo={textos[area][0]} descripcion={textos[area][1]} /><ProduccionGestion area={area} /></>;
}

function Configuracion({ sesion, guardar }: { sesion: { empresa: Empresa; perfil: Perfil }; guardar: (empresa: Empresa, perfil: Perfil) => void }) {
  const [empresa, setEmpresa] = useState(sesion.empresa);
  const [perfil, setPerfil] = useState(sesion.perfil);
  return <><Encabezado titulo="Configuración" descripcion="Elegí la empresa y el perfil con los que querés recorrer la aplicación." /><section className="tarjeta configuracion"><label>Empresa<select value={empresa} onChange={(e) => setEmpresa(e.target.value as Empresa)}><option>ENAV</option><option>JUBIAR</option></select></label><label>Perfil<select value={perfil} onChange={(e) => setPerfil(e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select></label><button className="primario" onClick={() => guardar(empresa, perfil)}>Aplicar cambios</button></section></>;
}

function ConfiguracionReal({ sesion, actualizar }: { sesion: SesionGestion; actualizar: (yo: Yo) => void }) {
  const [empresa, setEmpresa] = useState(sesion.empresa);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  async function aplicar() {
    setError(""); setAviso("");
    try { actualizar(await api<Yo>("ingreso/empresa", { method: "PUT", body: JSON.stringify({ empresa }) })); setAviso("Empresa cambiada."); }
    catch (x) { setError(x instanceof Error ? x.message : "No pudimos cambiar la empresa."); }
  }
  return <><Encabezado titulo="Mi cuenta" descripcion="Tus datos de acceso y la empresa con la que estás trabajando." />{error && <ErrorVisible mensaje={error} />}{aviso && <div className="aviso-exito" role="status">{aviso}</div>}
    <section className="tarjeta"><h2>{sesion.nombre}</h2><p>{sesion.email} · {perfiles[sesion.perfil].nombre}</p><p className="ayuda">El perfil lo asigna el administrador del sistema.</p></section>
    <section className="tarjeta configuracion"><label>Empresa<select value={empresa} onChange={(e) => setEmpresa(e.target.value as Empresa)}><option>ENAV</option><option>JUBIAR</option></select></label><button className="primario" onClick={aplicar}>Aplicar cambios</button></section>
    <FormularioClave titulo="Cambiar contraseña" listo={(yo) => { actualizar(yo); setAviso("Contraseña cambiada."); }} /></>;
}

function Usuarios() {
  return <><Encabezado titulo="Usuarios" descripcion="Quién puede entrar a Gestión, con qué perfil, y el registro de accesos." /><UsuariosGestion /></>;
}

function Pendiente({ seccion }: { seccion: Seccion }) { return <><Encabezado titulo={nombres[seccion]} descripcion="Módulo incorporado al armazón de Gestión." /><section className="tarjeta"><h2>Integración en curso</h2><p>El dominio existe, pero su API de gestión todavía debe completarse antes de habilitar esta operación. No se simulan reglas en el navegador.</p></section></>; }

function Contenido({ seccion, sesion, guardar, actualizar }: { seccion: Seccion; sesion: SesionGestion; guardar: (empresa: Empresa, perfil: Perfil) => void; actualizar: (yo: Yo) => void }) {
  if (seccion === "usuarios") return <Usuarios />;
  if (seccion === "configuracion" && sesion.real) return <ConfiguracionReal sesion={sesion} actualizar={actualizar} />;
  if (seccion === "inicio") return <Inicio empresa={sesion.empresa} nombre={sesion.nombre} />; if (seccion === "produccion") return <Produccion area="recepcion" />; if (seccion === "fila") return <Produccion area="fila" />; if (seccion === "bot") return <Produccion area="bot" />; if (seccion === "epp") return <Epp />; if (seccion === "analitica") return <Analitica />; if (seccion === "seleccion") return <Seleccion />; if (seccion === "capacitaciones") return <Capacitaciones />; if (seccion === "legajo") return <Legajo />; if (seccion === "salud") return <Salud />; if (seccion === "turnos") return <Turnos />; if (seccion === "contactos") return <Contactos />; if (seccion === "configuracion") return <Configuracion sesion={sesion} guardar={guardar} />; return <Pendiente seccion={seccion} />;
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

function GrupoMenu({ nombre, secciones, activa }: { nombre: string; secciones: Seccion[]; activa: Seccion }) {
  const [abierto, setAbierto] = useState(secciones.includes(activa));
  return <details className="menu-grupo" open={abierto} onToggle={(evento) => setAbierto(evento.currentTarget.open)}>
    <summary><span>{nombre}</span><i aria-hidden="true" /></summary>
    <div className="menu-grupo-enlaces">{secciones.map((seccion) => <Link key={seccion} href={seccion === "inicio" ? "/" : `/${seccion}`} className={seccion === activa ? "activo" : ""}><Icono nombre={seccion} />{nombres[seccion]}</Link>)}</div>
  </details>;
}

export default function Gestion({ seccionSolicitada }: { seccionSolicitada: Seccion }) {
  const [modo, setModo] = useState<"cargando" | "simulado" | "real">("cargando");
  const [sesion, setSesion] = useState<SesionGestion | null>(null);
  const [debeCambiar, setDebeCambiar] = useState(false);
  useEffect(() => {
    function simulado() { sessionStorage.removeItem("gestion-modo"); setModo("simulado"); const guardada = sessionStorage.getItem("gestion-sesion"); if (guardada) setSesion(JSON.parse(guardada)); }
    api<{ identidad_real: boolean }>("ingreso/estado").then(async (estado) => {
      if (!estado.identidad_real) { simulado(); return; }
      sessionStorage.setItem("gestion-modo", "real"); sessionStorage.removeItem("gestion-sesion");
      try { aplicar(await api<Yo>("ingreso/yo")); } catch { /* sin sesión: se muestra el ingreso */ }
      setModo("real");
    }).catch(simulado);
  }, []);
  function aplicar(yo: Yo) { setSesion(sesionDesde(yo)); setDebeCambiar(yo.debe_cambiar_clave); }
  function entrar(empresa: Empresa, perfil: Perfil) { const nueva = { empresa, perfil }; sessionStorage.setItem("gestion-sesion", JSON.stringify(nueva)); setSesion(nueva); }
  async function salir() { if (sesion?.real) await api("ingreso/salir", { method: "POST" }).catch(() => null); sessionStorage.removeItem("gestion-sesion"); setSesion(null); }
  if (modo === "cargando") return <main className="ingreso" aria-busy="true" />;
  if (modo === "real" && !sesion) return <IngresoReal entrar={aplicar} />;
  if (modo === "real" && debeCambiar) return <PrimerIngreso listo={aplicar} />;
  if (!sesion) return <Ingreso entrar={entrar} />;
  const valida = Object.hasOwn(nombres, seccionSolicitada) ? seccionSolicitada : "inicio";
  const permitido = puedeEntrar(sesion.perfil, valida);
  const permitidas = new Set(perfiles[sesion.perfil].secciones);
  return <div className="aplicacion"><aside><div className="marca"><span className="isotipo">SJ</span><div><strong>Suite Juviar</strong><small>Gestión interna</small></div></div><nav aria-label="Secciones">{gruposMenu.map((grupo) => { const secciones = grupo.secciones.filter((s) => permitidas.has(s)); if (!secciones.length) return null; return <GrupoMenu key={`${grupo.nombre}-${valida}`} nombre={grupo.nombre} secciones={secciones} activa={valida} />; })}</nav><Link className="perfil-actual" href="/configuracion"><span>{sesion.nombre ?? perfiles[sesion.perfil].nombre}</span><small>{sesion.real ? perfiles[sesion.perfil].nombre : "Cambiar configuración"}</small></Link></aside><div className="principal-contenedor"><header className="barra"><div><span className="pulso" /> API interna</div><strong>{sesion.empresa}</strong><button className="salir" onClick={salir}>Salir</button></header><main>{permitido ? <Contenido key={`${sesion.perfil}-${valida}`} seccion={valida} sesion={sesion} guardar={entrar} actualizar={aplicar} /> : <AccesoDenegado perfil={sesion.perfil} seccion={valida} />}</main><footer>Suite Juviar Gestión v{VERSION} · commit {COMMIT}</footer></div></div>;
}
