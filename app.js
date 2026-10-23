(() => {
  const cfg = window.HOLIDAY_RADAR_CONFIG || {}, form = document.getElementById('subscription-form');
  const status = document.getElementById('form-status'), error = document.getElementById('error-panel'), success = document.getElementById('confirm-panel');
  const warning = document.getElementById('config-warning'), manageActions = document.getElementById('manage-actions');
  let manageToken = '', busy = false;
  const configured = /^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(cfg.SUPABASE_URL || '') && (cfg.SUPABASE_ANON_KEY || '').length > 20 && !cfg.SUPABASE_ANON_KEY.includes('YOUR-');
  if (!configured) { warning.hidden = false; warning.textContent = 'Poveži Supabase projekt: u README-u su koraci za javni URL i anon ključ.'; }
  const message = (el, text) => { el.textContent = text; el.hidden = false; };
  function setBusy(v) { busy = v; ['submit-button','save-button','unsubscribe-button'].forEach(id => { const b=document.getElementById(id); if(b)b.disabled=v; }); }
  async function api(fn, payload) {
    if (!configured) throw new Error('Aplikacija još nije konfigurirana.');
    const r = await fetch(`${cfg.SUPABASE_URL}/functions/v1/${fn}`, {method:'POST',headers:{'Content-Type':'application/json',apikey:cfg.SUPABASE_ANON_KEY,Authorization:`Bearer ${cfg.SUPABASE_ANON_KEY}`},body:JSON.stringify(payload)});
    let data={}; try {data=await r.json();} catch(_) {}
    if(!r.ok) throw new Error(data.error || 'Zahtjev nije uspio. Pokušaj ponovno.'); return data;
  }
  const csv = s => s.split(',').map(x=>x.trim()).filter(Boolean);
  function getFilters() {
    const d=new FormData(form), ages=csv(String(d.get('children_ages')||'')).map(Number);
    if(ages.some(x=>!Number.isInteger(x)||x<0||x>17)) throw new Error('Dob djece upiši kao cijele brojeve od 0 do 17.');
    const nmin=d.get('nights_min')?Number(d.get('nights_min')):null, nmax=d.get('nights_max')?Number(d.get('nights_max')):null;
    if(nmin&&nmax&&nmin>nmax) throw new Error('Minimalan broj noćenja ne može biti veći od maksimalnog.');
    const from=String(d.get('date_from')||''), to=String(d.get('date_to')||''); if(from&&to&&from>to) throw new Error('Početni datum mora biti prije završnog datuma.');
    return {destinations:csv(String(d.get('destinations')||'')),countries:csv(String(d.get('countries')||'')),origin:String(d.get('origin')||'').trim(),date_from:from||null,date_to:to||null,date_flexible:form.elements.date_flexible.checked,nights_min:nmin,nights_max:nmax,adults:Number(d.get('adults')||2),children_ages:ages,rooms:Number(d.get('rooms')||1),budget:d.get('budget')?Number(d.get('budget')):null,currency:String(d.get('currency')||'EUR'),max_distance_km:d.get('max_distance_km')?Number(d.get('max_distance_km')):null,accommodation:String(d.get('accommodation')||'any'),meal_plan:String(d.get('meal_plan')||'any'),min_rating:Number(d.get('min_rating')||0),min_reviews:d.get('min_reviews')?Number(d.get('min_reviews')):null,free_cancellation:form.elements.free_cancellation.checked,features:csv(String(d.get('features')||'')).slice(0,12),frequency_hours:Number(d.get('frequency_hours')||24)};
  }
  function fill(f) {
    const set=(key,val)=>{if(form.elements[key]&&val!==undefined&&val!==null)form.elements[key].value=val;};
    set('destinations',(f.destinations||[]).join(', '));set('countries',(f.countries||[]).join(', '));set('origin',f.origin||'');set('date_from',f.date_from||'');set('date_to',f.date_to||'');set('nights_min',f.nights_min||'');set('nights_max',f.nights_max||'');set('adults',f.adults||2);set('children_ages',(f.children_ages||[]).join(', '));set('rooms',f.rooms||1);set('budget',f.budget??'');set('currency',f.currency||'EUR');set('max_distance_km',f.max_distance_km??'');set('accommodation',f.accommodation||'any');set('meal_plan',f.meal_plan||'any');set('min_rating',f.min_rating??0);set('min_reviews',f.min_reviews??'');set('features',(f.features||[]).join(', '));set('frequency_hours',f.frequency_hours||24);form.elements.date_flexible.checked=!!f.date_flexible;form.elements.free_cancellation.checked=!!f.free_cancellation;
  }
  function cleanUrl(){history.replaceState(null,'',location.pathname+location.hash);}
  form.addEventListener('submit',async e=>{e.preventDefault();if(busy||manageToken)return;error.hidden=true;status.textContent='';if(!form.reportValidity())return;try{setBusy(true);const filters=getFilters();if(!filters.destinations.length)throw new Error('Upiši barem jedno mjesto ili regiju.');const email=String(new FormData(form).get('email')||'').trim().toLowerCase();await api('subscribe',{email,filters});message(success,'Zahtjev je zaprimljen. Ako je adresa valjana, stići će e-mail za potvrdu. Provjeri i neželjenu poštu.');form.reset();form.elements.adults.value=2;form.elements.rooms.value=1;form.elements.currency.value='EUR';form.elements.frequency_hours.value='24';}catch(ex){message(error,ex.message||'Došlo je do pogreške.');}finally{setBusy(false);}});
  document.getElementById('save-button').addEventListener('click',async()=>{if(!manageToken||busy)return;try{setBusy(true);await api('manage',{action:'update',token:manageToken,filters:getFilters()});message(success,'Postavke su spremljene i primijenit će se pri sljedećoj provjeri.');}catch(ex){message(error,ex.message||'Promjene nisu spremljene.');}finally{setBusy(false);}});
  document.getElementById('unsubscribe-button').addEventListener('click',async()=>{if(!manageToken||busy||!confirm('Želiš li odjaviti ovu e-mail adresu?'))return;try{setBusy(true);await api('manage',{action:'unsubscribe',token:manageToken});message(success,'Obavijesti su isključene.');manageActions.hidden=true;form.querySelectorAll('input,select').forEach(x=>x.disabled=true);}catch(ex){message(error,ex.message||'Odjava nije uspjela.');}finally{setBusy(false);}});
  (async()=>{if(!configured)return;const p=new URLSearchParams(location.search),confirmToken=p.get('confirm'),unsub=p.get('unsubscribe'),token=p.get('manage');try{if(confirmToken){cleanUrl();const r=await api('confirm',{token:confirmToken});message(success,r.message||'E-mail potvrđen.');return;}if(unsub){cleanUrl();await api('manage',{action:'unsubscribe',token:unsub});message(success,'Obavijesti su isključene.');return;}if(token){cleanUrl();manageToken=token;const r=await api('manage',{action:'get',token});fill(r.filters||{});form.elements.email.value=r.email||'';form.elements.email.readOnly=true;document.getElementById('submit-button').hidden=true;manageActions.hidden=false;status.textContent='Uređuješ postojeću pretplatu.';}}catch(ex){cleanUrl();message(error,ex.message||'Poveznica nije valjana ili je istekla.');}})();
})();
