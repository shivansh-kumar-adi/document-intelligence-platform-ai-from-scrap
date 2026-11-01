const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export type DocumentItem={id:string;filename:string;status:string;page_count:number;chunk_count:number;uploaded_at:string;error?:string};
export type Collection={id:string;name:string;description:string};
export type Passage={chunk_id:string;document_id:string;document_name:string;page_number:number|null;excerpt:string;score:number;methods:string[]};
export type ChatResponse={answer:string;provider:string;grounded:boolean;insufficient_evidence:boolean;citations:Passage[];conversation_id:string};
export type Evaluation={cases:number;top_k:number;recall_at_k:number;precision_at_k:number;mrr:number;mean_retrieval_latency_ms:number;measured:boolean};

async function request<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch(BASE+path,init);
  if(!response.ok){const body=await response.json().catch(()=>({detail:`Request failed (${response.status})`}));throw new Error(body.detail||`Request failed (${response.status})`)}
  if(response.status===204)return undefined as T;
  return response.json();
}
export const api={
  dashboard:()=>request<{documents:number;indexed:number;processing:number;collections:number}>('/dashboard'),
  documents:()=>request<DocumentItem[]>('/documents'), collections:()=>request<Collection[]>('/collections'),
  createCollection:(name:string)=>request<Collection>('/collections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:''})}),
  upload:(file:File,collections:string[])=>{const body=new FormData();body.append('file',file);body.append('collection_ids',collections.join(','));return request<DocumentItem>('/documents',{method:'POST',body})},
  remove:(id:string)=>request<void>(`/documents/${id}`,{method:'DELETE'}),
  search:(query:string,collection_ids:string[]=[])=>request<Passage[]>('/retrieval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,collection_ids,top_k:8})}),
  chat:(query:string,collection_ids:string[]=[],conversation_id?:string)=>request<ChatResponse>('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,collection_ids,top_k:6,conversation_id})}),
  evaluate:(question:string,expected_document_ids:string[])=>request<Evaluation>('/evaluation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({top_k:5,cases:[{question,expected_document_ids}]})})
};
