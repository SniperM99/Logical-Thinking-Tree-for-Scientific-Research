import type { ResearchState } from './types';
export async function request<T>(path:string,data?:unknown):Promise<T>{
 const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
 const result=await response.json().catch(()=>({error:'服务没有返回有效的 JSON'}));
 if(!response.ok)throw new Error(result.error||result.detail||result.message||`HTTP ${response.status}`);
 return result as T;
}
export const researchApi={state:(spaceId?:string)=>request<ResearchState>('/api/state'+(spaceId?'?space_id='+encodeURIComponent(spaceId):'')),createSpace:(title:string,goal:string)=>request('/api/spaces',{title,goal})};
