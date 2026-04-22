(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[9495],{62898:function(e,t,r){"use strict";r.d(t,{Z:function(){return n}});var a=r(2265),o={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let i=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),n=(e,t)=>{let r=(0,a.forwardRef)(({color:r="currentColor",size:n=24,strokeWidth:s=2,absoluteStrokeWidth:l,children:c,...d},u)=>(0,a.createElement)("svg",{ref:u,...o,width:n,height:n,stroke:r,strokeWidth:l?24*Number(s)/Number(n):s,className:`lucide lucide-${i(e)}`,...d},[...t.map(([e,t])=>(0,a.createElement)(e,t)),...(Array.isArray(c)?c:[c])||[]]));return r.displayName=`${e}`,r}},1295:function(e,t,r){"use strict";r.d(t,{Z:function(){return o}});var a=r(62898);let o=(0,a.Z)("Mail",[["rect",{width:"20",height:"16",x:"2",y:"4",rx:"2",key:"18n3k1"}],["path",{d:"m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7",key:"1ocrg3"}]])},82549:function(e,t,r){"use strict";r.d(t,{Z:function(){return o}});var a=r(62898);let o=(0,a.Z)("X",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]])},91080:function(e,t,r){"use strict";r.d(t,{H:function(){return u},a:function(){return c}});var a=r(57437),o=r(2265),i=r(14958);let n="tt_current_user";function s(){localStorage.removeItem(n)}let l=(0,o.createContext)(null);function c(){let e=(0,o.useContext)(l);if(!e)throw Error("useAuth must be used inside <AuthProvider>");return e}async function d(e){var t;let r=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{};return fetch(e,{credentials:"include",headers:{"Content-Type":"application/json",...null!==(t=r.headers)&&void 0!==t?t:{}},...r})}function u(e){var t;let{children:c}=e,u=null!==(t=function(){let e=localStorage.getItem(n);if(!e)return null;try{return JSON.parse(e)}catch(e){return null}}())&&void 0!==t?t:null,[p,f]=(0,o.useState)(u),[m,h]=(0,o.useState)(!0),[g,b]=(0,o.useState)(!1),y=(0,o.useRef)(!1),x=(0,o.useRef)(null),v=(0,o.useCallback)(async()=>{y.current=!0,x.current&&x.current.abort();let e=new AbortController;x.current=e;try{let t=await fetch("".concat(i.C,"/api/auth/me"),{credentials:"include",headers:{"Content-Type":"application/json"},signal:e.signal});if(t.ok){let e=await t.json();f(e),e&&localStorage.setItem(n,JSON.stringify(e))}else f(null),s();b(!0)}catch(e){(null==e?void 0:e.name)!=="AbortError"&&(console.error("❌ Auth /me error:",e),f(null),s(),b(!0))}finally{x.current===e&&(y.current=!1,h(!1))}},[]);(0,o.useEffect)(()=>(v(),()=>{x.current&&x.current.abort()}),[v]),(0,o.useEffect)(()=>{let e=setInterval(async()=>{try{await d("".concat(i.C,"/api/auth/refresh"),{method:"POST"})}catch(e){}},3e6);return()=>clearInterval(e)},[]);let w=(0,o.useCallback)(async(e,t)=>{try{let a=await d("".concat(i.C,"/api/auth/login"),{method:"POST",body:JSON.stringify({email:e,password:t})});if(!a.ok)return{success:!1,message:"Ongeldige inloggegevens"};return await v(),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.notification()}),{success:!0}}catch(e){return console.error("❌ Login fout:",e),{success:!1,message:"Serverfout"}}},[v]),k=(0,o.useCallback)(async()=>{f(null),s();try{await d("".concat(i.C,"/api/auth/logout"),{method:"POST"}),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.impact()})}catch(e){}},[]);return(0,a.jsx)(l.Provider,{value:{user:p,loading:m,sessionChecked:g,isAuthenticated:!!p,login:w,logout:k,fetchWithAuth:d,reload:v},children:c})}},9323:function(e,t,r){"use strict";r.d(t,{D:function(){return c},d:function(){return l}});var a=r(57437),o=r(2265),i=r(5925),n=r(82549);let s=(0,o.createContext)(null);function l(){let e=(0,o.useContext)(s);if(!e)throw Error("❌ useModal must be used within a ModalProvider");return e}function c(e){let{children:t}=e,[r,n]=(0,o.useState)(null),[l,c]=(0,o.useState)(!1),u=(0,o.useCallback)(()=>{var e;l||(null==r||null===(e=r.onCancel)||void 0===e||e.call(r),n(null))},[r,l]),p=(0,o.useCallback)(e=>{c(!1),n(e)},[]),f=(0,o.useCallback)(function(e){let t=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"success",r={id:e};"success"===t?i.Am.success(e,r):"danger"===t?i.Am.error(e,r):(0,i.Am)(e,r)},[]);return(0,o.useEffect)(()=>{if(!r)return;let e=document.body.style.overflow;document.body.style.overflow="hidden";let t=e=>"Escape"===e.key&&u();return window.addEventListener("keydown",t),()=>{document.body.style.overflow=e,window.removeEventListener("keydown",t)}},[r,u]),(0,a.jsxs)(s.Provider,{value:{openConfirm:p,close:u,showSnackbar:f},children:[t,(0,a.jsx)(d,{modal:r,busy:l,setBusy:c,onClose:u})]})}function d(e){let{modal:t,busy:r,setBusy:o,onClose:i}=e;if(!t)return null;let{title:s="Confirm",description:l,icon:c,tone:d="primary",confirmText:u="Confirm",cancelText:p="Cancel",onConfirm:f}=t,m="danger"===d?{iconBg:"bg-red-100 dark:bg-red-900/40",iconText:"text-red-600 dark:text-red-400",confirm:"bg-red-600 hover:bg-red-700 shadow-red-600/20"}:"info"===d?{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"}:"success"===d?{iconBg:"bg-green-100 dark:bg-green-900/40",iconText:"text-green-600 dark:text-green-400",confirm:"bg-green-600 hover:bg-green-700 shadow-green-600/20"}:{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"},h=async()=>{if(!f){i();return}try{o(!0),await f(),i()}catch(e){console.error("❌ Modal onConfirm error:",e)}finally{o(!1)}};return(0,a.jsx)("div",{className:"fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in",children:(0,a.jsxs)("div",{className:"w-full max-w-md bg-card dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors",children:[(0,a.jsx)("button",{onClick:i,className:"absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10",children:(0,a.jsx)(n.Z,{className:"w-5 h-5"})}),(0,a.jsxs)("div",{className:"px-8 pt-8 pb-6 flex items-center gap-4",children:[c&&(0,a.jsx)("div",{className:"rounded-2xl p-3 ".concat(m.iconBg),children:(0,a.jsx)("div",{className:m.iconText,children:c})}),(0,a.jsx)("h2",{className:"text-2xl font-black text-foreground dark:text-white tracking-tight",children:s})]}),l&&(0,a.jsx)("div",{className:"flex-1 overflow-y-auto px-8 py-2 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed",children:l}),(0,a.jsxs)("div",{className:"px-8 py-8 flex justify-end gap-4 mt-4",children:[(0,a.jsx)("button",{onClick:i,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 disabled:opacity-50",children:p}),(0,a.jsxs)("button",{onClick:h,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest text-white shadow-lg transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 ".concat(m.confirm),children:[r&&(0,a.jsx)("div",{className:"w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full"}),r?"Processing…":u]})]})]})})}},14958:function(e,t,r){"use strict";r.d(t,{C:function(){return a}});let a="https://www.tradamind.com"},24033:function(e,t,r){e.exports=r(68165)},5925:function(e,t,r){"use strict";let a,o;r.d(t,{x7:function(){return eo},Am:function(){return I}});var i,n=r(2265);let s={data:""},l=e=>"object"==typeof window?((e?e.querySelector("#_goober"):window._goober)||Object.assign((e||document.head).appendChild(document.createElement("style")),{innerHTML:" ",id:"_goober"})).firstChild:e||s,c=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,d=/\/\*[^]*?\*\/|  +/g,u=/\n+/g,p=(e,t)=>{let r="",a="",o="";for(let i in e){let n=e[i];"@"==i[0]?"i"==i[1]?r=i+" "+n+";":a+="f"==i[1]?p(n,i):i+"{"+p(n,"k"==i[1]?"":t)+"}":"object"==typeof n?a+=p(n,t?t.replace(/([^,])+/g,e=>i.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+" "+t:t)):i):null!=n&&(i=/^--/.test(i)?i:i.replace(/[A-Z]/g,"-$&").toLowerCase(),o+=p.p?p.p(i,n):i+":"+n+";")}return r+(t&&o?t+"{"+o+"}":o)+a},f={},m=e=>{if("object"==typeof e){let t="";for(let r in e)t+=r+m(e[r]);return t}return e},h=(e,t,r,a,o)=>{var i;let n=m(e),s=f[n]||(f[n]=(e=>{let t=0,r=11;for(;t<e.length;)r=101*r+e.charCodeAt(t++)>>>0;return"go"+r})(n));if(!f[s]){let t=n!==e?e:(e=>{let t,r,a=[{}];for(;t=c.exec(e.replace(d,""));)t[4]?a.shift():t[3]?(r=t[3].replace(u," ").trim(),a.unshift(a[0][r]=a[0][r]||{})):a[0][t[1]]=t[2].replace(u," ").trim();return a[0]})(e);f[s]=p(o?{["@keyframes "+s]:t}:t,r?"":"."+s)}let l=r&&f.g?f.g:null;return r&&(f.g=f[s]),i=f[s],l?t.data=t.data.replace(l,i):-1===t.data.indexOf(i)&&(t.data=a?i+t.data:t.data+i),s},g=(e,t,r)=>e.reduce((e,a,o)=>{let i=t[o];if(i&&i.call){let e=i(r),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;i=t?"."+t:e&&"object"==typeof e?e.props?"":p(e,""):!1===e?"":e}return e+a+(null==i?"":i)},"");function b(e){let t=this||{},r=e.call?e(t.p):e;return h(r.unshift?r.raw?g(r,[].slice.call(arguments,1),t.p):r.reduce((e,r)=>Object.assign(e,r&&r.call?r(t.p):r),{}):r,l(t.target),t.g,t.o,t.k)}b.bind({g:1});let y,x,v,w=b.bind({k:1});function k(e,t){let r=this||{};return function(){let a=arguments;function o(i,n){let s=Object.assign({},i),l=s.className||o.className;r.p=Object.assign({theme:x&&x()},s),r.o=/ *go\d+/.test(l),s.className=b.apply(r,a)+(l?" "+l:""),t&&(s.ref=n);let c=e;return e[0]&&(c=s.as||e,delete s.as),v&&c[0]&&v(s),y(c,s)}return t?t(o):o}}var C=e=>"function"==typeof e,E=(e,t)=>C(e)?e(t):e,j=(a=0,()=>(++a).toString()),N=()=>{if(void 0===o&&"u">typeof window){let e=matchMedia("(prefers-reduced-motion: reduce)");o=!e||e.matches}return o},$=(e,t)=>{switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,20)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return $(e,{type:e.toasts.find(e=>e.id===r.id)?1:0,toast:r});case 3:let{toastId:a}=t;return{...e,toasts:e.toasts.map(e=>e.id===a||void 0===a?{...e,dismissed:!0,visible:!1}:e)};case 4:return void 0===t.toastId?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let o=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+o}))}}},A=[],O={toasts:[],pausedAt:void 0},S=e=>{O=$(O,e),A.forEach(e=>{e(O)})},P={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},T=(e={})=>{let[t,r]=(0,n.useState)(O),a=(0,n.useRef)(O);(0,n.useEffect)(()=>(a.current!==O&&r(O),A.push(r),()=>{let e=A.indexOf(r);e>-1&&A.splice(e,1)}),[]);let o=t.toasts.map(t=>{var r,a,o;return{...e,...e[t.type],...t,removeDelay:t.removeDelay||(null==(r=e[t.type])?void 0:r.removeDelay)||(null==e?void 0:e.removeDelay),duration:t.duration||(null==(a=e[t.type])?void 0:a.duration)||(null==e?void 0:e.duration)||P[t.type],style:{...e.style,...null==(o=e[t.type])?void 0:o.style,...t.style}}});return{...t,toasts:o}},D=(e,t="blank",r)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:"status","aria-live":"polite"},message:e,pauseDuration:0,...r,id:(null==r?void 0:r.id)||j()}),z=e=>(t,r)=>{let a=D(t,e,r);return S({type:2,toast:a}),a.id},I=(e,t)=>z("blank")(e,t);I.error=z("error"),I.success=z("success"),I.loading=z("loading"),I.custom=z("custom"),I.dismiss=e=>{S({type:3,toastId:e})},I.remove=e=>S({type:4,toastId:e}),I.promise=(e,t,r)=>{let a=I.loading(t.loading,{...r,...null==r?void 0:r.loading});return"function"==typeof e&&(e=e()),e.then(e=>{let o=t.success?E(t.success,e):void 0;return o?I.success(o,{id:a,...r,...null==r?void 0:r.success}):I.dismiss(a),e}).catch(e=>{let o=t.error?E(t.error,e):void 0;o?I.error(o,{id:a,...r,...null==r?void 0:r.error}):I.dismiss(a)}),e};var L=(e,t)=>{S({type:1,toast:{id:e,height:t}})},M=()=>{S({type:5,time:Date.now()})},_=new Map,B=1e3,Z=(e,t=B)=>{if(_.has(e))return;let r=setTimeout(()=>{_.delete(e),S({type:4,toastId:e})},t);_.set(e,r)},H=e=>{let{toasts:t,pausedAt:r}=T(e);(0,n.useEffect)(()=>{if(r)return;let e=Date.now(),a=t.map(t=>{if(t.duration===1/0)return;let r=(t.duration||0)+t.pauseDuration-(e-t.createdAt);if(r<0){t.visible&&I.dismiss(t.id);return}return setTimeout(()=>I.dismiss(t.id),r)});return()=>{a.forEach(e=>e&&clearTimeout(e))}},[t,r]);let a=(0,n.useCallback)(()=>{r&&S({type:6,time:Date.now()})},[r]),o=(0,n.useCallback)((e,r)=>{let{reverseOrder:a=!1,gutter:o=8,defaultPosition:i}=r||{},n=t.filter(t=>(t.position||i)===(e.position||i)&&t.height),s=n.findIndex(t=>t.id===e.id),l=n.filter((e,t)=>t<s&&e.visible).length;return n.filter(e=>e.visible).slice(...a?[l+1]:[0,l]).reduce((e,t)=>e+(t.height||0)+o,0)},[t]);return(0,n.useEffect)(()=>{t.forEach(e=>{if(e.dismissed)Z(e.id,e.removeDelay);else{let t=_.get(e.id);t&&(clearTimeout(t),_.delete(e.id))}})},[t]),{toasts:t,handlers:{updateHeight:L,startPause:M,endPause:a,calculateOffset:o}}},F=k("div")`
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
`,R=k("div")`
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
`,J=k("div")`
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
`,U=k("div")`
  position: absolute;
`,W=k("div")`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-width: 20px;
  min-height: 20px;
`,q=k("div")`
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
`,X=({toast:e})=>{let{icon:t,type:r,iconTheme:a}=e;return void 0!==t?"string"==typeof t?n.createElement(q,null,t):t:"blank"===r?null:n.createElement(W,null,n.createElement(R,{...a}),"loading"!==r&&n.createElement(U,null,"error"===r?n.createElement(F,{...a}):n.createElement(J,{...a})))},Y=e=>`
0% {transform: translate3d(0,${-200*e}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,G=e=>`
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
`,V=(e,t)=>{let r=e.includes("top")?1:-1,[a,o]=N()?["0%{opacity:0;} 100%{opacity:1;}","0%{opacity:1;} 100%{opacity:0;}"]:[Y(r),G(r)];return{animation:t?`${w(a)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${w(o)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}},ee=n.memo(({toast:e,position:t,style:r,children:a})=>{let o=e.height?V(e.position||t||"top-center",e.visible):{opacity:0},i=n.createElement(X,{toast:e}),s=n.createElement(Q,{...e.ariaProps},E(e.message,e));return n.createElement(K,{className:e.className,style:{...o,...r,...e.style}},"function"==typeof a?a({icon:i,message:s}):n.createElement(n.Fragment,null,i,s))});i=n.createElement,p.p=void 0,y=i,x=void 0,v=void 0;var et=({id:e,className:t,style:r,onHeightUpdate:a,children:o})=>{let i=n.useCallback(t=>{if(t){let r=()=>{a(e,t.getBoundingClientRect().height)};r(),new MutationObserver(r).observe(t,{subtree:!0,childList:!0,characterData:!0})}},[e,a]);return n.createElement("div",{ref:i,className:t,style:r},o)},er=(e,t)=>{let r=e.includes("top"),a=e.includes("center")?{justifyContent:"center"}:e.includes("right")?{justifyContent:"flex-end"}:{};return{left:0,right:0,display:"flex",position:"absolute",transition:N()?void 0:"all 230ms cubic-bezier(.21,1.02,.73,1)",transform:`translateY(${t*(r?1:-1)}px)`,...r?{top:0}:{bottom:0},...a}},ea=b`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`,eo=({reverseOrder:e,position:t="top-center",toastOptions:r,gutter:a,children:o,containerStyle:i,containerClassName:s})=>{let{toasts:l,handlers:c}=H(r);return n.createElement("div",{id:"_rht_toaster",style:{position:"fixed",zIndex:9999,top:16,left:16,right:16,bottom:16,pointerEvents:"none",...i},className:s,onMouseEnter:c.startPause,onMouseLeave:c.endPause},l.map(r=>{let i=r.position||t,s=er(i,c.calculateOffset(r,{reverseOrder:e,gutter:a,defaultPosition:t}));return n.createElement(et,{id:r.id,key:r.id,onHeightUpdate:c.updateHeight,className:r.visible?ea:"",style:s},"custom"===r.type?E(r.message,r):o?o(r):n.createElement(ee,{toast:r,position:i}))}))}}}]);