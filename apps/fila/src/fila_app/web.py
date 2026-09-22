from __future__ import annotations

BASE_CSS = """
:root{color-scheme:light;--ink:#17221c;--muted:#607068;--paper:#f4f0e7;--card:#fffefa;
--green:#12633d;--green2:#dcecdf;--amber:#d48a18;--blue:#245e83;--red:#9b332c;
font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-size:18px}main{max-width:760px;margin:auto;
padding:clamp(20px,5vw,56px)}h1{font-size:clamp(2rem,7vw,4.3rem);line-height:.95;letter-spacing:-.035em;
margin:0 0 18px}h2{font-size:1.45rem;margin:36px 0 12px}p{line-height:1.45}.muted{color:var(--muted)}
form,.panel{background:var(--card);padding:clamp(18px,4vw,32px);border-radius:16px;box-shadow:0 10px 28px #3c443817}
label{display:block;font-weight:750;margin:18px 0 7px}input,select,button{width:100%;min-height:58px;
font:inherit;border-radius:12px;border:2px solid #bdc5bd;padding:12px 14px;background:#fff}input:focus,select:focus,
button:focus-visible{outline:4px solid #86b99b;outline-offset:2px}button{margin-top:22px;border:0;background:var(--green);
color:white;font-weight:850;cursor:pointer}button.secondary{background:#e4e8e3;color:var(--ink)}button.danger{background:var(--red)}
.status{text-align:center;min-height:70vh;display:grid;place-content:center}.status strong{font-size:clamp(4rem,18vw,9rem);
line-height:.9}.llamado{background:#0b7d43;color:#fff}.list{display:grid;gap:10px}.row{display:grid;grid-template-columns:1fr auto;
gap:10px;align-items:center;background:var(--card);padding:16px;border-radius:14px}.row button{width:auto;margin:0}.tag{font-size:.8rem;
font-weight:800;padding:5px 9px;border-radius:99px;background:var(--green2)}.offline{position:sticky;top:0;background:#2b2923;
color:#fff;padding:10px;text-align:center;font-weight:750;z-index:5}.oculto{display:none!important}.acciones{display:flex;gap:8px}
.acciones button{margin:0}.espera{background:#111;color:#fff;min-height:100vh}.espera main{max-width:1200px}.espera h1{font-size:5vw}
.pantalla-fila{font-size:3vw}.parpadea{animation:pulso 1s infinite alternate}@keyframes pulso{to{opacity:.28}}
@media(max-width:600px){.row{grid-template-columns:1fr}.acciones{display:grid}.espera h1{font-size:10vw}.pantalla-fila{font-size:7vw}}
@media(prefers-reduced-motion:reduce){.parpadea{animation:none}}
::selection{background:#b5dac3;color:#102018}*{scrollbar-color:#789386 #eee9df}
"""


def pagina(titulo: str, cuerpo: str, script: str = "", clase: str = "") -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#12633d">
<link rel="manifest" href="/fila-manifest.json"><title>{titulo}</title><style>{BASE_CSS}</style></head>
<body class="{clase}">{cuerpo}<script>{script}</script></body></html>"""


def porton(sede: str) -> str:
    cuerpo = f"""<main><p class="muted">Portón · {sede.title()}</p><h1>Registrá tu llegada</h1>
<p>Son tres datos. El guardia confirmará cuando vea el camión.</p><form id="alta">
<label for="patente">Patente</label><input id="patente" autocomplete="off" required placeholder="AB 123 CD">
<div id="conocido" class="muted"></div><label for="productor">Productor</label>
<input id="productor" required maxlength="120" placeholder="Nombre del productor">
<label for="telefono">Tu teléfono <span class="muted">(opcional)</span></label>
<input id="telefono" inputmode="tel" placeholder="549264..."><button>Ya llegué</button>
<p id="error" role="alert"></p></form></main>"""
    script = f"""
const $=s=>document.querySelector(s);let espera;
$('#patente').addEventListener('blur',async()=>{{const p=$('#patente').value;if(p.length<5)return;
 const r=await fetch('/api/publico/vehiculos/'+encodeURIComponent(p));if(r.ok){{const d=await r.json();
 $('#conocido').textContent='Ya conocemos este camión: '+d.chofer+'. Confirmá el productor.';}}}});
$('#alta').addEventListener('submit',async e=>{{e.preventDefault();$('#error').textContent='';
 const body={{sede:'{sede}',patente:$('#patente').value,productor:$('#productor').value,
 telefono:$('#telefono').value||null,id_cliente:crypto.randomUUID()}};
 const r=await fetch('/api/publico/viajes',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify(body)}});
 const d=await r.json();if(!r.ok){{$('#error').textContent=d.detail||'No pudimos registrar. Avisale al guardia.';return}}
 location.href='/t/'+d.ticket;}});
"""
    return pagina("Llegada al portón", cuerpo, script)


def ticket(ticket: str) -> str:
    cuerpo = """<main id="estado" class="status"><div><p class="muted">Estado de tu camión</p>
<h1 id="mensaje">Consultando…</h1><strong id="numero"></strong><p id="detalle"></p></div></main>"""
    script = f"""
async function actualizar(){{const r=await fetch('/api/publico/tickets/{ticket}');if(!r.ok)return;
 const d=await r.json(),m=document.querySelector('#mensaje'),n=document.querySelector('#numero'),x=document.querySelector('#detalle');
 document.body.classList.toggle('llamado',d.estado==='llamado');n.textContent=d.numero_dia||'';
 if(d.estado==='pendiente'){{m.textContent='Esperando que el guardia confirme';x.textContent='Avisale que ya llegaste.'}}
 else if(d.estado==='en_espera'){{m.textContent='Estás en la fila';x.textContent=(d.adelante||0)+' camión(es) adelante';}}
 else if(d.estado==='llamado'){{m.textContent='PASÁ A BÁSCULA';x.textContent='El guardia te está esperando.'}}
 else if(d.estado==='en_bascula'){{m.textContent='Ya pasaste a báscula';x.textContent='Gracias.'}}
 else{{m.textContent='Este registro está cerrado';x.textContent=d.estado;}}}}
actualizar();setInterval(actualizar,15000);
"""
    return pagina("Estado del camión", cuerpo, script)


def guardia(sede: str) -> str:
    cuerpo = f"""<div id="offline" class="offline oculto">Sin conexión — <span>0</span> acciones por enviar</div>
<main><p class="muted">Guardia · {sede.title()}</p><h1>Fila del portón</h1>
<button id="altaDirecta" class="secondary">+ Camión sin celular</button><h2>Por confirmar</h2><div id="pendientes" class="list"></div>
<h2>Fila</h2><button id="siguiente">Llamar siguiente</button><div id="fila" class="list"></div>
<h2>Llamados</h2><div id="llamados" class="list"></div></main>"""
    script = f"""
const sede='{sede}',token=sessionStorage.getItem('guardia-token')||prompt('Clave del guardia');
sessionStorage.setItem('guardia-token',token);const H={{'content-type':'application/json','x-guardia-token':token}};
const id=()=>crypto.randomUUID(),ahora=()=>new Date().toISOString();let datos={{pendientes:[],espera:[],llamados:[]}};
function filaHtml(x,acciones=''){{return `<article class="row"><div><strong>${{x.numero_dia||''}} ${{x.patente}}</strong>
<div class="muted">${{x.productor_texto||''}}</div></div><div class="acciones">${{acciones}}</div></article>`}}
function pintar(){{pendientes.innerHTML=datos.pendientes.map(x=>filaHtml(x,`<button onclick="confirmar(${{x.id}})">Confirmar</button>`)).join('')||'<p class="muted">Ninguno.</p>';
 fila.innerHTML=datos.espera.map((x,i)=>filaHtml(x,`<span class="tag">${{['','Orgánico','Con turno','Espontáneo'][x.grupo]}}</span><button class="secondary" onclick="llamar(${{x.id}},${{i}})">Llamar</button>`)).join('')||'<p class="muted">Fila vacía.</p>';
 llamados.innerHTML=datos.llamados.map(x=>filaHtml(x,`<button onclick="accion(${{x.id}},'paso')">Pasó</button><button class="secondary" onclick="accion(${{x.id}},'no_vino')">No vino</button>`)).join('')||'<p class="muted">Ninguno.</p>';}}
async function cargar(){{try{{const r=await fetch('/api/guardia/{sede}',{{headers:H}});if(!r.ok)throw 0;datos=await r.json();pintar();offline.classList.add('oculto')}}catch{{offline.classList.remove('oculto')}}}}
async function enviar(url,body){{if(!navigator.onLine){{await cola(url,body);return}}const r=await fetch(url,{{method:'POST',headers:H,body:JSON.stringify(body)}});if(!r.ok)alert((await r.json()).detail);await cargar()}}
async function confirmar(viaje){{const c=prompt('CUIT del productor');if(!c)return;await enviar('/api/guardia/viajes/'+viaje+'/confirmar',{{id_cliente:id(),clientecuit:c,clientecodigo:null,declara_organica:confirm('¿Carga orgánica?'),momento_cliente:ahora()}})}}
altaDirecta.onclick=async()=>{{const patente=prompt('Patente');if(!patente)return;const productor=prompt('Productor');if(!productor)return;const clientecuit=prompt('CUIT real');if(!clientecuit)return;
 await enviar('/api/guardia/viajes/directo',{{id_cliente:id(),sede,patente,productor,telefono:null,clientecuit,clientecodigo:null,declara_organica:confirm('¿Carga orgánica?'),momento_cliente:ahora()}})}};
async function llamar(viaje,pos){{let motivo=null;if(pos>0){{motivo=prompt('Motivo: no_responde, documentacion_incompleta, problema_mecanico, indicacion_de_planta u otro');if(!motivo)return}}await accion(viaje,'llamar',motivo)}}
async function accion(viaje,a,motivo=null){{await enviar('/api/guardia/viajes/'+viaje+'/'+a,{{id_cliente:id(),momento_cliente:ahora(),motivo}})}}
siguiente.onclick=()=>datos.espera[0]&&accion(datos.espera[0].id,'llamar');
async function db(){{return new Promise((ok,no)=>{{const q=indexedDB.open('fila-offline',1);q.onupgradeneeded=()=>q.result.createObjectStore('acciones',{{keyPath:'id'}});q.onsuccess=()=>ok(q.result);q.onerror=no}})}}
async function cola(url,body){{const d=await db(),tx=d.transaction('acciones','readwrite');tx.objectStore('acciones').put({{id:body.id_cliente,url,body}});await estadoCola()}}
async function estadoCola(){{const d=await db(),tx=d.transaction('acciones');const q=tx.objectStore('acciones').count();q.onsuccess=()=>{{offline.querySelector('span').textContent=q.result;offline.classList.toggle('oculto',navigator.onLine&&q.result===0)}}}}
async function sincronizar(){{if(!navigator.onLine)return;const d=await db(),tx=d.transaction('acciones','readonly'),q=tx.objectStore('acciones').getAll();q.onsuccess=async()=>{{for(const a of q.result){{const r=await fetch(a.url,{{method:'POST',headers:H,body:JSON.stringify(a.body)}});if(r.ok){{const t=d.transaction('acciones','readwrite');t.objectStore('acciones').delete(a.id)}}}}await estadoCola();await cargar()}}}}
addEventListener('online',sincronizar);navigator.serviceWorker?.register('/fila-sw.js');cargar();estadoCola();setInterval(cargar,10000);
"""
    return pagina("Fila del portón", cuerpo, script)


def pantalla(sede: str) -> str:
    cuerpo = f"""<main><p>Portón · {sede.title()}</p><h1>Próximos camiones</h1><div id="lista" class="pantalla-fila"></div></main>"""
    script = f"""async function ver(){{const r=await fetch('/api/pantalla/{sede}?token='+encodeURIComponent(location.hash.slice(1)));
if(!r.ok)return;const d=await r.json();lista.innerHTML=d.llamados.map(x=>`<div class="parpadea"><strong>${{x.numero_dia}} · ${{x.patente}}</strong> — PASE A BÁSCULA</div>`).join('')||'<p>Sin llamados.</p>'}}ver();setInterval(ver,5000)"""
    return pagina("Pantalla de espera", cuerpo, script, "espera")


MANIFEST = '{"name":"Fila Juviar","short_name":"Fila","start_url":"/guardia/chimbas","display":"standalone","background_color":"#f4f0e7","theme_color":"#12633d","icons":[]}'
SERVICE_WORKER = """const C='fila-v1';self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(['/guardia/chimbas','/fila-manifest.json']))));self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request).then(r=>{let x=r.clone();caches.open(C).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)))})"""
