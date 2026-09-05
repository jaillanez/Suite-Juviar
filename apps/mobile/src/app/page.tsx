import { PERFILES } from "../perfiles";

export default function MobileHome() {
  return (
    <main>
      <p className="kicker">SUITE JUVÍAR · MÓVIL</p>
      <h1>Perfil asignado desde tu puesto.</h1>
      <p className="description">La aplicación habilita únicamente las herramientas correspondientes al legajo autenticado.</p>
      <section aria-label="Perfiles disponibles">
        {PERFILES.map((perfil, index) => (
          <article key={perfil}>
            <span>0{index + 1}</span>
            <strong>{perfil}</strong>
            <small>{perfil === "campo" ? "Fichaje y tareaje" : perfil === "deposito" ? "Entrega y firma de EPP" : "Pesadas y romaneos"}</small>
          </article>
        ))}
      </section>
    </main>
  );
}
