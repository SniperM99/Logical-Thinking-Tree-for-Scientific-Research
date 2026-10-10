import {mountResearchController} from './legacy';
import type {SelectionSnapshot} from './types';
export interface ResearchController {selectSpace(id:string):Promise<void>;selectNode(id:string):Promise<void>;refresh():Promise<void>;newSpace():void;newNode(title?:string):void;dispose():void}
export function mountController(onSelection:(snapshot:SelectionSnapshot)=>void):ResearchController{return mountResearchController(onSelection) as ResearchController}
