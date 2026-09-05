(function(){
  "use strict";

  /* ---- viñedo del hero ---- */
  var vg = document.getElementById('vineyard'), ps = document.getElementById('posts');
  if (vg){
    var vx = 720, vy = 462, out = '', po = '';
    for (var i = -14; i <= 14; i++){
      var xb = vx + i * 118 * 1.9;
      out += '<line x1="' + vx + '" y1="' + vy + '" x2="' + xb + '" y2="790"/>';
    }
    for (var j = 0; j < 34; j++){
      var rowProgress = j / 33, y = vy + 16 + Math.pow(rowProgress, 2.1) * 300;
      var w = 1.2 + Math.pow(rowProgress, 2) * 5, h = 5 + Math.pow(rowProgress, 2) * 34;
      for (var k = -9; k <= 9; k++){
        var sp = (y - vy) / (790 - vy);
        var x = vx + k * 118 * 1.9 * sp;
        if (x > -40 && x < 1480) po += '<rect x="' + (x - w/2).toFixed(1) + '" y="' + (y - h).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + h.toFixed(1) + '"/>';
      }
    }
    vg.innerHTML = out;
    ps.innerHTML = po;
  }

  /* ---- arte de ranura ---- */
  var art = {
    vineyard: '<defs><linearGradient id="gv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6E7F52"/><stop offset="1" stop-color="#2B3324"/></linearGradient></defs><rect width="400" height="300" fill="url(#gv)"/><g stroke="#1E2419" stroke-width="3" opacity=".55">' + (function(){var s='';for(var i=-8;i<=8;i++){s+='<line x1="200" y1="90" x2="'+(200+i*150)+'" y2="320"/>';}return s;})() + '</g><rect y="0" width="400" height="92" fill="#8FA26B" opacity=".35"/>',
    tanks: '<rect width="400" height="300" fill="#2A2028"/><g fill="#4A4048">' + (function(){var s='';for(var i=0;i<6;i++){s+='<rect x="'+(18+i*64)+'" y="60" width="46" height="200" rx="4"/>';}return s;})() + '</g><g fill="#6B5C66" opacity=".7">' + (function(){var s='';for(var i=0;i<6;i++){s+='<rect x="'+(18+i*64)+'" y="60" width="12" height="200"/>';}return s;})() + '</g><rect y="252" width="400" height="48" fill="#1A1219"/>',
    barrel: '<rect width="400" height="300" fill="#33212A"/><g stroke="#7A4A38" stroke-width="2" fill="#4A2C28">' + (function(){var s='';for(var r=0;r<3;r++){for(var c=0;c<5;c++){s+='<ellipse cx="'+(46+c*78)+'" cy="'+(58+r*92)+'" rx="34" ry="34"/>';}}return s;})() + '</g>',
    drums: '<rect width="400" height="300" fill="#2B2530"/><g fill="#B0741A" opacity=".85">' + (function(){var s='';for(var r=0;r<2;r++){for(var c=0;c<6;c++){s+='<rect x="'+(14+c*64)+'" y="'+(70+r*104)+'" width="48" height="92" rx="5"/>';}}return s;})() + '</g><g stroke="#3A2C18" stroke-width="2" opacity=".5">' + (function(){var s='';for(var r=0;r<2;r++){for(var c=0;c<6;c++){s+='<line x1="'+(14+c*64)+'" y1="'+(100+r*104)+'" x2="'+(62+c*64)+'" y2="'+(100+r*104)+'"/><line x1="'+(14+c*64)+'" y1="'+(132+r*104)+'" x2="'+(62+c*64)+'" y2="'+(132+r*104)+'"/>';}}return s;})() + '</g>',
    evap: '<rect width="400" height="300" fill="#24202A"/><g stroke="#8C8090" stroke-width="6" fill="none" opacity=".8"><path d="M40 270V90a26 26 0 0 1 52 0v180"/><path d="M150 270V70a26 26 0 0 1 52 0v200"/><path d="M260 270V110a26 26 0 0 1 52 0v160"/></g><g stroke="#B0741A" stroke-width="4" fill="none" opacity=".8"><path d="M66 150h84M176 190h84M286 130h74"/></g>'
  };
  Array.prototype.slice.call(document.querySelectorAll('.slot[data-art]')).forEach(function(el){
    var key = el.getAttribute('data-art');
    if (!art[key]) return;
    var svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 400 300');
    svg.setAttribute('preserveAspectRatio','xMidYMid slice');
    svg.setAttribute('aria-hidden','true');
    svg.innerHTML = art[key];
    el.insertBefore(svg, el.firstChild);
  });

  /* ---- idioma ---- */
  var nodes = Array.prototype.slice.call(document.querySelectorAll('[data-en]'));
  nodes.forEach(function(el){ el.dataset.es = el.innerHTML; });
  var phNodes = Array.prototype.slice.call(document.querySelectorAll('[data-en-ph]'));
  phNodes.forEach(function(el){ el.dataset.esPh = el.getAttribute('placeholder') || ''; });
  var btnEs = document.getElementById('btn-es'), btnEn = document.getElementById('btn-en');
  function setLang(l){
    nodes.forEach(function(el){ el.innerHTML = (l==='en') ? el.dataset.en : el.dataset.es; });
    phNodes.forEach(function(el){ el.setAttribute('placeholder',(l==='en')?el.getAttribute('data-en-ph'):el.dataset.esPh); });
    document.documentElement.lang = l;
    btnEs.setAttribute('aria-pressed', String(l==='es'));
    btnEn.setAttribute('aria-pressed', String(l==='en'));
    try{ localStorage.setItem('lang', l); }catch(e){}
    render();
  }
  btnEs.addEventListener('click', function(){ setLang('es'); });
  btnEn.addEventListener('click', function(){ setLang('en'); });

  /* ---- enrutamiento ---- */
  var form = document.getElementById('lead'), payloadEl = document.getElementById('payload');
  var ref = 'B2B-2026-' + String(Math.floor(Math.random()*900)+100);
  document.getElementById('r-ref').textContent = ref;
  function lang(){ return document.documentElement.lang === 'en' ? 'en' : 'es'; }
  function t(es,en){ return lang()==='en' ? en : es; }
  function product(){ var e=form.querySelector('input[name="product"]:checked'); return e?e.value:'bulk_wine'; }
  function certs(){ return Array.prototype.slice.call(form.querySelectorAll('input[name="cert"]:checked')).map(function(c){return c.value;}); }
  function num(id){ var v=parseFloat(document.getElementById(id).value); return isNaN(v)?null:v; }

  function route(p,c){
    var organic = c.indexOf('Organic_Letis')>-1, kosher = c.indexOf('Kosher')>-1;
    if (p==='bulk_wine') return {plant:'JUVIAR S.A.', site:'Lavalle, Mendoza', eta:t('5–7 días','5–7 days')};
    if (p==='jcu_decolourised' || p==='jcu_alcoholised') return {plant:'JUVIAR S.A.', site:t('Planta concentradora, Lavalle','Concentrate plant, Lavalle'), eta:t('7–10 días','7–10 days')};
    if (organic || kosher) return {plant:'ENAV S.A.', site:'Chimbas, San Juan', eta:t('7–10 días','7–10 days')};
    if (p==='jcu_virgin') return {plant:t('ENAV o JUVIAR','ENAV or JUVIAR'), site:t('Según balance de stock','Subject to stock balance'), eta:t('10–14 días','10–14 days')};
    return {plant:'ENAV S.A.', site:'Media Agua, San Juan', eta:t('7–10 días','7–10 days')};
  }

  function render(){
    var p = product(), c = certs(), isWine = p==='bulk_wine';
    Array.prototype.slice.call(document.querySelectorAll('.wine-only')).forEach(function(el){ el.classList.toggle('hide', !isWine); });
    var r = route(p,c);
    document.getElementById('r-plant').textContent = r.plant;
    document.getElementById('r-site').textContent = r.site;
    document.getElementById('r-eta').textContent = r.eta;
    var specs = { target_brix:num('brix'), ph_target:num('ph'), total_acidity_gl:num('acidity'), so2_free_ppm:num('so2') };
    if (isWine){ specs.abv_target = num('abv'); specs.optical_density_420_520 = document.getElementById('colour').value || null; }
    payloadEl.textContent = JSON.stringify({
      lead_id: ref,
      client_metadata:{
        company_name: document.getElementById('company').value || null,
        contact_email: document.getElementById('email').value || null,
        country: document.getElementById('country').value || null,
        industry_segment: document.getElementById('segment').value
      },
      product_line: p,
      projected_volume:{ annual_tons:num('volume'), shipment_format:document.getElementById('format').value },
      lab_specs: specs,
      certifications_required: c,
      routing:{ plant:r.plant, site:r.site },
      inv_2026:{ tacit_acceptance_days:30, transit_certificate:'digital' }
    }, null, 2);
  }
  form.addEventListener('input', render);
  form.addEventListener('change', render);
  form.addEventListener('submit', function(e){
    e.preventDefault();
    var msg = document.getElementById('formmsg');
    var btn = form.querySelector('.submit');
    var co = document.getElementById('company').value.trim();
    var em = document.getElementById('email').value.trim();
    var pa = document.getElementById('country').value.trim();
    if (!co || !em || !pa){ msg.textContent = t('Faltan razón social, correo o país de destino.','Company, email or destination country is missing.'); return; }
    if (em.indexOf('@') < 1 || em.indexOf('.') < 0){ msg.textContent = t('Revise el correo corporativo.','Check the work email.'); return; }

    btn.disabled = true;
    msg.textContent = t('Enviando…','Sending…');

    fetch(form.dataset.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': form.dataset.token || '' },
      body: payloadEl.textContent
    }).then(function(res){
      if (!res.ok) throw new Error(res.status);
      return res.json();
    }).then(function(data){
      msg.textContent = t('Solicitud registrada con el número ' + data.referencia + '. Le responde el equipo comercial.',
                          'Request registered as ' + data.referencia + '. Our sales team will get back to you.');
      form.querySelectorAll('input, select, button').forEach(function(el){ el.disabled = true; });
    }).catch(function(){
      btn.disabled = false;
      msg.textContent = t('No se pudo enviar. Reintente en unos minutos o escriba a exportaciones@juviar.com.ar.',
                          'Could not send. Try again shortly or write to exportaciones@juviar.com.ar.');
    });
  });
  document.getElementById('copybtn').addEventListener('click', function(){
    var b = this, o = b.textContent;
    function done(ok){ b.textContent = ok ? t('Copiado','Copied') : t('No se pudo copiar','Copy failed'); setTimeout(function(){ b.textContent = o; },1600); }
    if (navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(payloadEl.textContent).then(function(){done(true);},function(){done(false);});
    } else { done(false); }
  });

  var saved = null;
  try{ saved = localStorage.getItem('lang'); }catch(e){}
  if (saved === 'en'){ setLang('en'); } else { render(); }
})();
