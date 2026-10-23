import { corsHeaders, dbFetch, reply, sha256 } from "../_shared/common.ts";
Deno.serve(async(req:Request)=>{
  if(req.method==="OPTIONS")return new Response("ok",{headers:corsHeaders});
  if(req.method!=="POST")return reply(405,{error:"Metoda nije dopuštena."});
  try{
    const body=await req.json(), token=String(body?.token||"");
    if(token.length<32||token.length>200)return reply(400,{error:"Poveznica nije valjana ili je istekla."});
    const q=new URLSearchParams({select:"id",status:"eq.pending",confirm_token_hash:`eq.${await sha256(token)}`});
    const r=await dbFetch(`subscriptions?${q}`,{method:"PATCH",headers:{Prefer:"return=representation"},body:JSON.stringify({status:"active",verified_at:new Date().toISOString(),confirm_token_hash:null,confirmation_sent_at:null,updated_at:new Date().toISOString()})});
    if(!r.ok)throw new Error("Update failed"); if(!(await r.json()).length)return reply(400,{error:"Poveznica nije valjana ili je istekla."});
    return reply(200,{ok:true,message:"E-mail je potvrđen. Holiday Radar je aktivan."});
  }catch(err){console.error("confirm failed",err instanceof Error?err.message:"unknown");return reply(500,{error:"Potvrda trenutno nije dostupna. Pokušaj ponovno kasnije."});}
});
