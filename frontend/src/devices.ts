import {request} from './api';
export interface ResearchDevice {id:string;name:string;workspace:string;last_seen:string;created_at:string}
export interface DispatchSpec {device_id:string;argv:string[];cwd:string;timeout_seconds:number}
export interface DeviceJob {id:string;run_id:string;device_id:string;argv:string[];cwd:string;timeout_seconds:number;status:string;created_at:string}
export const deviceApi={list:()=>request<ResearchDevice[]>('/api/devices'),dispatch:(runId:string,spec:DispatchSpec)=>request<DeviceJob>('/api/runs/'+encodeURIComponent(runId)+'/dispatch',spec)};
export function deviceHeartbeatLabel(lastSeen:string):string{const timestamp=Date.parse(lastSeen);if(!Number.isFinite(timestamp))return '心跳状态未知';return Date.now()-timestamp<=90000?'近期在线（90 秒内心跳）':'心跳过期 / 可能离线'}
export function validateDispatch(spec:DispatchSpec):DispatchSpec{if(!spec.device_id)throw Error('请选择真实执行设备');if(!Array.isArray(spec.argv)||!spec.argv.length||spec.argv.some(item=>typeof item!=='string'||!item.length))throw Error('命令必须是非空字符串数组，例如 ["python3", "experiment.py"]');if(spec.cwd.startsWith('/')||spec.cwd.split(/[\\/]/).includes('..'))throw Error('执行目录必须为设备工作区内的相对路径');if(!Number.isInteger(spec.timeout_seconds)||spec.timeout_seconds<1||spec.timeout_seconds>86400)throw Error('超时必须为 1～86400 秒的整数');return spec}
