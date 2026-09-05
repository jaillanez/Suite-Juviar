const modules = [
  { name: "Turnos", detail: "Asistencia y desvíos horarios", stage: "Etapa 1" },
  { name: "RRHH y EPP", detail: "Entregas, catálogo y firma", stage: "Etapa 2" },
  { name: "Cosecha", detail: "Tareaje y trazabilidad de origen", stage: "Etapa 3" },
  { name: "Recepción", detail: "Romaneos y pesadas de báscula", stage: "Etapa 3" },
];

export default function Home() {
  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#inicio" aria-label="Suite Juviar, inicio">
          <span className="brandMark" aria-hidden="true">SJ</span>
          <span>Suite Juviar</span>
        </a>
        <span className="environment">BASE 0.1</span>
      </header>

      <section className="hero" id="inicio">
        <div>
          <p className="eyebrow">OPERACIÓN UNIFICADA · ENAV / JUBIAR</p>
          <h1>Una base confiable para cada operación crítica.</h1>
          <p className="lead">
            Personal, turnos, EPP, cosecha y recepción sobre una arquitectura modular,
            auditable y preparada para crecer por etapas.
          </p>
          <div className="status" role="status">
            <span className="statusDot" aria-hidden="true" />
            Plataforma base configurada
          </div>
        </div>
        <aside className="principles" aria-label="Principios de la plataforma">
          <p className="cardLabel">Principios operativos</p>
          <dl>
            <div><dt>01</dt><dd>Datos personales protegidos</dd></div>
            <div><dt>02</dt><dd>Bitácora inmutable</dd></div>
            <div><dt>03</dt><dd>Módulos independientes</dd></div>
          </dl>
        </aside>
      </section>

      <section className="moduleSection" aria-labelledby="modules-title">
        <div className="sectionHeading">
          <div><p className="eyebrow">HOJA DE RUTA</p><h2 id="modules-title">Módulos de negocio</h2></div>
          <p>Construcción ordenada por dependencia técnica.</p>
        </div>
        <div className="moduleGrid">
          {modules.map((module) => (
            <article className="moduleCard" key={module.name}>
              <span>{module.stage}</span>
              <h3>{module.name}</h3>
              <p>{module.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
