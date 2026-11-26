import type { Metadata, Viewport } from "next";

// Página pública: la piden Meta (app de WhatsApp) y la Ley 25.326 de Protección de Datos Personales.
export const metadata: Metadata = { title: "Política de privacidad · Juviar ENAV", robots: { index: true, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#174f3b" };

const estilo = { maxWidth: 760, margin: "0 auto", padding: "32px 20px 64px", lineHeight: 1.6, color: "#1f2a24", fontSize: 16 } as const;

export default function Privacidad() {
  return <main style={estilo}>
    <h1>Política de privacidad</h1>
    <p>Última actualización: 26 de noviembre de 2026.</p>
    <p>Esta política explica qué datos personales tratan <strong>ENAV S.A.</strong> (CUIT 30-69313567-9) y <strong>JUVIAR S.A.</strong> (CUIT 30-68827405-9), en adelante «la empresa», cuando una persona se comunica con el WhatsApp de la empresa (+54 9 261 342-0830) o usa sus sistemas de gestión, y cómo los protege.</p>

    <h2>Qué datos tratamos</h2>
    <ul>
      <li><strong>Productores de uva:</strong> número de celular, CUIT y razón social de la cuenta vinculada, los mensajes que envía al bot (ofertas de uva, consultas) y los datos de sus entregas en bodega (fechas, kilos, variedad, grado).</li>
      <li><strong>Personal de la empresa:</strong> número de celular, legajo, nombre, y lo que envía por WhatsApp para trámites internos (fotos para mantenimiento, certificados médicos, pedidos de elementos de protección personal).</li>
      <li><strong>Postulantes:</strong> el currículum que envían y los datos que contiene.</li>
      <li><strong>Choferes y camiones en planta:</strong> patente y foto de la patente al ingreso.</li>
    </ul>

    <h2>Para qué los usamos</h2>
    <ul>
      <li>Responder las consultas y gestionar ofertas, turnos y entregas de uva.</li>
      <li>Avisar novedades sobre turnos y entregas al número registrado.</li>
      <li>Gestionar trámites internos del personal (mantenimiento, salud laboral, elementos de protección, aviso del micro).</li>
      <li>Evaluar postulaciones laborales.</li>
      <li>Cumplir obligaciones legales e impositivas.</li>
    </ul>
    <p>No vendemos ni cedemos los datos a terceros con fines comerciales. Los datos de salud solo los ve el personal médico autorizado.</p>

    <h2>Con quién se comparten</h2>
    <p>Los mensajes de WhatsApp viajan por la plataforma de WhatsApp Business de Meta Platforms, según sus propias condiciones. Los datos se guardan en servidores contratados por la empresa. Además, pueden consultarse organismos oficiales cuando la ley lo requiere (por ejemplo ARCA).</p>

    <h2>Cuánto tiempo los guardamos</h2>
    <p>Mientras dure la relación comercial o laboral y luego el tiempo que exijan las normas aplicables. Los currículums se conservan para futuras búsquedas salvo que la persona pida su eliminación.</p>

    <h2>Tus derechos</h2>
    <p>Podés pedir acceso, rectificación, actualización o eliminación de tus datos, y dejar de recibir mensajes. Para hacerlo, escribí a <a href="mailto:Recursoshumanos2023.e@gmail.com">Recursoshumanos2023.e@gmail.com</a> o comunicate con la administración de la empresa. Respondemos dentro de los plazos de la Ley 25.326.</p>
    <p>La Agencia de Acceso a la Información Pública (AAIP), órgano de control de la Ley 25.326, atiende las denuncias y reclamos de quienes resulten afectados en sus derechos por incumplimiento de las normas vigentes en materia de protección de datos personales.</p>

    <h2 id="eliminacion">Cómo pedir la eliminación de tus datos</h2>
    <p>Escribí a <a href="mailto:Recursoshumanos2023.e@gmail.com">Recursoshumanos2023.e@gmail.com</a> con el asunto «Eliminar mis datos», indicando tu nombre y el número de celular con el que te comunicaste. Vamos a confirmar tu identidad y eliminar o anonimizar los datos que no estemos obligados a conservar por ley, y te avisaremos cuando esté hecho.</p>
  </main>;
}
