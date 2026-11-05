export interface Product {id:string;name:string;price:number;currency:string;processor_brand:string;processor:string;ram_gb:number;storage_gb:number;weight_kg:number;battery_hours:number;seller:string;source_type:string;timestamp:string;available:boolean}
export interface Recommendation {product:Product;score:number;breakdown:Record<string,number>;tradeoffs:string[];explanation:string}
export interface Analysis {id:string;status:string;intent:{max_budget:number;missing_essential_details:string[]};recommendations?:Recommendation[];steps:string[]}
export interface Order {id:string;product_id:string;amount:number;currency:string;status:string;payment?:Payment|null}
export interface Payment {id:string;order_id:string;amount:number;status:string}
export interface AuditEvent {id:string;event:string;created_at:string}
const base=process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export async function api<T>(path:string, body?:unknown):Promise<T> {
 const response=await fetch(base+path,{method:body===undefined?"GET":"POST",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>({detail:"Backend unavailable"}));throw new Error(typeof error.detail==="string"?error.detail:JSON.stringify(error.detail));}
 return response.json();
}
export const money=(value:number)=>new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:0}).format(value);
