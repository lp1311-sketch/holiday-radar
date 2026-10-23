import { corsHeaders, dbFetch, reply, sha256, validateFilters } from "../_shared/common.ts";
Deno.serve(async(req:Request)=>{
  if(req.method==="OPTIONS")return new Response("ok",{headers:corsHeaders});
  if(req.method!=="POST")return reply(405,{error:"Metoda nije dopuštena."});
  try{
    const body=await req.json(), token=String(body?.token||""), action=String(body?.action||"");
    if(token.length<32||token.length>200)return reply(400,{error:"Privatna poveznica nije valjana ili je istekla."});
    const q=new URLSearchParams({select:"id,email,filters",status:"eq.active",manage_token_hash:`eq.${await sha256(token)}`});
    const r=await dbFetch(`subscriptions?${q}`);if(!r.ok)throw new Error("Lookup failed");const rows=await r.json();
    if(!rows.length)return reply(400,{error:"Privatna poveznica nije valjana ili je istekla."});const row=rows[0];
    if(action==="get")return reply(200,{ok:true,email:row.email,filters:row.filters});
    if(action==="update"){
      const filters=validateFilters(body?.filters),u=await dbFetch(`subscriptions?id=eq.${encodeURIComponent(row.id)}`,{method:"PATCH",headers:{Prefer:"return=minimal"},body:JSON.stringify({filters,last_scanned_at:null,updated_at:new Date().toISOString()})});
      if(!u.ok)throw new Error("Update failed");return reply(200,{ok:true});
    }
    if(action==="unsubscribe"){
      const u=await dbFetch(`subscriptions?id=eq.${encodeURIComponent(row.id)}`,{method:"DELETE",headers:{Prefer:"return=minimal"}});
      if(!u.ok)throw new Error("Unsubscribe failed");return reply(200,{ok:true});
    }
    return reply(400,{error:"Nepoznata radnja."});
  }catch(err){
    console.error("manage failed",err instanceof Error?err.message:"unknown");
    const msg=err instanceof Error&&/kriterij|mjesto|raspon|datum|brojčan|valjan|podržan|djece/i.test(err.message)?err.message:"Postavke nije moguće obraditi. Pokušaj ponovno kasnije.";
    return reply(400,{error:msg});
  }
});
