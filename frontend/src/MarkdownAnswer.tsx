import {useState, type ComponentPropsWithoutRef} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function CodeBlock({children, ...props}:ComponentPropsWithoutRef<'pre'>){
 const [copied,setCopied]=useState(false);
 async function copy(element:HTMLButtonElement){
  const code=element.closest('.markdown-code-block')?.querySelector('code')?.textContent;
  if(!code)return;
  try{await navigator.clipboard.writeText(code);setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{setCopied(false)}
 }
 return <div className="markdown-code-block"><div className="markdown-code-toolbar"><span>代码</span><button type="button" onClick={event=>void copy(event.currentTarget)} aria-label="复制代码">{copied?'已复制':'复制'}</button></div><pre {...props}>{children}</pre></div>;
}

export default function MarkdownAnswer({text}:{text:string}){
 return <div className="chat-answer markdown-answer"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
  pre:({node: _node,...props})=><CodeBlock {...props}/>,
  table:({node: _node,...props})=><div className="markdown-table-scroll" tabIndex={0} role="region" aria-label="回答中的表格"><table {...props}/></div>,
  a:({node: _node,...props})=><a {...props} target="_blank" rel="noopener noreferrer"/>
 }}>{text}</ReactMarkdown></div>;
}
