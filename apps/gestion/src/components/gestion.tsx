"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Empresa, nombres, puedeEntrar, Perfil, perfiles, Seccion } from "@/lib/acceso";
import { api } from "@/lib/api";
import { ErrorVisible, Simulado, Tabla, Vacio } from "./compartidos";

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0";
const COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT ?? "local";
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/backend";

type Stock = Record<string, unknown> & { item_codigo: string; disponible: number; minimo: number; estado: string };
type Catalogo = Record<string, unknown> & { codigo: string; producto: string; familia: string; marca: string };

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
  const [catalogo, setCatalogo] = useState<Catalogo[]>([]); const [stock, setStock] = useState<Stock[]>([]); const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<Catalogo[]>("rrhh-epp/catalogo", { headers: { "X-Legajo-Usuario": "1210" } }), api<Stock[]>("rrhh-epp/stock", { headers: { "X-Legajo-Usuario": "1210" } })]).then(([c, s]) => { setCatalogo(c); setStock(s); }).catch((e) => setError(e.message)); }, []);
  return <><Encabezado titulo="Elementos de protección personal" descripcion="Catálogo, matriz, stock, avisos y constancias de entrega." />{error && <ErrorVisible mensaje={error} />}<div className="metricas"><article><span>Elementos RD 068/11</span><strong>{catalogo.length || "—"}</strong><small>Catálogo vigente</small></article><article><span>Ítems bajo mínimo</span><strong>{stock.filter((s) => s.disponible < s.minimo).length || "—"}</strong><small>Avisos, no pedidos de compra</small></article></div><div className="rejilla"><section className="tarjeta"><div className="titulo-fila"><h2>Catálogo</h2><span className="estado">Sólo lectura</span></div>{catalogo.length ? <Tabla etiqueta="Catálogo EPP" filas={catalogo} columnas={[{ clave: "codigo", titulo: "Código" }, { clave: "producto", titulo: "Elemento" }, { clave: "familia", titulo: "Familia" }, { clave: "marca", titulo: "Marca" }]} /> : <Vacio>Cargando catálogo…</Vacio>}</section><section className="tarjeta"><div className="titulo-fila"><h2>Stock</h2><Simulado nivel="tabla" /></div>{stock.length ? <Tabla etiqueta="Stock EPP" filas={stock} columnas={[{ clave: "item_codigo", titulo: "Ítem" }, { clave: "disponible", titulo: "Disponible" }, { clave: "minimo", titulo: "Mínimo" }, { clave: "estado", titulo: "Estado", valor: (f) => <span className={f.disponible < f.minimo ? "estado estado-alerta" : "estado"}>{f.estado}</span> }]} /> : <Vacio>Cargando existencias…</Vacio>}</section></div></>;
}

function Analitica() {
  const hoy = new Date().toISOString().slice(0, 10); const inicio = `${new Date().getFullYear()}-01-01`;
  return <><Encabezado titulo="Analítica EPP" descripcion="Consumo, duración real y reclamos, siempre con el tamaño de muestra visible." /><div className="metricas"><article><span>Costo</span><strong>—</strong><small>Faltan precios reales de Compras</small></article><article><span>Exportación</span><strong>Bloqueada</strong><small>La fuente actual es simulada</small></article></div><section className="tarjeta"><h2>Tablero del período</h2><p>La API disponible todavía entrega esta vista como documento. Se abre dentro de Gestión sin habilitar una exportación inválida.</p><iframe className="visor" title="Tablero analítico" src={`${API_BASE}/epp-analitica/?desde=${inicio}&hasta=${hoy}`} /></section></>;
}

function Legajo() {
  const [numero, setNumero] = useState("1042"); const [url, setUrl] = useState(`${API_BASE}/legajo/1042`);
  return <><Encabezado titulo="Legajos" descripcion="Consulta documental con formato correspondiente a la empresa del trabajador." /><section className="tarjeta"><form className="form-linea" onSubmit={(e: FormEvent) => { e.preventDefault(); setUrl(`${API_BASE}/legajo/${numero}`); }}><label>Número de legajo<input value={numero} onChange={(e) => setNumero(e.target.value)} required /></label><button className="primario">Buscar</button></form><iframe className="visor" title="Ficha del legajo" src={url} /></section></>;
}

function Salud() {
  const [mensaje, setMensaje] = useState(""); const [error, setError] = useState("");
  async function cargar(e: FormEvent<HTMLFormElement>) { e.preventDefault(); setError(""); const f = new FormData(e.currentTarget); try { const r = await api<{ id: string }>("salud/certificados", { method: "POST", headers: { "X-Rol": "MEDICO" }, body: JSON.stringify(Object.fromEntries(f)) }); setMensaje(`Certificado ${r.id} cargado y auditado.`); } catch (x) { setError(x instanceof Error ? x.message : "No fue posible cargar el certificado."); } }
  return <><Encabezado titulo="Salud laboral" descripcion="Área separada. Acceso exclusivo del Servicio Médico." />{error && <ErrorVisible mensaje={error} />}{mensaje && <div className="aviso-exito" role="status">{mensaje}</div>}<section className="tarjeta"><h2>Nuevo certificado</h2><form className="form-grid" onSubmit={cargar}><label>Legajo<input name="legajo" required defaultValue="1042" /></label><label>Diagnóstico del catálogo<select name="diagnostico_codigo" required><option value="MUESTRA-RESP">Afección respiratoria (muestra)</option><option value="MUESTRA-TRAU">Traumatismo (muestra)</option></select></label><label>Desde<input name="desde" type="date" required /></label><label>Hasta<input name="hasta" type="date" required /></label><button className="primario">Registrar certificado</button></form><p className="preliminar">La evaluación del artículo 208 es preliminar hasta contar con las fuentes reales.</p></section></>;
}

function Turnos() {
  const [salida, setSalida] = useState(""); const [error, setError] = useState("");
  async function cargar(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const f = Object.fromEntries(new FormData(e.currentTarget)); try { const r = await api<{ id: string }>("turnos/cronogramas", { method: "POST", body: JSON.stringify(f) }); setSalida(`Cronograma ${r.id} registrado. Todavía no genera una imputación.`); } catch (x) { setError(x instanceof Error ? x.message : "No fue posible registrar."); } }
  return <><Encabezado titulo="Turnos y conciliación" descripcion="Cronogramas, desvíos y propuestas que RRHH debe aprobar expresamente." />{error && <ErrorVisible mensaje={error} />}{salida && <div className="aviso-exito">{salida}</div>}<section className="tarjeta"><h2>Cargar cronograma</h2><form className="form-grid" onSubmit={cargar}><label>Legajo<input name="legajo" defaultValue="1042" required /></label><label>Sector<input name="sector" defaultValue="Bodega" required /></label><label>Fecha<input name="fecha" type="date" required /></label><label>Desde<input name="desde" type="time" required /></label><label>Hasta<input name="hasta" type="time" required /></label><input type="hidden" name="autor" value="supervisor-prueba" /><button className="primario">Guardar cronograma</button></form><p className="ayuda">Guardar un cronograma no imputa novedades. La aprobación se realiza luego, en lote, por RRHH.</p></section></>;
}

type Busqueda = Record<string, unknown> & { id: string; nombre: string; perfil: string; definido_por: string; definido_en: string };
type Cv = Record<string, unknown> & { id: string; nombre: string; requiere_revision: boolean; resultado?: { puntaje: number; razones: string[] } };

function Seleccion() {
  const [busquedas, setBusquedas] = useState<Busqueda[]>([]); const [cvs, setCvs] = useState<Cv[]>([]); const [error, setError] = useState("");
  const recargar = () => Promise.all([api<Busqueda[]>("seleccion/busquedas"), api<Cv[]>("seleccion/cvs")]).then(([b, c]) => { setBusquedas(b); setCvs(c); }).catch((e) => setError(e.message));
  useEffect(() => { recargar(); }, []);
  async function crear(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const f = Object.fromEntries(new FormData(e.currentTarget)); try { await api("seleccion/busquedas", { method: "POST", body: JSON.stringify({ ...f, edad_minima: f.edad_minima ? Number(f.edad_minima) : null, edad_maxima: f.edad_maxima ? Number(f.edad_maxima) : null, secundaria_completa: f.secundaria_completa === "on" }) }); e.currentTarget.reset(); recargar(); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo crear la búsqueda."); } }
  async function cargar(e: FormEvent<HTMLInputElement>) { const archivo = e.currentTarget.files?.[0]; if (!archivo) return; const contenido_base64 = await new Promise<string>((resolve, reject) => { const lector = new FileReader(); lector.onerror = reject; lector.onload = () => resolve(String(lector.result).split(",")[1]); lector.readAsDataURL(archivo); }); try { await api("seleccion/cvs/lote", { method: "POST", body: JSON.stringify({ archivos: [{ nombre: archivo.name, contenido_base64 }] }) }); recargar(); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo cargar el lote."); } }
  return <><Encabezado titulo="Selección" descripcion="Búsquedas explicables, ranking revisable y originales siempre conservados." />{error && <ErrorVisible mensaje={error} />}<div className="rejilla"><section className="tarjeta"><h2>Abrir búsqueda</h2><form className="form-grid" onSubmit={crear}><label>Nombre<input name="nombre" required /></label><label>Perfil<select name="perfil"><option>BODEGA</option><option>MANTENIMIENTO</option><option>ADMINISTRACION</option></select></label><label>Edad mínima<input name="edad_minima" type="number" min="0" /></label><label>Edad máxima<input name="edad_maxima" type="number" min="0" /></label><label><span>Secundaria completa</span><input name="secundaria_completa" type="checkbox" /></label><input type="hidden" name="definido_por" value="rrhh-prueba" /><button className="primario">Crear búsqueda</button></form></section><section className="tarjeta"><div className="titulo-fila"><h2>Búsquedas abiertas</h2><Simulado nivel="tabla" /></div>{busquedas.length ? <Tabla etiqueta="Búsquedas" filas={busquedas} columnas={[{ clave: "nombre", titulo: "Búsqueda" }, { clave: "perfil", titulo: "Perfil" }, { clave: "definido_por", titulo: "Criterio por" }, { clave: "definido_en", titulo: "Fecha", valor: (f) => new Date(f.definido_en).toLocaleString("es-AR") }]} /> : <Vacio>No hay búsquedas abiertas.</Vacio>}</section><section className="tarjeta"><div className="titulo-fila"><h2>Bandeja de CV</h2><label className="carga">Carga manual<input type="file" accept="application/pdf" onChange={cargar} /></label></div>{cvs.length ? <Tabla etiqueta="CV recibidos" filas={cvs} columnas={[{ clave: "nombre", titulo: "Original" }, { clave: "requiere_revision", titulo: "Estado", valor: (f) => <span className={f.requiere_revision ? "estado estado-alerta" : "estado"}>{f.requiere_revision ? "Revisión" : "Leído"}</span> }, { clave: "resultado", titulo: "Motivo", valor: (f) => f.resultado?.razones?.join(" · ") ?? "Elegí una búsqueda para evaluar" }]} /> : <Vacio>Cargá un lote de CV en PDF para comenzar.</Vacio>}</section></div></>;
}

type Tema = Record<string, unknown> & { id: string; nombre: string; horas: number; dictados: Array<{ id: string; fecha: string; instructor: string }> };
function Capacitaciones() {
  const [temas, setTemas] = useState<Tema[]>([]); const [error, setError] = useState("");
  const recargar = () => api<Tema[]>("capacitaciones/temas").then(setTemas).catch((e) => setError(e.message)); useEffect(() => { recargar(); }, []);
  async function crear(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const f = Object.fromEntries(new FormData(e.currentTarget)); try { await api("capacitaciones/temas", { method: "POST", body: JSON.stringify({ nombre: f.nombre, horas: Number(f.horas) }) }); e.currentTarget.reset(); recargar(); } catch (x) { setError(x instanceof Error ? x.message : "No se pudo crear el tema."); } }
  return <><Encabezado titulo="Capacitaciones" descripcion="Temas, dictados, asistencia firmada y seguimiento anual." />{error && <ErrorVisible mensaje={error} />}<div className="rejilla"><section className="tarjeta"><h2>Nuevo tema</h2><form className="form-linea" onSubmit={crear}><label>Nombre<input name="nombre" required /></label><label>Horas<input name="horas" type="number" min="0.5" step="0.5" required /></label><button className="primario">Crear tema</button></form></section><section className="tarjeta"><div className="titulo-fila"><h2>Temas y tandas</h2><Simulado nivel="tabla" /></div>{temas.length ? <Tabla etiqueta="Temas" filas={temas} columnas={[{ clave: "nombre", titulo: "Tema" }, { clave: "horas", titulo: "Horas" }, { clave: "dictados", titulo: "Tandas", valor: (f) => f.dictados.length }]} /> : <Vacio>No hay temas cargados.</Vacio>}</section><section className="tarjeta"><h2>Supervisores con asistencia baja</h2><Vacio>Sin alertas con la muestra actual.</Vacio></section></div></>;
}

function Pendiente({ seccion }: { seccion: Seccion }) { return <><Encabezado titulo={nombres[seccion]} descripcion="Módulo incorporado al armazón de Gestión." /><section className="tarjeta"><h2>Integración en curso</h2><p>El dominio existe, pero su API de gestión todavía debe completarse antes de habilitar esta operación. No se simulan reglas en el navegador.</p></section></>; }

function Contenido({ seccion, empresa }: { seccion: Seccion; empresa: Empresa }) {
  if (seccion === "inicio") return <Inicio empresa={empresa} />; if (seccion === "epp") return <Epp />; if (seccion === "analitica") return <Analitica />; if (seccion === "seleccion") return <Seleccion />; if (seccion === "capacitaciones") return <Capacitaciones />; if (seccion === "legajo") return <Legajo />; if (seccion === "salud") return <Salud />; if (seccion === "turnos") return <Turnos />; return <Pendiente seccion={seccion} />;
}

export default function Gestion({ seccionSolicitada }: { seccionSolicitada: Seccion }) {
  const [sesion, setSesion] = useState<{ empresa: Empresa; perfil: Perfil } | null>(null);
  useEffect(() => { const guardada = sessionStorage.getItem("gestion-sesion"); if (guardada) setSesion(JSON.parse(guardada)); }, []);
  function entrar(empresa: Empresa, perfil: Perfil) { const nueva = { empresa, perfil }; sessionStorage.setItem("gestion-sesion", JSON.stringify(nueva)); setSesion(nueva); }
  if (!sesion) return <Ingreso entrar={entrar} />;
  const valida = Object.hasOwn(nombres, seccionSolicitada) ? seccionSolicitada : "inicio";
  const permitido = puedeEntrar(sesion.perfil, valida);
  return <div className="aplicacion"><aside><div className="marca"><span className="isotipo">SJ</span><div><strong>Suite Juviar</strong><small>Gestión interna</small></div></div><nav aria-label="Secciones">{perfiles[sesion.perfil].secciones.map((s) => <Link key={s} href={s === "inicio" ? "/" : `/${s}`} className={s === valida ? "activo" : ""}><Icono nombre={s} />{nombres[s]}</Link>)}</nav><div className="modo-prueba"><strong>Modo prueba</strong><label>Perfil<select value={sesion.perfil} onChange={(e) => entrar(sesion.empresa, e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select></label></div></aside><div className="principal-contenedor"><div className="franja">DATOS SIMULADOS · SIN VALIDEZ PRODUCTIVA</div><header className="barra"><div><span className="pulso" /> API interna</div><label>Empresa<select value={sesion.empresa} onChange={(e) => entrar(e.target.value as Empresa, sesion.perfil)}><option>ENAV</option><option>JUBIAR</option></select></label><button className="salir" onClick={() => { sessionStorage.removeItem("gestion-sesion"); setSesion(null); }}>Salir</button></header><main>{permitido ? <Contenido seccion={valida} empresa={sesion.empresa} /> : <><Encabezado titulo="Acceso denegado" descripcion="Tu perfil no tiene permiso para ingresar a esta sección." /><ErrorVisible mensaje={`El perfil ${perfiles[sesion.perfil].nombre} no puede acceder a ${nombres[valida]}.`} /></>}</main><footer>Suite Juviar Gestión v{VERSION} · commit {COMMIT}</footer></div></div>;
}
