(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[3185],{62898:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(2265),o={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let i=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),s=(e,t)=>{let r=(0,a.forwardRef)(({color:r="currentColor",size:s=24,strokeWidth:n=2,absoluteStrokeWidth:l,children:d,...c},u)=>(0,a.createElement)("svg",{ref:u,...o,width:s,height:s,stroke:r,strokeWidth:l?24*Number(n)/Number(s):n,className:`lucide lucide-${i(e)}`,...c},[...t.map(([e,t])=>(0,a.createElement)(e,t)),...(Array.isArray(d)?d:[d])||[]]));return r.displayName=`${e}`,r}},82549:function(e,t,r){"use strict";r.d(t,{Z:function(){return o}});var a=r(62898);let o=(0,a.Z)("X",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]])},58041:function(e,t,r){Promise.resolve().then(r.bind(r,195)),Promise.resolve().then(r.bind(r,79043)),Promise.resolve().then(r.t.bind(r,55610,23))},9323:function(e,t,r){"use strict";r.d(t,{D:function(){return d},d:function(){return l}});var a=r(57437),o=r(2265),i=r(5925),s=r(82549);let n=(0,o.createContext)(null);function l(){let e=(0,o.useContext)(n);if(!e)throw Error("❌ useModal must be used within a ModalProvider");return e}function d(e){let{children:t}=e,[r,s]=(0,o.useState)(null),[l,d]=(0,o.useState)(!1),u=(0,o.useCallback)(()=>{var e;l||(null==r||null===(e=r.onCancel)||void 0===e||e.call(r),s(null))},[r,l]),p=(0,o.useCallback)(e=>{d(!1),s(e)},[]),f=(0,o.useCallback)(function(e){let t=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"success",r={id:e};"success"===t?i.Am.success(e,r):"danger"===t?i.Am.error(e,r):(0,i.Am)(e,r)},[]);return(0,o.useEffect)(()=>{if(!r)return;let e=document.body.style.overflow;document.body.style.overflow="hidden";let t=e=>"Escape"===e.key&&u();return window.addEventListener("keydown",t),()=>{document.body.style.overflow=e,window.removeEventListener("keydown",t)}},[r,u]),(0,a.jsxs)(n.Provider,{value:{openConfirm:p,close:u,showSnackbar:f},children:[t,(0,a.jsx)(c,{modal:r,busy:l,setBusy:d,onClose:u})]})}function c(e){let{modal:t,busy:r,setBusy:o,onClose:i}=e;if(!t)return null;let{title:n="Confirm",description:l,icon:d,tone:c="primary",confirmText:u="Confirm",cancelText:p="Cancel",onConfirm:f}=t,m="danger"===c?{iconBg:"bg-red-100 dark:bg-red-900/40",iconText:"text-red-600 dark:text-red-400",confirm:"bg-red-600 hover:bg-red-700 shadow-red-600/20"}:"info"===c?{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"}:"success"===c?{iconBg:"bg-green-100 dark:bg-green-900/40",iconText:"text-green-600 dark:text-green-400",confirm:"bg-green-600 hover:bg-green-700 shadow-green-600/20"}:{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"},h=async()=>{if(!f){i();return}try{o(!0),await f(),i()}catch(e){console.error("❌ Modal onConfirm error:",e)}finally{o(!1)}};return(0,a.jsx)("div",{className:"fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in",children:(0,a.jsxs)("div",{className:"w-full max-w-md bg-card dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors",children:[(0,a.jsx)("button",{onClick:i,className:"absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10",children:(0,a.jsx)(s.Z,{className:"w-5 h-5"})}),(0,a.jsxs)("div",{className:"px-8 pt-8 pb-6 flex items-center gap-4",children:[d&&(0,a.jsx)("div",{className:"rounded-2xl p-3 ".concat(m.iconBg),children:(0,a.jsx)("div",{className:m.iconText,children:d})}),(0,a.jsx)("h2",{className:"text-2xl font-black text-foreground dark:text-white tracking-tight",children:n})]}),l&&(0,a.jsx)("div",{className:"flex-1 overflow-y-auto px-8 py-2 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed",children:l}),(0,a.jsxs)("div",{className:"px-8 py-8 flex justify-end gap-4 mt-4",children:[(0,a.jsx)("button",{onClick:i,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 disabled:opacity-50",children:p}),(0,a.jsxs)("button",{onClick:h,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest text-white shadow-lg transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 ".concat(m.confirm),children:[r&&(0,a.jsx)("div",{className:"w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full"}),r?"Processing…":u]})]})]})})}},55640:function(e,t,r){"use strict";r.d(t,{Mq:function(){return i}});var a=r(14958);async function o(e){var t;let r=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{},o=null!==(t=null==r?void 0:r.cache)&&void 0!==t?t:"no-store",i=await fetch("".concat(a.C).concat(e),{...r,credentials:"include",cache:o,headers:{"Content-Type":"application/json","Cache-Control":"no-store, no-cache, must-revalidate, proxy-revalidate",Pragma:"no-cache",Expires:"0",...r.headers||{}}});if(!i.ok){let t=await i.text().catch(()=>""),r=Error("API request failed");throw r.status=i.status,r.body=t,r.path=e,console.error("❌ fetchAuth ".concat(e," failed:"),i.status,t),r}let s=i.headers.get("content-type")||"";if(s.includes("application/json"))try{return await i.json()}catch(e){return null}return i}let i=o},14958:function(e,t,r){"use strict";r.d(t,{C:function(){return a}});let a="https://www.tradamind.com"},55610:function(){},30622:function(e,t,r){"use strict";/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var a=r(2265),o=Symbol.for("react.element"),i=Symbol.for("react.fragment"),s=Object.prototype.hasOwnProperty,n=a.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,l={key:!0,ref:!0,__self:!0,__source:!0};function d(e,t,r){var a,i={},d=null,c=null;for(a in void 0!==r&&(d=""+r),void 0!==t.key&&(d=""+t.key),void 0!==t.ref&&(c=t.ref),t)s.call(t,a)&&!l.hasOwnProperty(a)&&(i[a]=t[a]);if(e&&e.defaultProps)for(a in t=e.defaultProps)void 0===i[a]&&(i[a]=t[a]);return{$$typeof:o,type:e,key:d,ref:c,props:i,_owner:n.current}}t.Fragment=i,t.jsx=d,t.jsxs=d},57437:function(e,t,r){"use strict";e.exports=r(30622)},24033:function(e,t,r){e.exports=r(68165)},5925:function(e,t,r){"use strict";let a,o;r.d(t,{x7:function(){return eo},Am:function(){return I}});var i,s=r(2265);let n={data:""},l=e=>"object"==typeof window?((e?e.querySelector("#_goober"):window._goober)||Object.assign((e||document.head).appendChild(document.createElement("style")),{innerHTML:" ",id:"_goober"})).firstChild:e||n,d=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,c=/\/\*[^]*?\*\/|  +/g,u=/\n+/g,p=(e,t)=>{let r="",a="",o="";for(let i in e){let s=e[i];"@"==i[0]?"i"==i[1]?r=i+" "+s+";":a+="f"==i[1]?p(s,i):i+"{"+p(s,"k"==i[1]?"":t)+"}":"object"==typeof s?a+=p(s,t?t.replace(/([^,])+/g,e=>i.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+" "+t:t)):i):null!=s&&(i=/^--/.test(i)?i:i.replace(/[A-Z]/g,"-$&").toLowerCase(),o+=p.p?p.p(i,s):i+":"+s+";")}return r+(t&&o?t+"{"+o+"}":o)+a},f={},m=e=>{if("object"==typeof e){let t="";for(let r in e)t+=r+m(e[r]);return t}return e},h=(e,t,r,a,o)=>{var i;let s=m(e),n=f[s]||(f[s]=(e=>{let t=0,r=11;for(;t<e.length;)r=101*r+e.charCodeAt(t++)>>>0;return"go"+r})(s));if(!f[n]){let t=s!==e?e:(e=>{let t,r,a=[{}];for(;t=d.exec(e.replace(c,""));)t[4]?a.shift():t[3]?(r=t[3].replace(u," ").trim(),a.unshift(a[0][r]=a[0][r]||{})):a[0][t[1]]=t[2].replace(u," ").trim();return a[0]})(e);f[n]=p(o?{["@keyframes "+n]:t}:t,r?"":"."+n)}let l=r&&f.g?f.g:null;return r&&(f.g=f[n]),i=f[n],l?t.data=t.data.replace(l,i):-1===t.data.indexOf(i)&&(t.data=a?i+t.data:t.data+i),n},b=(e,t,r)=>e.reduce((e,a,o)=>{let i=t[o];if(i&&i.call){let e=i(r),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;i=t?"."+t:e&&"object"==typeof e?e.props?"":p(e,""):!1===e?"":e}return e+a+(null==i?"":i)},"");function g(e){let t=this||{},r=e.call?e(t.p):e;return h(r.unshift?r.raw?b(r,[].slice.call(arguments,1),t.p):r.reduce((e,r)=>Object.assign(e,r&&r.call?r(t.p):r),{}):r,l(t.target),t.g,t.o,t.k)}g.bind({g:1});let y,x,v,w=g.bind({k:1});function k(e,t){let r=this||{};return function(){let a=arguments;function o(i,s){let n=Object.assign({},i),l=n.className||o.className;r.p=Object.assign({theme:x&&x()},n),r.o=/ *go\d+/.test(l),n.className=g.apply(r,a)+(l?" "+l:""),t&&(n.ref=s);let d=e;return e[0]&&(d=n.as||e,delete n.as),v&&d[0]&&v(n),y(d,n)}return t?t(o):o}}var E=e=>"function"==typeof e,C=(e,t)=>E(e)?e(t):e,j=(a=0,()=>(++a).toString()),N=()=>{if(void 0===o&&"u">typeof window){let e=matchMedia("(prefers-reduced-motion: reduce)");o=!e||e.matches}return o},_=(e,t)=>{switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,20)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return _(e,{type:e.toasts.find(e=>e.id===r.id)?1:0,toast:r});case 3:let{toastId:a}=t;return{...e,toasts:e.toasts.map(e=>e.id===a||void 0===a?{...e,dismissed:!0,visible:!1}:e)};case 4:return void 0===t.toastId?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let o=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+o}))}}},$=[],O={toasts:[],pausedAt:void 0},P=e=>{O=_(O,e),$.forEach(e=>{e(O)})},A={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},D=(e={})=>{let[t,r]=(0,s.useState)(O),a=(0,s.useRef)(O);(0,s.useEffect)(()=>(a.current!==O&&r(O),$.push(r),()=>{let e=$.indexOf(r);e>-1&&$.splice(e,1)}),[]);let o=t.toasts.map(t=>{var r,a,o;return{...e,...e[t.type],...t,removeDelay:t.removeDelay||(null==(r=e[t.type])?void 0:r.removeDelay)||(null==e?void 0:e.removeDelay),duration:t.duration||(null==(a=e[t.type])?void 0:a.duration)||(null==e?void 0:e.duration)||A[t.type],style:{...e.style,...null==(o=e[t.type])?void 0:o.style,...t.style}}});return{...t,toasts:o}},T=(e,t="blank",r)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:"status","aria-live":"polite"},message:e,pauseDuration:0,...r,id:(null==r?void 0:r.id)||j()}),z=e=>(t,r)=>{let a=T(t,e,r);return P({type:2,toast:a}),a.id},I=(e,t)=>z("blank")(e,t);I.error=z("error"),I.success=z("success"),I.loading=z("loading"),I.custom=z("custom"),I.dismiss=e=>{P({type:3,toastId:e})},I.remove=e=>P({type:4,toastId:e}),I.promise=(e,t,r)=>{let a=I.loading(t.loading,{...r,...null==r?void 0:r.loading});return"function"==typeof e&&(e=e()),e.then(e=>{let o=t.success?C(t.success,e):void 0;return o?I.success(o,{id:a,...r,...null==r?void 0:r.success}):I.dismiss(a),e}).catch(e=>{let o=t.error?C(t.error,e):void 0;o?I.error(o,{id:a,...r,...null==r?void 0:r.error}):I.dismiss(a)}),e};var L=(e,t)=>{P({type:1,toast:{id:e,height:t}})},S=()=>{P({type:5,time:Date.now()})},M=new Map,B=1e3,R=(e,t=B)=>{if(M.has(e))return;let r=setTimeout(()=>{M.delete(e),P({type:4,toastId:e})},t);M.set(e,r)},F=e=>{let{toasts:t,pausedAt:r}=D(e);(0,s.useEffect)(()=>{if(r)return;let e=Date.now(),a=t.map(t=>{if(t.duration===1/0)return;let r=(t.duration||0)+t.pauseDuration-(e-t.createdAt);if(r<0){t.visible&&I.dismiss(t.id);return}return setTimeout(()=>I.dismiss(t.id),r)});return()=>{a.forEach(e=>e&&clearTimeout(e))}},[t,r]);let a=(0,s.useCallback)(()=>{r&&P({type:6,time:Date.now()})},[r]),o=(0,s.useCallback)((e,r)=>{let{reverseOrder:a=!1,gutter:o=8,defaultPosition:i}=r||{},s=t.filter(t=>(t.position||i)===(e.position||i)&&t.height),n=s.findIndex(t=>t.id===e.id),l=s.filter((e,t)=>t<n&&e.visible).length;return s.filter(e=>e.visible).slice(...a?[l+1]:[0,l]).reduce((e,t)=>e+(t.height||0)+o,0)},[t]);return(0,s.useEffect)(()=>{t.forEach(e=>{if(e.dismissed)R(e.id,e.removeDelay);else{let t=M.get(e.id);t&&(clearTimeout(t),M.delete(e.id))}})},[t]),{toasts:t,handlers:{updateHeight:L,startPause:S,endPause:a,calculateOffset:o}}},Z=k("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||"#ff4b4b"};
  position: relative;
  transform: rotate(45deg);

  animation: ${w`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
 transform: scale(1) rotate(45deg);
  opacity: 1;
}`} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;

  &:after,
  &:before {
    content: '';
    animation: ${w`
from {
  transform: scale(0);
  opacity: 0;
}
to {
  transform: scale(1);
  opacity: 1;
}`} 0.15s ease-out forwards;
    animation-delay: 150ms;
    position: absolute;
    border-radius: 3px;
    opacity: 0;
    background: ${e=>e.secondary||"#fff"};
    bottom: 9px;
    left: 4px;
    height: 2px;
    width: 12px;
  }

  &:before {
    animation: ${w`
from {
  transform: scale(0) rotate(90deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(90deg);
	opacity: 1;
}`} 0.15s ease-out forwards;
    animation-delay: 180ms;
    transform: rotate(90deg);
  }
`,H=k("div")`
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border: 2px solid;
  border-radius: 100%;
  border-color: ${e=>e.secondary||"#e0e0e0"};
  border-right-color: ${e=>e.primary||"#616161"};
  animation: ${w`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
`} 1s linear infinite;
`,U=k("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||"#61d345"};
  position: relative;
  transform: rotate(45deg);

  animation: ${w`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(45deg);
	opacity: 1;
}`} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;
  &:after {
    content: '';
    box-sizing: border-box;
    animation: ${w`
0% {
	height: 0;
	width: 0;
	opacity: 0;
}
40% {
  height: 0;
	width: 6px;
	opacity: 1;
}
100% {
  opacity: 1;
  height: 10px;
}`} 0.2s ease-out forwards;
    opacity: 0;
    animation-delay: 200ms;
    position: absolute;
    border-right: 2px solid;
    border-bottom: 2px solid;
    border-color: ${e=>e.secondary||"#fff"};
    bottom: 6px;
    left: 6px;
    height: 10px;
    width: 6px;
  }
`,q=k("div")`
  position: absolute;
`,W=k("div")`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-width: 20px;
  min-height: 20px;
`,Y=k("div")`
  position: relative;
  transform: scale(0.6);
  opacity: 0.4;
  min-width: 20px;
  animation: ${w`
from {
  transform: scale(0.6);
  opacity: 0.4;
}
to {
  transform: scale(1);
  opacity: 1;
}`} 0.3s 0.12s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
`,X=({toast:e})=>{let{icon:t,type:r,iconTheme:a}=e;return void 0!==t?"string"==typeof t?s.createElement(Y,null,t):t:"blank"===r?null:s.createElement(W,null,s.createElement(H,{...a}),"loading"!==r&&s.createElement(q,null,"error"===r?s.createElement(Z,{...a}):s.createElement(U,{...a})))},G=e=>`
0% {transform: translate3d(0,${-200*e}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,J=e=>`
0% {transform: translate3d(0,0,-1px) scale(1); opacity:1;}
100% {transform: translate3d(0,${-150*e}%,-1px) scale(.6); opacity:0;}
`,K=k("div")`
  display: flex;
  align-items: center;
  background: #fff;
  color: #363636;
  line-height: 1.3;
  will-change: transform;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1), 0 3px 3px rgba(0, 0, 0, 0.05);
  max-width: 350px;
  pointer-events: auto;
  padding: 8px 10px;
  border-radius: 8px;
`,Q=k("div")`
  display: flex;
  justify-content: center;
  margin: 4px 10px;
  color: inherit;
  flex: 1 1 auto;
  white-space: pre-line;
`,V=(e,t)=>{let r=e.includes("top")?1:-1,[a,o]=N()?["0%{opacity:0;} 100%{opacity:1;}","0%{opacity:1;} 100%{opacity:0;}"]:[G(r),J(r)];return{animation:t?`${w(a)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${w(o)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}},ee=s.memo(({toast:e,position:t,style:r,children:a})=>{let o=e.height?V(e.position||t||"top-center",e.visible):{opacity:0},i=s.createElement(X,{toast:e}),n=s.createElement(Q,{...e.ariaProps},C(e.message,e));return s.createElement(K,{className:e.className,style:{...o,...r,...e.style}},"function"==typeof a?a({icon:i,message:n}):s.createElement(s.Fragment,null,i,n))});i=s.createElement,p.p=void 0,y=i,x=void 0,v=void 0;var et=({id:e,className:t,style:r,onHeightUpdate:a,children:o})=>{let i=s.useCallback(t=>{if(t){let r=()=>{a(e,t.getBoundingClientRect().height)};r(),new MutationObserver(r).observe(t,{subtree:!0,childList:!0,characterData:!0})}},[e,a]);return s.createElement("div",{ref:i,className:t,style:r},o)},er=(e,t)=>{let r=e.includes("top"),a=e.includes("center")?{justifyContent:"center"}:e.includes("right")?{justifyContent:"flex-end"}:{};return{left:0,right:0,display:"flex",position:"absolute",transition:N()?void 0:"all 230ms cubic-bezier(.21,1.02,.73,1)",transform:`translateY(${t*(r?1:-1)}px)`,...r?{top:0}:{bottom:0},...a}},ea=g`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`,eo=({reverseOrder:e,position:t="top-center",toastOptions:r,gutter:a,children:o,containerStyle:i,containerClassName:n})=>{let{toasts:l,handlers:d}=F(r);return s.createElement("div",{id:"_rht_toaster",style:{position:"fixed",zIndex:9999,top:16,left:16,right:16,bottom:16,pointerEvents:"none",...i},className:n,onMouseEnter:d.startPause,onMouseLeave:d.endPause},l.map(r=>{let i=r.position||t,n=er(i,d.calculateOffset(r,{reverseOrder:e,gutter:a,defaultPosition:t}));return s.createElement(et,{id:r.id,key:r.id,onHeightUpdate:d.updateHeight,className:r.visible?ea:"",style:n},"custom"===r.type?C(r.message,r):o?o(r):s.createElement(ee,{toast:r,position:i}))}))}}},function(e){e.O(0,[916,2971,596,1744],function(){return e(e.s=58041)}),_N_E=e.O()}]);