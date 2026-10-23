export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json; charset=utf-8",
};
export function reply(status: number, payload: Record<string, unknown>) {
  return new Response(JSON.stringify(payload), { status, headers: corsHeaders });
}
export function serviceHeaders(extra: Record<string, string> = {}) {
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!key) throw new Error("Missing service key");
  return { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", ...extra };
}
export async function dbFetch(path: string, init: RequestInit = {}) {
  const base = Deno.env.get("SUPABASE_URL");
  if (!base) throw new Error("Missing Supabase URL");
  return fetch(`${base.replace(/\/$/, "")}/rest/v1/${path}`, {
    ...init,
    headers: { ...serviceHeaders(), ...(init.headers as Record<string, string> || {}) },
  });
}
export async function sha256(value: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes)).map(x => x.toString(16).padStart(2, "0")).join("");
}
const allowedAccommodation = new Set(["any", "hotel", "apartment", "camping", "resort", "holiday_home"]);
const allowedMeal = new Set(["any", "breakfast", "half_board", "full_board", "all_inclusive", "self_catering"]);
const allowedCurrency = new Set(["EUR", "USD", "GBP", "CHF", "CAD", "AUD"]);
const shortText = (v: unknown, max: number) => typeof v === "string" ? v.trim().slice(0, max) : "";
const optionalNumber = (v: unknown, min: number, max: number) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= min && n <= max ? n : NaN;
};
const cleanList = (v: unknown, count: number, length: number) => Array.isArray(v) ? v.slice(0,count).map(x=>shortText(x,length)).filter(Boolean) : [];
export function validateFilters(input: unknown) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Neispravni kriteriji.");
  const f = input as Record<string, unknown>;
  const destinations=cleanList(f.destinations,8,80), countries=cleanList(f.countries,12,60);
  if (!destinations.length) throw new Error("Upiši barem jedno mjesto ili regiju.");
  const adults=optionalNumber(f.adults??2,1,20), rooms=optionalNumber(f.rooms??1,1,10);
  const nightsMin=optionalNumber(f.nights_min,1,90), nightsMax=optionalNumber(f.nights_max,1,90);
  const budget=optionalNumber(f.budget,0,10000000), distance=optionalNumber(f.max_distance_km,1,20000);
  const rating=optionalNumber(f.min_rating??0,0,10), reviews=optionalNumber(f.min_reviews,0,10000000);
  const frequency=optionalNumber(f.frequency_hours??24,6,24);
  for(const n of [adults,rooms,nightsMin,nightsMax,budget,distance,rating,reviews,frequency]) if(Number.isNaN(n)) throw new Error("Jedan od brojčanih kriterija nije valjan.");
  if(nightsMin!==null&&nightsMax!==null&&nightsMin>nightsMax) throw new Error("Raspon noćenja nije valjan.");
  const dateFrom=shortText(f.date_from,10)||null, dateTo=shortText(f.date_to,10)||null, datePattern=/^\d{4}-\d{2}-\d{2}$/;
  if((dateFrom&&!datePattern.test(dateFrom))||(dateTo&&!datePattern.test(dateTo))) throw new Error("Datum nije valjan.");
  if(dateFrom&&dateTo&&dateFrom>dateTo) throw new Error("Raspon datuma nije valjan.");
  const childInput=Array.isArray(f.children_ages)?f.children_ages.slice(0,12):[];
  const children=childInput.map(x=>Number(x));
  if(children.some(x=>!Number.isInteger(x)||x<0||x>17)) throw new Error("Dob djece nije valjana.");
  const accommodation=shortText(f.accommodation,24)||"any", meal=shortText(f.meal_plan,24)||"any", currency=shortText(f.currency,3).toUpperCase()||"EUR";
  if(!allowedAccommodation.has(accommodation)||!allowedMeal.has(meal)||!allowedCurrency.has(currency)) throw new Error("Odabrana vrijednost nije podržana.");
  return {destinations,countries,origin:shortText(f.origin,120),date_from:dateFrom,date_to:dateTo,date_flexible:Boolean(f.date_flexible),nights_min:nightsMin,nights_max:nightsMax,adults:adults??2,children_ages:children,rooms:rooms??1,budget,currency,max_distance_km:distance,accommodation,meal_plan:meal,min_rating:rating??0,min_reviews:reviews,free_cancellation:Boolean(f.free_cancellation),features:cleanList(f.features,12,50),frequency_hours:frequency??24};
}
