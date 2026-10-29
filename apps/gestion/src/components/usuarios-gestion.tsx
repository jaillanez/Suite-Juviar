"use client";

import { FormEvent, useEffect, useState } from "react";
import { Perfil, perfiles } from "@/lib/acceso";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla, Ventana } from "./compartidos";

type Usuario = { id: string; email: string; nombre: string; perfil: Perfil; empresas: string[]; activo: boolean; debe_cambiar_clave: boolean; creado_en: string };
type Acceso = { momento: string; actor: string; accion: string; detalle: string };

const acciones: Record<string, string> = {
  INGRESO: "Ingresó", SALIDA: "Salió", INGRESO_FALLIDO: "Intento fallido", INGRESO_BLOQUEADO: "Bloqueado por intentos",
  CAMBIO_CLAVE: "Cambió su contraseña", ALTA_USUARIO: "Dio de alta un usuario",
  MODIFICACION_USUARIO: "Modificó un usuario", RESTABLECIMIENTO_CLAVE: "Restableció una contraseña",
};

function fecha(valor: string) {
  return new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

const EMPRESAS = ["ENAV", "JUBIAR"];

function SelectorEmpresas({ valor }: { valor: string[] }) {
  return <fieldset className="empresas-usuario"><legend>Empresas a las que tiene acceso</legend>{EMPRESAS.map(e => <label key={e}><input type="checkbox" name="empresas" value={e} defaultChecked={valor.includes(e)} /> {e}</label>)}</fieldset>;
}

function empresasElegidas(f: FormData) { return f.getAll("empresas").map(String); }

function SelectorPerfil({ valor, cambiar }: { valor: Perfil; cambiar: (p: Perfil) => void }) {
  return <select value={valor} onChange={(e) => cambiar(e.target.value as Perfil)}>{Object.entries(perfiles).map(([id, p]) => <option key={id} value={id}>{p.nombre}</option>)}</select>;
}

export function UsuariosGestion() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [accesos, setAccesos] = useState<Acceso[]>([]);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [perfilNuevo, setPerfilNuevo] = useState<Perfil>("RRHH");
  const [editando, setEditando] = useState<Usuario | null>(null);
  const [creando, setCreando] = useState(false);
  const [errorVentana, setErrorVentana] = useState("");

  async function refrescar() {
    setUsuarios(await api<Usuario[]>("usuarios"));
    setAccesos(await api<Acceso[]>("usuarios/accesos"));
  }
  function informar(x: unknown) { setAviso(""); setError(x instanceof Error ? x.message : "No pudimos completar la operación."); }
  useEffect(() => { refrescar().catch(informar); }, []);

  async function crear(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setAviso(""); setErrorVentana("");
    const f = new FormData(e.currentTarget);
    if (!empresasElegidas(f).length) { setErrorVentana("Elegí al menos una empresa."); return; }
    try {
      const creado = await api<Usuario>("usuarios", { method: "POST", body: JSON.stringify({
        nombre: f.get("nombre"), email: f.get("email"), perfil: perfilNuevo, empresas: empresasElegidas(f), clave_inicial: f.get("clave"),
      }) });
      setCreando(false); setPerfilNuevo("RRHH");
      setAviso(`Usuario creado. Pasale a ${creado.nombre} su correo y la contraseña inicial: la va a cambiar en su primer ingreso.`);
      await refrescar();
    } catch (x) { setErrorVentana(x instanceof Error ? x.message : "No pudimos crear el usuario."); }
  }

  async function guardar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!editando) return; setError(""); setAviso(""); setErrorVentana("");
    const f = new FormData(e.currentTarget);
    if (!empresasElegidas(f).length) { setErrorVentana("Elegí al menos una empresa."); return; }
    try {
      await api(`usuarios/${editando.id}`, { method: "PUT", body: JSON.stringify({
        nombre: f.get("nombre"), perfil: editando.perfil, empresas: empresasElegidas(f), activo: f.get("activo") === "si",
      }) });
      const clave = String(f.get("clave") || "");
      if (clave) await api(`usuarios/${editando.id}/clave`, { method: "POST", body: JSON.stringify({ clave_temporal: clave }) });
      setAviso(clave ? "Cambios guardados. La persona va a tener que elegir una contraseña nueva al entrar." : "Cambios guardados.");
      setEditando(null); await refrescar();
    } catch (x) { setErrorVentana(x instanceof Error ? x.message : "No pudimos guardar los cambios."); }
  }

  return <>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <div className="aviso-exito" role="status">{aviso}</div>}
    {creando && <Ventana titulo="Nuevo usuario" cerrar={() => { setCreando(false); setErrorVentana(""); }}>
      <p className="ayuda">Cada persona entra con su correo y su contraseña. El perfil define qué secciones ve.</p>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <form className="form-grid" onSubmit={crear}>
        <label>Nombre y apellido<input name="nombre" required maxLength={120} /></label>
        <label>Correo<input name="email" type="email" required autoComplete="off" /></label>
        <label>Perfil<SelectorPerfil valor={perfilNuevo} cambiar={setPerfilNuevo} /></label>
        <SelectorEmpresas valor={["ENAV"]} />
        <label>Contraseña inicial<input name="clave" type="text" required minLength={10} autoComplete="off" placeholder="Al menos 10 caracteres" /></label>
        <div className="acciones"><button type="button" onClick={() => setCreando(false)}>Cancelar</button><button className="primario">Crear usuario</button></div>
      </form>
    </Ventana>}

    {editando && <Ventana titulo={`Modificar a ${editando.nombre}`} cerrar={() => { setEditando(null); setErrorVentana(""); }}>
      <p className="ayuda">{editando.email}</p>
      {errorVentana && <ErrorVisible mensaje={errorVentana} />}
      <form className="form-grid" onSubmit={guardar} key={editando.id}>
        <label>Nombre y apellido<input name="nombre" defaultValue={editando.nombre} required maxLength={120} /></label>
        <label>Perfil<SelectorPerfil valor={editando.perfil} cambiar={(p) => setEditando({ ...editando, perfil: p })} /></label>
        <SelectorEmpresas valor={editando.empresas} />
        <label>Estado<select name="activo" defaultValue={editando.activo ? "si" : "no"}><option value="si">Activo</option><option value="no">Sin acceso</option></select></label>
        <label>Contraseña nueva (opcional)<input name="clave" type="text" minLength={10} autoComplete="off" placeholder="Dejala vacía para no cambiarla" /></label>
        <div className="acciones"><button type="button" onClick={() => setEditando(null)}>Cancelar</button><button className="primario">Guardar cambios</button></div>
      </form>
    </Ventana>}

    <section className="tarjeta">
      <div className="titulo-fila"><h2>Usuarios</h2><button className="primario" onClick={() => { setCreando(true); setAviso(""); setError(""); setErrorVentana(""); }}>Nuevo usuario</button></div>
      <p className="ayuda">Tocá una persona para modificarla.</p>
      <Tabla etiqueta="Usuarios" filas={usuarios} alElegir={(u) => { setEditando(u); setAviso(""); setError(""); setErrorVentana(""); }} columnas={[
        { clave: "nombre", titulo: "Nombre" },
        { clave: "email", titulo: "Correo" },
        { clave: "perfil", titulo: "Perfil", valor: (u) => perfiles[u.perfil]?.nombre ?? u.perfil },
        { clave: "empresas", titulo: "Empresas", valor: (u) => u.empresas.join(" y ") },
        { clave: "activo", titulo: "Estado", valor: (u) => !u.activo ? "Sin acceso" : u.debe_cambiar_clave ? "Falta su primer ingreso" : "Activo" },
      ]} />
    </section>

    <section className="tarjeta">
      <h2>Últimos accesos</h2>
      <Tabla etiqueta="Últimos accesos" porPagina={10} filas={accesos} columnas={[
        { clave: "momento", titulo: "Fecha", valor: (a) => fecha(a.momento) },
        { clave: "actor", titulo: "Quién" },
        { clave: "accion", titulo: "Qué hizo", valor: (a) => acciones[a.accion] ?? a.accion },
        { clave: "detalle", titulo: "Detalle" },
      ]} />
    </section>
  </>;
}
