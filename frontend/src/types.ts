export type NodeKind = 'thought' | 'action';
export interface Space {id:string;title:string;root_id:string;goal?:string}
export interface ResearchNode {id:string;space_id:string;parent_id:string|null;sources:string[];title:string;kind:NodeKind;summary:string;reason:string;version:number;frozen:boolean;hidden:boolean;archived:boolean;created_at:string}
export interface Conversation {id:string;anchor_id:string;title:string;space_id:string;origin_scope?:'space'|'node'}
export interface QA {assignment_status?:string;assignment_reason?:string;primary_node_id?:string;primary_node_title?:string;id:string;conversation_id:string;title:string;question:string;answer:string;user_message_id:string;answer_message_id:string;created_at:string}
export interface Proposal {id:string;node_id:string;operation:string;status:string;reason:string;sources?:string[];preview:Record<string,unknown>}
export interface Run {id:string;node_id:string;status:string;device:string;parameters:Record<string,unknown>;execution_mode:string}
export interface Provider {configured:boolean;model:string;base_url:string;growth_mode:string;remote_execution:string}
export interface ResearchState {spaces:Space[];nodes:ResearchNode[];conversations:Conversation[];qas:QA[];proposals:Proposal[];runs:Run[];provider:Provider;metrics:Record<string,number>;[key:string]:unknown}
export interface SelectionSnapshot {spaceId:string|null;nodeId:string|null;state:ResearchState}
