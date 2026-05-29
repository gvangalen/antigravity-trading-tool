(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[6697],{62898:function(e,t,r){"use strict";r.d(t,{Z:function(){return o}});var i=r(2265),a={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let s=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),o=(e,t)=>{let r=(0,i.forwardRef)(({color:r="currentColor",size:o=24,strokeWidth:n=2,absoluteStrokeWidth:l,children:c,...d},u)=>(0,i.createElement)("svg",{ref:u,...a,width:o,height:o,stroke:r,strokeWidth:l?24*Number(n)/Number(o):n,className:`lucide lucide-${s(e)}`,...d},[...t.map(([e,t])=>(0,i.createElement)(e,t)),...(Array.isArray(c)?c:[c])||[]]));return r.displayName=`${e}`,r}},20173:function(e,t,r){"use strict";r.d(t,{Z:function(){return a}});var i=r(62898);let a=(0,i.Z)("CheckCircle2",[["path",{d:"M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z",key:"14v8dr"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]])},82549:function(e,t,r){"use strict";r.d(t,{Z:function(){return a}});var i=r(62898);let a=(0,i.Z)("X",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]])},62601:function(e,t,r){"use strict";var i,a;e.exports=(null==(i=r.g.process)?void 0:i.env)&&"object"==typeof(null==(a=r.g.process)?void 0:a.env)?r.g.process:r(58960)},6481:function(e,t,r){Promise.resolve().then(r.bind(r,65874))},65874:function(e,t,r){"use strict";r.r(t),r.d(t,{default:function(){return d}});var i=r(57437),a=r(2265),s=r(86858),o=r(43349),n=r(61396),l=r.n(n),c=r(64411);function d(e){let{children:t}=e,[r,n]=(0,a.useState)(!1);return(0,i.jsxs)(i.Fragment,{children:[(0,i.jsxs)("div",{className:"min-h-screen bg-[#020617] text-slate-100 transition-all duration-300 relative overflow-hidden",style:{paddingRight:r?window.innerWidth<1024?"0px":"400px":"0px"},children:[(0,i.jsx)("div",{className:"absolute inset-0 pointer-events-none opacity-20",style:{backgroundImage:"radial-gradient(circle at 2px 2px, rgba(255,255,255,0.05) 1px, transparent 0)",backgroundSize:"40px 40px"}}),(0,i.jsx)("div",{className:"absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-96 bg-blue-600/10 blur-[120px] rounded-full pointer-events-none"}),(0,i.jsxs)("header",{className:"fixed top-0 left-0 right-0 z-50 h-16 border-b border-slate-800 bg-[#020617]/80 backdrop-blur-md flex items-center justify-between px-8",children:[(0,i.jsx)("div",{className:"flex items-center gap-4",children:(0,i.jsxs)(l(),{href:"/onboarding",className:"flex items-center gap-3 group transition-all",children:[(0,i.jsx)("div",{className:"p-2 bg-blue-600 rounded-xl shadow-lg shadow-blue-600/20 group-hover:scale-110 transition-transform",children:(0,i.jsx)(c.Z,{className:"w-5 h-5 text-white"})}),(0,i.jsxs)("div",{children:[(0,i.jsx)("h1",{className:"text-sm font-black uppercase tracking-[0.2em] leading-none mb-1",children:"Launch Protocol"}),(0,i.jsx)("span",{className:"text-[10px] font-bold text-slate-500 uppercase tracking-widest leading-none",children:"V1.1.0 Initializing"})]})]})}),(0,i.jsx)("div",{className:"flex items-center gap-6",children:(0,i.jsxs)("div",{className:"hidden md:flex items-center gap-2 px-4 py-1.5 bg-slate-900 border border-slate-800 rounded-full",children:[(0,i.jsx)("div",{className:"w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"}),(0,i.jsx)("span",{className:"text-[10px] font-bold text-slate-400 uppercase tracking-widest",children:"Assistant Online"})]})})]}),(0,i.jsx)("main",{className:"pt-24 pb-12 min-h-screen relative z-10 px-6 max-w-6xl mx-auto",children:t})]}),(0,i.jsx)(s.Z,{isOpen:r,setIsOpen:n}),!r&&(0,i.jsx)(o.Z,{isOpen:r,onClick:()=>n(!0)})]})}},58960:function(e){!function(){var t={229:function(e){var t,r,i,a=e.exports={};function s(){throw Error("setTimeout has not been defined")}function o(){throw Error("clearTimeout has not been defined")}function n(e){if(t===setTimeout)return setTimeout(e,0);if((t===s||!t)&&setTimeout)return t=setTimeout,setTimeout(e,0);try{return t(e,0)}catch(r){try{return t.call(null,e,0)}catch(r){return t.call(this,e,0)}}}!function(){try{t="function"==typeof setTimeout?setTimeout:s}catch(e){t=s}try{r="function"==typeof clearTimeout?clearTimeout:o}catch(e){r=o}}();var l=[],c=!1,d=-1;function u(){c&&i&&(c=!1,i.length?l=i.concat(l):d=-1,l.length&&p())}function p(){if(!c){var e=n(u);c=!0;for(var t=l.length;t;){for(i=l,l=[];++d<t;)i&&i[d].run();d=-1,t=l.length}i=null,c=!1,function(e){if(r===clearTimeout)return clearTimeout(e);if((r===o||!r)&&clearTimeout)return r=clearTimeout,clearTimeout(e);try{r(e)}catch(t){try{return r.call(null,e)}catch(t){return r.call(this,e)}}}(e)}}function f(e,t){this.fun=e,this.array=t}function m(){}a.nextTick=function(e){var t=Array(arguments.length-1);if(arguments.length>1)for(var r=1;r<arguments.length;r++)t[r-1]=arguments[r];l.push(new f(e,t)),1!==l.length||c||n(p)},f.prototype.run=function(){this.fun.apply(null,this.array)},a.title="browser",a.browser=!0,a.env={},a.argv=[],a.version="",a.versions={},a.on=m,a.addListener=m,a.once=m,a.off=m,a.removeListener=m,a.removeAllListeners=m,a.emit=m,a.prependListener=m,a.prependOnceListener=m,a.listeners=function(e){return[]},a.binding=function(e){throw Error("process.binding is not supported")},a.cwd=function(){return"/"},a.chdir=function(e){throw Error("process.chdir is not supported")},a.umask=function(){return 0}}},r={};function i(e){var a=r[e];if(void 0!==a)return a.exports;var s=r[e]={exports:{}},o=!0;try{t[e](s,s.exports,i),o=!1}finally{o&&delete r[e]}return s.exports}i.ab="//";var a=i(229);e.exports=a}()},5925:function(e,t,r){"use strict";let i,a;r.d(t,{x7:function(){return ea},Am:function(){return _}});var s,o=r(2265);let n={data:""},l=e=>"object"==typeof window?((e?e.querySelector("#_goober"):window._goober)||Object.assign((e||document.head).appendChild(document.createElement("style")),{innerHTML:" ",id:"_goober"})).firstChild:e||n,c=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,d=/\/\*[^]*?\*\/|  +/g,u=/\n+/g,p=(e,t)=>{let r="",i="",a="";for(let s in e){let o=e[s];"@"==s[0]?"i"==s[1]?r=s+" "+o+";":i+="f"==s[1]?p(o,s):s+"{"+p(o,"k"==s[1]?"":t)+"}":"object"==typeof o?i+=p(o,t?t.replace(/([^,])+/g,e=>s.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+" "+t:t)):s):null!=o&&(s=/^--/.test(s)?s:s.replace(/[A-Z]/g,"-$&").toLowerCase(),a+=p.p?p.p(s,o):s+":"+o+";")}return r+(t&&a?t+"{"+a+"}":a)+i},f={},m=e=>{if("object"==typeof e){let t="";for(let r in e)t+=r+m(e[r]);return t}return e},h=(e,t,r,i,a)=>{var s;let o=m(e),n=f[o]||(f[o]=(e=>{let t=0,r=11;for(;t<e.length;)r=101*r+e.charCodeAt(t++)>>>0;return"go"+r})(o));if(!f[n]){let t=o!==e?e:(e=>{let t,r,i=[{}];for(;t=c.exec(e.replace(d,""));)t[4]?i.shift():t[3]?(r=t[3].replace(u," ").trim(),i.unshift(i[0][r]=i[0][r]||{})):i[0][t[1]]=t[2].replace(u," ").trim();return i[0]})(e);f[n]=p(a?{["@keyframes "+n]:t}:t,r?"":"."+n)}let l=r&&f.g?f.g:null;return r&&(f.g=f[n]),s=f[n],l?t.data=t.data.replace(l,s):-1===t.data.indexOf(s)&&(t.data=i?s+t.data:t.data+s),n},g=(e,t,r)=>e.reduce((e,i,a)=>{let s=t[a];if(s&&s.call){let e=s(r),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;s=t?"."+t:e&&"object"==typeof e?e.props?"":p(e,""):!1===e?"":e}return e+i+(null==s?"":s)},"");function b(e){let t=this||{},r=e.call?e(t.p):e;return h(r.unshift?r.raw?g(r,[].slice.call(arguments,1),t.p):r.reduce((e,r)=>Object.assign(e,r&&r.call?r(t.p):r),{}):r,l(t.target),t.g,t.o,t.k)}b.bind({g:1});let y,x,v,w=b.bind({k:1});function k(e,t){let r=this||{};return function(){let i=arguments;function a(s,o){let n=Object.assign({},s),l=n.className||a.className;r.p=Object.assign({theme:x&&x()},n),r.o=/ *go\d+/.test(l),n.className=b.apply(r,i)+(l?" "+l:""),t&&(n.ref=o);let c=e;return e[0]&&(c=n.as||e,delete n.as),v&&c[0]&&v(n),y(c,n)}return t?t(a):a}}var j=e=>"function"==typeof e,E=(e,t)=>j(e)?e(t):e,N=(i=0,()=>(++i).toString()),T=()=>{if(void 0===a&&"u">typeof window){let e=matchMedia("(prefers-reduced-motion: reduce)");a=!e||e.matches}return a},$=(e,t)=>{switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,20)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return $(e,{type:e.toasts.find(e=>e.id===r.id)?1:0,toast:r});case 3:let{toastId:i}=t;return{...e,toasts:e.toasts.map(e=>e.id===i||void 0===i?{...e,dismissed:!0,visible:!1}:e)};case 4:return void 0===t.toastId?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let a=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+a}))}}},O=[],C={toasts:[],pausedAt:void 0},z=e=>{C=$(C,e),O.forEach(e=>{e(C)})},A={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},D=(e={})=>{let[t,r]=(0,o.useState)(C),i=(0,o.useRef)(C);(0,o.useEffect)(()=>(i.current!==C&&r(C),O.push(r),()=>{let e=O.indexOf(r);e>-1&&O.splice(e,1)}),[]);let a=t.toasts.map(t=>{var r,i,a;return{...e,...e[t.type],...t,removeDelay:t.removeDelay||(null==(r=e[t.type])?void 0:r.removeDelay)||(null==e?void 0:e.removeDelay),duration:t.duration||(null==(i=e[t.type])?void 0:i.duration)||(null==e?void 0:e.duration)||A[t.type],style:{...e.style,...null==(a=e[t.type])?void 0:a.style,...t.style}}});return{...t,toasts:a}},L=(e,t="blank",r)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:"status","aria-live":"polite"},message:e,pauseDuration:0,...r,id:(null==r?void 0:r.id)||N()}),I=e=>(t,r)=>{let i=L(t,e,r);return z({type:2,toast:i}),i.id},_=(e,t)=>I("blank")(e,t);_.error=I("error"),_.success=I("success"),_.loading=I("loading"),_.custom=I("custom"),_.dismiss=e=>{z({type:3,toastId:e})},_.remove=e=>z({type:4,toastId:e}),_.promise=(e,t,r)=>{let i=_.loading(t.loading,{...r,...null==r?void 0:r.loading});return"function"==typeof e&&(e=e()),e.then(e=>{let a=t.success?E(t.success,e):void 0;return a?_.success(a,{id:i,...r,...null==r?void 0:r.success}):_.dismiss(i),e}).catch(e=>{let a=t.error?E(t.error,e):void 0;a?_.error(a,{id:i,...r,...null==r?void 0:r.error}):_.dismiss(i)}),e};var P=(e,t)=>{z({type:1,toast:{id:e,height:t}})},Z=()=>{z({type:5,time:Date.now()})},M=new Map,S=1e3,F=(e,t=S)=>{if(M.has(e))return;let r=setTimeout(()=>{M.delete(e),z({type:4,toastId:e})},t);M.set(e,r)},H=e=>{let{toasts:t,pausedAt:r}=D(e);(0,o.useEffect)(()=>{if(r)return;let e=Date.now(),i=t.map(t=>{if(t.duration===1/0)return;let r=(t.duration||0)+t.pauseDuration-(e-t.createdAt);if(r<0){t.visible&&_.dismiss(t.id);return}return setTimeout(()=>_.dismiss(t.id),r)});return()=>{i.forEach(e=>e&&clearTimeout(e))}},[t,r]);let i=(0,o.useCallback)(()=>{r&&z({type:6,time:Date.now()})},[r]),a=(0,o.useCallback)((e,r)=>{let{reverseOrder:i=!1,gutter:a=8,defaultPosition:s}=r||{},o=t.filter(t=>(t.position||s)===(e.position||s)&&t.height),n=o.findIndex(t=>t.id===e.id),l=o.filter((e,t)=>t<n&&e.visible).length;return o.filter(e=>e.visible).slice(...i?[l+1]:[0,l]).reduce((e,t)=>e+(t.height||0)+a,0)},[t]);return(0,o.useEffect)(()=>{t.forEach(e=>{if(e.dismissed)F(e.id,e.removeDelay);else{let t=M.get(e.id);t&&(clearTimeout(t),M.delete(e.id))}})},[t]),{toasts:t,handlers:{updateHeight:P,startPause:Z,endPause:i,calculateOffset:a}}},R=k("div")`
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
`,W=k("div")`
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
`,B=k("div")`
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
`,q=k("div")`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-width: 20px;
  min-height: 20px;
`,V=k("div")`
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
`,X=({toast:e})=>{let{icon:t,type:r,iconTheme:i}=e;return void 0!==t?"string"==typeof t?o.createElement(V,null,t):t:"blank"===r?null:o.createElement(q,null,o.createElement(W,{...i}),"loading"!==r&&o.createElement(U,null,"error"===r?o.createElement(R,{...i}):o.createElement(B,{...i})))},Y=e=>`
0% {transform: translate3d(0,${-200*e}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,G=e=>`
0% {transform: translate3d(0,0,-1px) scale(1); opacity:1;}
100% {transform: translate3d(0,${-150*e}%,-1px) scale(.6); opacity:0;}
`,J=k("div")`
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
`,K=k("div")`
  display: flex;
  justify-content: center;
  margin: 4px 10px;
  color: inherit;
  flex: 1 1 auto;
  white-space: pre-line;
`,Q=(e,t)=>{let r=e.includes("top")?1:-1,[i,a]=T()?["0%{opacity:0;} 100%{opacity:1;}","0%{opacity:1;} 100%{opacity:0;}"]:[Y(r),G(r)];return{animation:t?`${w(i)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${w(a)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}},ee=o.memo(({toast:e,position:t,style:r,children:i})=>{let a=e.height?Q(e.position||t||"top-center",e.visible):{opacity:0},s=o.createElement(X,{toast:e}),n=o.createElement(K,{...e.ariaProps},E(e.message,e));return o.createElement(J,{className:e.className,style:{...a,...r,...e.style}},"function"==typeof i?i({icon:s,message:n}):o.createElement(o.Fragment,null,s,n))});s=o.createElement,p.p=void 0,y=s,x=void 0,v=void 0;var et=({id:e,className:t,style:r,onHeightUpdate:i,children:a})=>{let s=o.useCallback(t=>{if(t){let r=()=>{i(e,t.getBoundingClientRect().height)};r(),new MutationObserver(r).observe(t,{subtree:!0,childList:!0,characterData:!0})}},[e,i]);return o.createElement("div",{ref:s,className:t,style:r},a)},er=(e,t)=>{let r=e.includes("top"),i=e.includes("center")?{justifyContent:"center"}:e.includes("right")?{justifyContent:"flex-end"}:{};return{left:0,right:0,display:"flex",position:"absolute",transition:T()?void 0:"all 230ms cubic-bezier(.21,1.02,.73,1)",transform:`translateY(${t*(r?1:-1)}px)`,...r?{top:0}:{bottom:0},...i}},ei=b`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`,ea=({reverseOrder:e,position:t="top-center",toastOptions:r,gutter:i,children:a,containerStyle:s,containerClassName:n})=>{let{toasts:l,handlers:c}=H(r);return o.createElement("div",{id:"_rht_toaster",style:{position:"fixed",zIndex:9999,top:16,left:16,right:16,bottom:16,pointerEvents:"none",...s},className:n,onMouseEnter:c.startPause,onMouseLeave:c.endPause},l.map(r=>{let s=r.position||t,n=er(s,c.calculateOffset(r,{reverseOrder:e,gutter:i,defaultPosition:t}));return o.createElement(et,{id:r.id,key:r.id,onHeightUpdate:c.updateHeight,className:r.visible?ei:"",style:n},"custom"===r.type?E(r.message,r):a?a(r):o.createElement(ee,{toast:r,position:s}))}))}}},function(e){e.O(0,[1176,6003,5230,5268,3588,132,8006,6265,8713,2971,596,1744],function(){return e(e.s=6481)}),_N_E=e.O()}]);