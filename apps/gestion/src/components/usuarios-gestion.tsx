"use client";

import { FormEvent, useEffect, useState } from "react";
import { Perfil, perfiles } from "@/lib/acceso";
import { api } from "@/lib/api";
import { ErrorVisible, Tabla } from "./compartidos";

type Usuario = { id: string; email: string; nombre: string; perfil: Perfil; empresa: string; activo: boolean; debe_cambiar_clave: boolean; creado_en: string };
type Acceso = { momento: string; actor: string; accion: string; detalle: string };

const acciones: Record<string, string> = {
  INGRESO: "Ingresó", SALIDA: "Salió", INGRESO_FALLIDO: "Intento fallido", INGRESO_BLOQUEADO: "Bloqueado por intentos",
  CAMBIO_CLAVE: "Cambió su contraseña", ALTA_USUARIO: "Dio de alta un usuario",
  MODIFICACION_USUARIO: "Modificó un usuario", RESTABLECIMIENTO_CLAVE: "Restableció una contraseña",
};

function fecha(valor: string) {
  return new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

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

  async function refrescar() {
    setUsuarios(await api<Usuario[]>("usuarios"));
    setAccesos(await api<Acceso[]>("usuarios/accesos"));
  }
  function informar(x: unknown) { setAviso(""); setError(x instanceof Error ? x.message : "No pudimos completar la operación."); }
  useEffect(() => { refrescar().catch(informar); }, []);

  async function crear(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setAviso("");
    const form = e.currentTarget; const f = new FormData(form);
    try {
      const creado = await api<Usuario>("usuarios", { method: "POST", body: JSON.stringify({
        nombre: f.get("nombre"), email: f.get("email"), perfil: perfilNuevo, empresa: f.get("empresa"), clave_inicial: f.get("clave"),
      }) });
      form.reset(); setPerfilNuevo("RRHH");
      setAviso(`Usuario creado. Pasale a ${creado.nombre} su correo y la contraseña inicial: la va a cambiar en su primer ingreso.`);
      await refrescar();
    } catch (x) { informar(x); }
  }

  async function guardar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!editando) return; setError(""); setAviso("");
    const f = new FormData(e.currentTarget);
    try {
      await api(`usuarios/${editando.id}`, { method: "PUT", body: JSON.stringify({
        nombre: f.get("nombre"), perfil: editando.perfil, empresa: f.get("empresa"), activo: f.get("activo") === "si",
      }) });
      const clave = String(f.get("clave") || "");
      if (clave) await api(`usuarios/${editando.id}/clave`, { method: "POST", body: JSON.stringify({ clave_temporal: clave }) });
      setAviso(clave ? "Cambios guardados. La persona va a tener que elegir una contraseña nueva al entrar." : "Cambios guardados.");
      setEditando(null); await refrescar();
    } catch (x) { informar(x); }
  }

  return <>
    {error && <ErrorVisible mensaje={error} />}
    {aviso && <div className="aviso-exito" role="status">{aviso}</div>}
    <section className="tarjeta">
      <h2>Nuevo usuario</h2>
      <p className="ayuda">Cada persona entra con su correo y su contraseña. El perfil define qué secciones ve.</p>
      <form className="form-grid" onSubmit={crear}>
        <label>Nombre y apellido<input name="nombre" required maxLength={120} /></label>
        <label>Correo<input name="email" type="email" required autoComplete="off" /></label>
        <label>Perfil<SelectorPerfil valor={perfilNuevo} cambiar={setPerfilNuevo} /></label>
        <label>Empresa<select name="empresa" defaultValue="ENAV"><option>ENAV</option><option>JUBIAR</option></select></label>
        <label>Contraseña inicial<input name="clave" type="text" required minLength={10} autoComplete="off" placeholder="Al menos 10 caracteres" /></label>
        <div className="acciones"><button className="primario">Crear usuario</button></div>
      </form>
    </section>

    {editando && <section className="tarjeta">
      <h2>Modificar a {editando.nombre}</h2>
      <form className="form-grid" onSubmit={guardar} key={editando.id}>
        <label>Nombre y apellido<input name="nombre" defaultValue={editando.nombre} required maxLength={120} /></label>
        <label>Perfil<SelectorPerfil valor={editando.perfil} cambiar={(p) => setEditando({ ...editando, perfil: p })} /></label>
        <label>Empresa<select name="empresa" defaultValue={editando.empresa}><option>ENAV</option><option>JUBIAR</option></select></label>
        <label>Estado<select name="activo" defaultValue={editando.activo ? "si" : "no"}><option value="si">Activo</option><option value="no">Sin acceso</option></select></label>
        <label>Contraseña nueva (opcional)<input name="clave" type="text" minLength={10} autoComplete="off" placeholder="Dejala vacía para no cambiarla" /></label>
        <div className="acciones"><button type="button" onClick={() => setEditando(null)}>Cancelar</button><button className="primario">Guardar cambios</button></div>
      </form>
    </section>}

    <section className="tarjeta">
      <h2>Usuarios</h2>
      <Tabla etiqueta="Usuarios" filas={usuarios} columnas={[
        { clave: "nombre", titulo: "Nombre" },
        { clave: "email", titulo: "Correo" },
        { clave: "perfil", titulo: "Perfil", valor: (u) => perfiles[u.perfil]?.nombre ?? u.perfil },
        { clave: "empresa", titulo: "Empresa" },
        { clave: "activo", titulo: "Estado", valor: (u) => !u.activo ? "Sin acceso" : u.debe_cambiar_clave ? "Falta su primer ingreso" : "Activo" },
        { clave: "id", titulo: "", valor: (u) => <button onClick={() => { setEditando(u); setAviso(""); setError(""); }}>Modificar</button> },
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
