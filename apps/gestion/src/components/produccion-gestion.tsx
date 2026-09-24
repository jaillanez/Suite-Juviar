"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { ErrorVisible } from "./compartidos";

type Romaneo = { id: string; numero: number; estado: string };
export type AreaProduccion = "recepcion" | "fila" | "bot";

const FILA_URL = process.env.NEXT_PUBLIC_FILA_URL ?? "https://juviar-bot.duckdns.org";
const BOT_URL = process.env.NEXT_PUBLIC_BOT_SIMULADOR_URL ?? "http://127.0.0.1:8099";

export function ProduccionGestion({ area = "recepcion" }: { area?: AreaProduccion }) {
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [creado, setCreado] = useState<Romaneo | null>(null);

  async function abrirRomaneo(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    setGuardando(true);
    setError("");
    setCreado(null);
    const datos = new FormData(evento.currentTarget);
    try {
      const respuesta = await api<Romaneo>("recepcion/romaneos", {
        method: "POST",
        body: JSON.stringify({
          productor_cuit: datos.get("productor_cuit"),
          transportista_cuit: datos.get("transportista_cuit"),
          chofer_dni: datos.get("chofer_dni"),
          patente_chasis: datos.get("patente_chasis"),
          patente_acoplado: datos.get("patente_acoplado") || null,
          variedad: datos.get("variedad"),
          finca: datos.get("finca") || null,
          bruto_kg: Number(datos.get("bruto_kg")),
          origen_peso: datos.get("origen_peso"),
          operador_legajo: datos.get("operador_legajo"),
        }),
      });
      setCreado(respuesta);
      formulario.reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo abrir el romaneo.");
    } finally {
      setGuardando(false);
    }
  }

  return <div className="produccion">
    {area === "recepcion" && <section className="tarjeta produccion-operacion">
      <div className="titulo-fila"><div><h2>Abrir romaneo</h2><p className="ayuda">Registra el ingreso real del camión. El peso queda trazado con su origen y operador.</p></div></div>
      {error && <ErrorVisible mensaje={error} />}
      {creado && <div className="resultado-operacion" role="status"><strong>Romaneo {creado.numero} abierto</strong><span>Estado: {creado.estado}</span><small>ID {creado.id}</small></div>}
      <form className="form-grid produccion-form" onSubmit={abrirRomaneo}>
        <label>CUIT del productor<input name="productor_cuit" inputMode="numeric" required /></label>
        <label>CUIT del transportista<input name="transportista_cuit" inputMode="numeric" required /></label>
        <label>DNI del chofer<input name="chofer_dni" inputMode="numeric" required /></label>
        <label>Patente del camión<input name="patente_chasis" autoCapitalize="characters" required /></label>
        <label>Patente del acoplado<input name="patente_acoplado" autoCapitalize="characters" /></label>
        <label>Variedad<input name="variedad" required /></label>
        <label>Finca<input name="finca" /></label>
        <label>Peso bruto (kg)<input name="bruto_kg" type="number" min="1" step="0.01" required /></label>
        <label>Origen del peso<select name="origen_peso"><option value="BASCULA_DIGITAL">Báscula digital</option><option value="CARGA_MANUAL">Carga manual</option></select></label>
        <label>Legajo del operador<input name="operador_legajo" required /></label>
        <button className="primario" disabled={guardando}>{guardando ? "Registrando…" : "Abrir romaneo"}</button>
      </form>
    </section>}

    {area === "fila" && <section className="tarjeta produccion-acceso">
      <div><h2>Fila de camiones</h2><p>Operá llamados, confirmaciones, ingresos directos y búsqueda de productores desde la consola del portón.</p></div>
      <div className="acciones-produccion">
        <a className="boton primario" href={`${FILA_URL}/guardia/chimbas`} target="_blank" rel="noreferrer">Abrir consola de guardia</a>
        <a className="boton" href={`${FILA_URL}/pantalla/chimbas`} target="_blank" rel="noreferrer">Abrir pantalla de espera</a>
      </div>
      <p className="ayuda">La consola se abre en el servicio DMZ y mantiene sus propias credenciales. Gestión nunca recibe el token del guardia.</p>
    </section>}

    {area === "bot" && <section className="tarjeta produccion-acceso">
      <div><h2>Bot de productores</h2><p>Probá consultas por cuenta, estadísticas de cosecha, reportes PDF y administración de contactos.</p></div>
      <div className="acciones-produccion">
        <a className="boton primario" href={BOT_URL} target="_blank" rel="noreferrer">Abrir simulador del bot</a>
        <a className="boton" href="/contactos">Administrar contactos</a>
      </div>
      <p className="ayuda">Los reportes públicos se generan en la DMZ con datos mínimos publicados desde la red interna.</p>
    </section>}
  </div>;
}
