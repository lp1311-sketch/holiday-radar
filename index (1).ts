import { corsHeaders, dbFetch, reply, sha256, validateFilters } from "../_shared/common.ts";
Deno.serve(async (req: Request) => {
  if(req.method==="OPTIONS") return new Response("ok",{headers:corsHeaders});
  if(req.method!=="POST") return reply(405,{error:"Metoda nije dopuštena."});
  try {
    const body=await req.json(), email=String(body?.email||"").trim().toLowerCase();
    if(email.length>254||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return reply(400,{error:"Upiši valjanu e-mail adresu."});
    const filters=validateFilters(body?.filters);
    const ip=(req.headers.get("x-forwarded-for")||req.headers.get("cf-connecting-ip")||"").split(",")[0].trim(), salt=Deno.env.get("RATE_LIMIT_SECRET");
    if(!ip||!salt) return reply(503,{error:"Zaštita prijave trenutno nije dostupna. Pokušaj ponovno kasnije."});
    {
      const rate=await dbFetch("rpc/consume_signup_rate_limit",{method:"POST",body:JSON.stringify({p_ip_hash:await sha256(`${salt}:${ip}`)})});
      if(!rate.ok) throw new Error("Rate limit unavailable");
      if(await rate.json()!==true) return reply(429,{error:"Previše pokušaja s ove mreže. Pokušaj ponovno za nekoliko minuta."});
    }
    const q=new URLSearchParams({select:"id,status",email:`eq.${email}`});
    const lookup=await dbFetch(`subscriptions?${q}`); if(!lookup.ok) throw new Error("Lookup failed");
    const rows=await lookup.json();
    if(rows.length){
      if(rows[0].status!=="active"){
        const patch=await dbFetch(`subscriptions?id=eq.${encodeURIComponent(rows[0].id)}`,{method:"PATCH",headers:{Prefer:"return=minimal"},body:JSON.stringify({status:"pending",filters,confirm_token_hash:null,manage_token_hash:null,confirmation_sent_at:null,updated_at:new Date().toISOString()})});
        if(!patch.ok) throw new Error("Update failed");
      }
    }else{
      const insert=await dbFetch("subscriptions",{method:"POST",headers:{Prefer:"return=minimal"},body:JSON.stringify({email,filters,status:"pending"})});
      if(!insert.ok) throw new Error("Insert failed");
    }
    return reply(200,{ok:true,message:"Zahtjev je zaprimljen."});
  }catch(err){
    console.error("subscribe failed",err instanceof Error?err.message:"unknown");
    const msg=err instanceof Error&&/kriterij|mjesto|raspon|datum|brojčan|valjan|podržan|djece/i.test(err.message)?err.message:"Zahtjev nije moguće obraditi. Provjeri podatke i pokušaj ponovno.";
    return reply(400,{error:msg});
  }
});
