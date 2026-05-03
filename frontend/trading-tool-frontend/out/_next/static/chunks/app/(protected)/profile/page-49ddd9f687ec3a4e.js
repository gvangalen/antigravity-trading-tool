(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[5551],{62898:function(e,t,r){"use strict";r.d(t,{Z:function(){return n}});var a=r(2265),s={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let i=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),n=(e,t)=>{let r=(0,a.forwardRef)(({color:r="currentColor",size:n=24,strokeWidth:o=2,absoluteStrokeWidth:l,children:d,...c},u)=>(0,a.createElement)("svg",{ref:u,...s,width:n,height:n,stroke:r,strokeWidth:l?24*Number(o)/Number(n):o,className:`lucide lucide-${i(e)}`,...c},[...t.map(([e,t])=>(0,a.createElement)(e,t)),...(Array.isArray(d)?d:[d])||[]]));return r.displayName=`${e}`,r}},98783:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("ArrowUpRight",[["path",{d:"M7 7h10v10",key:"1tivn9"}],["path",{d:"M7 17 17 7",key:"1vkiza"}]])},60272:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Brain",[["path",{d:"M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z",key:"1mhkh5"}],["path",{d:"M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z",key:"1d6s00"}]])},86264:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Loader2",[["path",{d:"M21 12a9 9 0 1 1-6.219-8.56",key:"13zald"}]])},65883:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("LogOut",[["path",{d:"M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4",key:"1uf3rs"}],["polyline",{points:"16 17 21 12 16 7",key:"1gabdz"}],["line",{x1:"21",x2:"9",y1:"12",y2:"12",key:"1uyos4"}]])},1295:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Mail",[["rect",{width:"20",height:"16",x:"2",y:"4",rx:"2",key:"18n3k1"}],["path",{d:"m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7",key:"1ocrg3"}]])},49036:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Shield",[["path",{d:"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10",key:"1irkt0"}]])},82549:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("X",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]])},2859:function(e,t,r){Promise.resolve().then(r.bind(r,60477))},60477:function(e,t,r){"use strict";r.r(t),r.d(t,{default:function(){return b}});var a=r(57437),s=r(91080),i=r(86264),n=r(1295),o=r(49036),l=r(98783),d=r(60272),c=r(65883),u=r(61396),p=r.n(u),m=r(2265),f=r(24033),x=r(9323);function b(){let{user:e,logout:t}=(0,s.a)(),{showSnackbar:r}=(0,x.d)(),u=(0,f.useRouter)(),[b,h]=(0,m.useState)(!1);if(!e)return(0,a.jsx)("div",{className:"flex items-center justify-center min-h-[60vh]",children:(0,a.jsx)(i.Z,{className:"w-8 h-8 animate-spin text-blue-600"})});let g=async()=>{h(!0),await t(),r("You have been safely logged out ✔","success"),u.push("/login")},v="".concat(e.first_name||""," ").concat(e.last_name||"").trim()||e.email;return e.ai_requests_used_day,e.ai_requests_limit_day,(0,a.jsx)("div",{className:"min-h-screen bg-background text-foreground transition-colors duration-300 p-8 pt-12",children:(0,a.jsxs)("div",{className:"max-w-4xl mx-auto space-y-8 animate-fade-in",children:[(0,a.jsxs)("div",{className:"border-l-4 border-blue-600 pl-8 mb-12",children:[(0,a.jsx)("div",{className:"text-[11px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 opacity-80",children:"Account Laboratory"}),(0,a.jsx)("h1",{className:"text-5xl font-black text-foreground tracking-tight leading-none",children:"User Profile"})]}),(0,a.jsxs)("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-8",children:[(0,a.jsx)("div",{className:"bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group",children:(0,a.jsxs)("div",{className:"space-y-8",children:[(0,a.jsxs)("div",{className:"flex items-center gap-4",children:[(0,a.jsx)("div",{className:"w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-black text-xl shadow-lg shadow-blue-900/20",children:v.charAt(0).toUpperCase()}),(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-[10px] font-black text-secondary uppercase tracking-widest mb-1",children:"Trader Identity"}),(0,a.jsx)("div",{className:"text-2xl font-black text-foreground tracking-tight",children:v})]})]}),(0,a.jsxs)("div",{className:"space-y-6",children:[(0,a.jsxs)("div",{className:"flex items-center gap-4",children:[(0,a.jsx)("div",{className:"p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary",children:(0,a.jsx)(n.Z,{size:18})}),(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-[9px] font-black text-dim uppercase tracking-widest mb-0.5",children:"Contact Port"}),(0,a.jsx)("div",{className:"text-sm font-bold text-foreground",children:e.email})]})]}),(0,a.jsxs)("div",{className:"flex items-center gap-4",children:[(0,a.jsx)("div",{className:"p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary",children:(0,a.jsx)(o.Z,{size:18})}),(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-[9px] font-black text-dim uppercase tracking-widest mb-0.5",children:"Authorization Level"}),(0,a.jsx)("div",{className:"inline-flex items-center px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] font-black uppercase tracking-tighter border border-blue-200 dark:border-blue-800",children:e.role||"PRO"})]})]})]})]})}),(0,a.jsxs)("div",{className:"bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group relative overflow-hidden",children:[(0,a.jsx)("div",{className:"absolute top-0 right-0 w-32 h-32 bg-blue-600/5 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000"}),(0,a.jsxs)("div",{className:"relative z-10 space-y-12",children:[(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-[10px] font-black text-secondary uppercase tracking-widest mb-1",children:"Service Tier"}),(0,a.jsxs)("div",{className:"text-3xl font-black text-foreground tracking-tighter uppercase italic",children:[e.ai_plan||"Basis"," Plan"]})]}),(0,a.jsxs)("div",{className:"px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 text-[9px] font-black uppercase tracking-widest flex items-center gap-1.5",children:[(0,a.jsx)("div",{className:"w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"}),"Active"]})]}),(0,a.jsx)("div",{className:"py-6 border-y border-[var(--color-border-subtle)]",children:(0,a.jsx)("p",{className:"text-[11px] font-bold text-dim leading-relaxed uppercase tracking-widest",children:"Professional access enabled. All intelligence nodes are fully synchronized with your account."})}),(0,a.jsxs)("button",{className:"w-full bg-foreground text-card hover:bg-slate-800 py-4 rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 group/btn active:scale-95 shadow-xl",children:["Upgrade to Pro Level",(0,a.jsx)(l.Z,{size:14,className:"group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform"})]})]})]})]}),(0,a.jsxs)("div",{className:"bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10",children:[(0,a.jsx)("div",{className:"text-[10px] font-black text-secondary uppercase tracking-widest mb-6",children:"Strategic Terminal Actions"}),(0,a.jsxs)("div",{className:"grid grid-cols-1 sm:grid-cols-2 gap-4",children:[(0,a.jsxs)(p(),{href:"/admin/ai",className:"flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-blue-600/30 transition-all group",children:[(0,a.jsx)("div",{className:"p-3 rounded-xl bg-card text-blue-600 border border-[var(--color-border)]",children:(0,a.jsx)(d.Z,{size:20})}),(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-sm font-black text-foreground tracking-tight group-hover:text-blue-600 transition-colors",children:"AI Settings Interface"}),(0,a.jsx)("div",{className:"text-[10px] font-bold text-dim uppercase tracking-widest",children:"Adjust intelligence parameters"})]})]}),(0,a.jsxs)("button",{onClick:g,disabled:b,className:"flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-rose-600/30 transition-all group text-left",children:[(0,a.jsx)("div",{className:"p-3 rounded-xl bg-card text-rose-600 border border-[var(--color-border)]",children:b?(0,a.jsx)(i.Z,{size:20,className:"animate-spin"}):(0,a.jsx)(c.Z,{size:20})}),(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"text-sm font-black text-foreground tracking-tight group-hover:text-rose-600 transition-colors",children:"Sign Out Securely"}),(0,a.jsx)("div",{className:"text-[10px] font-bold text-dim uppercase tracking-widest",children:"Terminate current session"})]})]})]})]})]})})}},91080:function(e,t,r){"use strict";r.d(t,{H:function(){return u},a:function(){return d}});var a=r(57437),s=r(2265),i=r(14958);let n="tt_current_user";function o(){localStorage.removeItem(n)}let l=(0,s.createContext)(null);function d(){let e=(0,s.useContext)(l);if(!e)throw Error("useAuth must be used inside <AuthProvider>");return e}async function c(e){var t;let r=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{};return fetch(e,{credentials:"include",headers:{"Content-Type":"application/json",...null!==(t=r.headers)&&void 0!==t?t:{}},...r})}function u(e){var t;let{children:d}=e,u=null!==(t=function(){let e=localStorage.getItem(n);if(!e)return null;try{return JSON.parse(e)}catch(e){return null}}())&&void 0!==t?t:null,[p,m]=(0,s.useState)(u),[f,x]=(0,s.useState)(!0),[b,h]=(0,s.useState)(!1),g=(0,s.useRef)(!1),v=(0,s.useRef)(null),y=(0,s.useCallback)(async()=>{g.current=!0,v.current&&v.current.abort();let e=new AbortController;v.current=e;try{let t=await fetch("".concat(i.C,"/api/auth/me"),{credentials:"include",headers:{"Content-Type":"application/json"},signal:e.signal});if(t.ok){let e=await t.json();m(e),e&&localStorage.setItem(n,JSON.stringify(e))}else m(null),o();h(!0)}catch(e){(null==e?void 0:e.name)!=="AbortError"&&(console.error("❌ Auth /me error:",e),m(null),o(),h(!0))}finally{v.current===e&&(g.current=!1,x(!1))}},[]);(0,s.useEffect)(()=>(y(),()=>{v.current&&v.current.abort()}),[y]),(0,s.useEffect)(()=>{let e=setInterval(async()=>{try{await c("".concat(i.C,"/api/auth/refresh"),{method:"POST"})}catch(e){}},3e6);return()=>clearInterval(e)},[]);let w=(0,s.useCallback)(async(e,t)=>{try{let a=await c("".concat(i.C,"/api/auth/login"),{method:"POST",body:JSON.stringify({email:e,password:t})});if(!a.ok)return{success:!1,message:"Ongeldige inloggegevens"};return await y(),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.notification()}),{success:!0}}catch(e){return console.error("❌ Login fout:",e),{success:!1,message:"Serverfout"}}},[y]),k=(0,s.useCallback)(async()=>{m(null),o();try{await c("".concat(i.C,"/api/auth/logout"),{method:"POST"}),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.impact()})}catch(e){}},[]);return(0,a.jsx)(l.Provider,{value:{user:p,loading:f,sessionChecked:b,isAuthenticated:!!p,login:w,logout:k,fetchWithAuth:c,reload:y},children:d})}},9323:function(e,t,r){"use strict";r.d(t,{D:function(){return d},d:function(){return l}});var a=r(57437),s=r(2265),i=r(5925),n=r(82549);let o=(0,s.createContext)(null);function l(){let e=(0,s.useContext)(o);if(!e)throw Error("❌ useModal must be used within a ModalProvider");return e}function d(e){let{children:t}=e,[r,n]=(0,s.useState)(null),[l,d]=(0,s.useState)(!1),u=(0,s.useCallback)(()=>{var e;l||(null==r||null===(e=r.onCancel)||void 0===e||e.call(r),n(null))},[r,l]),p=(0,s.useCallback)(e=>{d(!1),n(e)},[]),m=(0,s.useCallback)(function(e){let t=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"success",r={id:e};"success"===t?i.Am.success(e,r):"danger"===t?i.Am.error(e,r):(0,i.Am)(e,r)},[]);return(0,s.useEffect)(()=>{if(!r)return;let e=document.body.style.overflow;document.body.style.overflow="hidden";let t=e=>"Escape"===e.key&&u();return window.addEventListener("keydown",t),()=>{document.body.style.overflow=e,window.removeEventListener("keydown",t)}},[r,u]),(0,a.jsxs)(o.Provider,{value:{openConfirm:p,close:u,showSnackbar:m},children:[t,(0,a.jsx)(c,{modal:r,busy:l,setBusy:d,onClose:u})]})}function c(e){let{modal:t,busy:r,setBusy:s,onClose:i}=e;if(!t)return null;let{title:o="Confirm",description:l,icon:d,tone:c="primary",confirmText:u="Confirm",cancelText:p="Cancel",onConfirm:m}=t,f="danger"===c?{iconBg:"bg-red-100 dark:bg-red-900/40",iconText:"text-red-600 dark:text-red-400",confirm:"bg-red-600 hover:bg-red-700 shadow-red-600/20"}:"info"===c?{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"}:"success"===c?{iconBg:"bg-green-100 dark:bg-green-900/40",iconText:"text-green-600 dark:text-green-400",confirm:"bg-green-600 hover:bg-green-700 shadow-green-600/20"}:{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"},x=async()=>{if(!m){i();return}try{s(!0),await m(),i()}catch(e){console.error("❌ Modal onConfirm error:",e)}finally{s(!1)}};return(0,a.jsx)("div",{className:"fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in",children:(0,a.jsxs)("div",{className:"w-full max-w-md bg-card dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors",children:[(0,a.jsx)("button",{onClick:i,className:"absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10",children:(0,a.jsx)(n.Z,{className:"w-5 h-5"})}),(0,a.jsxs)("div",{className:"px-8 pt-8 pb-6 flex items-center gap-4",children:[d&&(0,a.jsx)("div",{className:"rounded-2xl p-3 ".concat(f.iconBg),children:(0,a.jsx)("div",{className:f.iconText,children:d})}),(0,a.jsx)("h2",{className:"text-2xl font-black text-foreground dark:text-white tracking-tight",children:o})]}),l&&(0,a.jsx)("div",{className:"flex-1 overflow-y-auto px-8 py-2 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed",children:l}),(0,a.jsxs)("div",{className:"px-8 py-8 flex justify-end gap-4 mt-4",children:[(0,a.jsx)("button",{onClick:i,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 disabled:opacity-50",children:p}),(0,a.jsxs)("button",{onClick:x,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest text-white shadow-lg transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 ".concat(f.confirm),children:[r&&(0,a.jsx)("div",{className:"w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full"}),r?"Processing…":u]})]})]})})}},14958:function(e,t,r){"use strict";r.d(t,{C:function(){return a}}),"localhost"!==window.location.hostname&&window.location.hostname;let a=window.location.hostname.includes("tradamind.com")?"https://www.tradamind.com":"https://tradamind.com"},24033:function(e,t,r){e.exports=r(68165)},5925:function(e,t,r){"use strict";let a,s;r.d(t,{x7:function(){return es},Am:function(){return T}});var i,n=r(2265);let o={data:""},l=e=>"object"==typeof window?((e?e.querySelector("#_goober"):window._goober)||Object.assign((e||document.head).appendChild(document.createElement("style")),{innerHTML:" ",id:"_goober"})).firstChild:e||o,d=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,c=/\/\*[^]*?\*\/|  +/g,u=/\n+/g,p=(e,t)=>{let r="",a="",s="";for(let i in e){let n=e[i];"@"==i[0]?"i"==i[1]?r=i+" "+n+";":a+="f"==i[1]?p(n,i):i+"{"+p(n,"k"==i[1]?"":t)+"}":"object"==typeof n?a+=p(n,t?t.replace(/([^,])+/g,e=>i.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+" "+t:t)):i):null!=n&&(i=/^--/.test(i)?i:i.replace(/[A-Z]/g,"-$&").toLowerCase(),s+=p.p?p.p(i,n):i+":"+n+";")}return r+(t&&s?t+"{"+s+"}":s)+a},m={},f=e=>{if("object"==typeof e){let t="";for(let r in e)t+=r+f(e[r]);return t}return e},x=(e,t,r,a,s)=>{var i;let n=f(e),o=m[n]||(m[n]=(e=>{let t=0,r=11;for(;t<e.length;)r=101*r+e.charCodeAt(t++)>>>0;return"go"+r})(n));if(!m[o]){let t=n!==e?e:(e=>{let t,r,a=[{}];for(;t=d.exec(e.replace(c,""));)t[4]?a.shift():t[3]?(r=t[3].replace(u," ").trim(),a.unshift(a[0][r]=a[0][r]||{})):a[0][t[1]]=t[2].replace(u," ").trim();return a[0]})(e);m[o]=p(s?{["@keyframes "+o]:t}:t,r?"":"."+o)}let l=r&&m.g?m.g:null;return r&&(m.g=m[o]),i=m[o],l?t.data=t.data.replace(l,i):-1===t.data.indexOf(i)&&(t.data=a?i+t.data:t.data+i),o},b=(e,t,r)=>e.reduce((e,a,s)=>{let i=t[s];if(i&&i.call){let e=i(r),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;i=t?"."+t:e&&"object"==typeof e?e.props?"":p(e,""):!1===e?"":e}return e+a+(null==i?"":i)},"");function h(e){let t=this||{},r=e.call?e(t.p):e;return x(r.unshift?r.raw?b(r,[].slice.call(arguments,1),t.p):r.reduce((e,r)=>Object.assign(e,r&&r.call?r(t.p):r),{}):r,l(t.target),t.g,t.o,t.k)}h.bind({g:1});let g,v,y,w=h.bind({k:1});function k(e,t){let r=this||{};return function(){let a=arguments;function s(i,n){let o=Object.assign({},i),l=o.className||s.className;r.p=Object.assign({theme:v&&v()},o),r.o=/ *go\d+/.test(l),o.className=h.apply(r,a)+(l?" "+l:""),t&&(o.ref=n);let d=e;return e[0]&&(d=o.as||e,delete o.as),y&&d[0]&&y(o),g(d,o)}return t?t(s):s}}var j=e=>"function"==typeof e,N=(e,t)=>j(e)?e(t):e,C=(a=0,()=>(++a).toString()),E=()=>{if(void 0===s&&"u">typeof window){let e=matchMedia("(prefers-reduced-motion: reduce)");s=!e||e.matches}return s},A=(e,t)=>{switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,20)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return A(e,{type:e.toasts.find(e=>e.id===r.id)?1:0,toast:r});case 3:let{toastId:a}=t;return{...e,toasts:e.toasts.map(e=>e.id===a||void 0===a?{...e,dismissed:!0,visible:!1}:e)};case 4:return void 0===t.toastId?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let s=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+s}))}}},S=[],Z={toasts:[],pausedAt:void 0},z=e=>{Z=A(Z,e),S.forEach(e=>{e(Z)})},O={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},P=(e={})=>{let[t,r]=(0,n.useState)(Z),a=(0,n.useRef)(Z);(0,n.useEffect)(()=>(a.current!==Z&&r(Z),S.push(r),()=>{let e=S.indexOf(r);e>-1&&S.splice(e,1)}),[]);let s=t.toasts.map(t=>{var r,a,s;return{...e,...e[t.type],...t,removeDelay:t.removeDelay||(null==(r=e[t.type])?void 0:r.removeDelay)||(null==e?void 0:e.removeDelay),duration:t.duration||(null==(a=e[t.type])?void 0:a.duration)||(null==e?void 0:e.duration)||O[t.type],style:{...e.style,...null==(s=e[t.type])?void 0:s.style,...t.style}}});return{...t,toasts:s}},$=(e,t="blank",r)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:"status","aria-live":"polite"},message:e,pauseDuration:0,...r,id:(null==r?void 0:r.id)||C()}),_=e=>(t,r)=>{let a=$(t,e,r);return z({type:2,toast:a}),a.id},T=(e,t)=>_("blank")(e,t);T.error=_("error"),T.success=_("success"),T.loading=_("loading"),T.custom=_("custom"),T.dismiss=e=>{z({type:3,toastId:e})},T.remove=e=>z({type:4,toastId:e}),T.promise=(e,t,r)=>{let a=T.loading(t.loading,{...r,...null==r?void 0:r.loading});return"function"==typeof e&&(e=e()),e.then(e=>{let s=t.success?N(t.success,e):void 0;return s?T.success(s,{id:a,...r,...null==r?void 0:r.success}):T.dismiss(a),e}).catch(e=>{let s=t.error?N(t.error,e):void 0;s?T.error(s,{id:a,...r,...null==r?void 0:r.error}):T.dismiss(a)}),e};var M=(e,t)=>{z({type:1,toast:{id:e,height:t}})},I=()=>{z({type:5,time:Date.now()})},L=new Map,D=1e3,B=(e,t=D)=>{if(L.has(e))return;let r=setTimeout(()=>{L.delete(e),z({type:4,toastId:e})},t);L.set(e,r)},R=e=>{let{toasts:t,pausedAt:r}=P(e);(0,n.useEffect)(()=>{if(r)return;let e=Date.now(),a=t.map(t=>{if(t.duration===1/0)return;let r=(t.duration||0)+t.pauseDuration-(e-t.createdAt);if(r<0){t.visible&&T.dismiss(t.id);return}return setTimeout(()=>T.dismiss(t.id),r)});return()=>{a.forEach(e=>e&&clearTimeout(e))}},[t,r]);let a=(0,n.useCallback)(()=>{r&&z({type:6,time:Date.now()})},[r]),s=(0,n.useCallback)((e,r)=>{let{reverseOrder:a=!1,gutter:s=8,defaultPosition:i}=r||{},n=t.filter(t=>(t.position||i)===(e.position||i)&&t.height),o=n.findIndex(t=>t.id===e.id),l=n.filter((e,t)=>t<o&&e.visible).length;return n.filter(e=>e.visible).slice(...a?[l+1]:[0,l]).reduce((e,t)=>e+(t.height||0)+s,0)},[t]);return(0,n.useEffect)(()=>{t.forEach(e=>{if(e.dismissed)B(e.id,e.removeDelay);else{let t=L.get(e.id);t&&(clearTimeout(t),L.delete(e.id))}})},[t]),{toasts:t,handlers:{updateHeight:M,startPause:I,endPause:a,calculateOffset:s}}},H=k("div")`
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
`,U=k("div")`
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
`,F=k("div")`
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
`,J=k("div")`
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
`,W=({toast:e})=>{let{icon:t,type:r,iconTheme:a}=e;return void 0!==t?"string"==typeof t?n.createElement(V,null,t):t:"blank"===r?null:n.createElement(J,null,n.createElement(U,{...a}),"loading"!==r&&n.createElement(q,null,"error"===r?n.createElement(H,{...a}):n.createElement(F,{...a})))},Y=e=>`
0% {transform: translate3d(0,${-200*e}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,X=e=>`
0% {transform: translate3d(0,0,-1px) scale(1); opacity:1;}
100% {transform: translate3d(0,${-150*e}%,-1px) scale(.6); opacity:0;}
`,G=k("div")`
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
`,Q=(e,t)=>{let r=e.includes("top")?1:-1,[a,s]=E()?["0%{opacity:0;} 100%{opacity:1;}","0%{opacity:1;} 100%{opacity:0;}"]:[Y(r),X(r)];return{animation:t?`${w(a)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${w(s)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}},ee=n.memo(({toast:e,position:t,style:r,children:a})=>{let s=e.height?Q(e.position||t||"top-center",e.visible):{opacity:0},i=n.createElement(W,{toast:e}),o=n.createElement(K,{...e.ariaProps},N(e.message,e));return n.createElement(G,{className:e.className,style:{...s,...r,...e.style}},"function"==typeof a?a({icon:i,message:o}):n.createElement(n.Fragment,null,i,o))});i=n.createElement,p.p=void 0,g=i,v=void 0,y=void 0;var et=({id:e,className:t,style:r,onHeightUpdate:a,children:s})=>{let i=n.useCallback(t=>{if(t){let r=()=>{a(e,t.getBoundingClientRect().height)};r(),new MutationObserver(r).observe(t,{subtree:!0,childList:!0,characterData:!0})}},[e,a]);return n.createElement("div",{ref:i,className:t,style:r},s)},er=(e,t)=>{let r=e.includes("top"),a=e.includes("center")?{justifyContent:"center"}:e.includes("right")?{justifyContent:"flex-end"}:{};return{left:0,right:0,display:"flex",position:"absolute",transition:E()?void 0:"all 230ms cubic-bezier(.21,1.02,.73,1)",transform:`translateY(${t*(r?1:-1)}px)`,...r?{top:0}:{bottom:0},...a}},ea=h`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`,es=({reverseOrder:e,position:t="top-center",toastOptions:r,gutter:a,children:s,containerStyle:i,containerClassName:o})=>{let{toasts:l,handlers:d}=R(r);return n.createElement("div",{id:"_rht_toaster",style:{position:"fixed",zIndex:9999,top:16,left:16,right:16,bottom:16,pointerEvents:"none",...i},className:o,onMouseEnter:d.startPause,onMouseLeave:d.endPause},l.map(r=>{let i=r.position||t,o=er(i,d.calculateOffset(r,{reverseOrder:e,gutter:a,defaultPosition:t}));return n.createElement(et,{id:r.id,key:r.id,onHeightUpdate:d.updateHeight,className:r.visible?ea:"",style:o},"custom"===r.type?N(r.message,r):s?s(r):n.createElement(ee,{toast:r,position:i}))}))}}},function(e){e.O(0,[1176,2971,596,1744],function(){return e(e.s=2859)}),_N_E=e.O()}]);