export const base = import.meta.env.VITE_API_BASE_URL || '';
export function token(){return sessionStorage.getItem('cloudwise-token')}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch(base+'/api/v1'+path,{method,headers:{'Content-Type':'application/json',...(token()?{Authorization:'Bearer '+token()}: {})},body:body===undefined?undefined:JSON.stringify(body)});
  let data:any;try{data=await response.json()}catch{throw new Error('The server returned an unreadable response.')}
  if(!response.ok){if(response.status===401 && path!='/auth/login'){sessionStorage.removeItem('cloudwise-token');window.dispatchEvent(new Event('auth-expired'))}throw new Error(data.error?.message||'Request failed')}
  return data;
}
export type Rec={id:string;resource_id:string|null;finding_type:string;title:string;explanation:string;evidence:string[];proposed_action:string;risk_level:string;estimated_monthly_savings:string|null;currency:string;savings_assumptions:string[];status:string;created_at:string;explanation_source:string;data_source:string};
export const money=(value:string|number|null,currency='USD')=>value===null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency,maximumFractionDigits:2}).format(Number(value));
export const date=(value:string|null)=>value?new Date(value).toLocaleString():'Not yet';
