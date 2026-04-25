(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[6782],{62898:function(e,t,r){"use strict";r.d(t,{Z:function(){return n}});var a=r(2265),s={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let i=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),n=(e,t)=>{let r=(0,a.forwardRef)(({color:r="currentColor",size:n=24,strokeWidth:o=2,absoluteStrokeWidth:l,children:c,...d},u)=>(0,a.createElement)("svg",{ref:u,...s,width:n,height:n,stroke:r,strokeWidth:l?24*Number(o)/Number(n):o,className:`lucide lucide-${i(e)}`,...d},[...t.map(([e,t])=>(0,a.createElement)(e,t)),...(Array.isArray(c)?c:[c])||[]]));return r.displayName=`${e}`,r}},5589:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Lock",[["rect",{width:"18",height:"11",x:"3",y:"11",rx:"2",ry:"2",key:"1w4ew1"}],["path",{d:"M7 11V7a5 5 0 0 1 10 0v4",key:"fwvmzm"}]])},1295:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("Mail",[["rect",{width:"20",height:"16",x:"2",y:"4",rx:"2",key:"18n3k1"}],["path",{d:"m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7",key:"1ocrg3"}]])},36678:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("ShieldCheck",[["path",{d:"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10",key:"1irkt0"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]])},67972:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("User",[["path",{d:"M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2",key:"975kel"}],["circle",{cx:"12",cy:"7",r:"4",key:"17ys0d"}]])},82549:function(e,t,r){"use strict";r.d(t,{Z:function(){return s}});var a=r(62898);let s=(0,a.Z)("X",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]])},81646:function(e,t,r){Promise.resolve().then(r.bind(r,35581))},35581:function(e,t,r){"use strict";r.r(t),r.d(t,{default:function(){return x}});var a=r(57437),s=r(2265),i=r(61396),n=r.n(i),o=r(24033),l=r(36678),c=r(67972),d=r(1295),u=r(5589),m=r(62898);let p=(0,m.Z)("UserPlus",[["path",{d:"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",key:"1yyitq"}],["circle",{cx:"9",cy:"7",r:"4",key:"nufk8"}],["line",{x1:"19",x2:"19",y1:"8",y2:"14",key:"1bvyxn"}],["line",{x1:"22",x2:"16",y1:"11",y2:"11",key:"1shjgl"}]]);var f=r(14958),h=r(91080),g=r(9323);function x(){let e=(0,o.useRouter)(),{login:t,isAuthenticated:r,loading:i,sessionChecked:m}=(0,h.a)(),{showSnackbar:x}=(0,g.d)(),[b,y]=(0,s.useState)(""),[v,k]=(0,s.useState)(""),[w,j]=(0,s.useState)(""),[N,C]=(0,s.useState)(!1),E=(0,s.useRef)(!1);(0,s.useEffect)(()=>{m&&r&&!E.current&&(E.current=!0,e.replace("/dashboard"))},[r,m,e]);let A=async r=>{r.preventDefault(),C(!0);try{let r=await fetch("".concat(f.C,"/api/auth/register"),{method:"POST",headers:{"Content-Type":"application/json"},credentials:"include",body:JSON.stringify({first_name:b,email:v,password:w})});if(!r.ok){let e=await r.json().catch(()=>({}));x(e.detail||"Account aanmaken mislukt. Bestaat dit e-mailadres al?","danger"),C(!1);return}x("Account aangemaakt ✔ Je wordt nu ingelogd…","success");let a=await t(v,w);if(!a.success){x("Account gemaakt — log nu handmatig in","info"),e.replace("/login");return}e.replace("/dashboard")}catch(e){console.error("❌ Register fout:",e),x("Serverfout bij account aanmaken","danger")}finally{C(!1)}};return(0,a.jsx)("div",{className:"min-h-screen flex items-center justify-center bg-[var(--bg-premium-gradient)] px-4",children:(0,a.jsxs)("div",{className:"w-full max-w-md card bg-white/95 backdrop-blur-sm p-10 animate-fade-in",children:[(0,a.jsxs)("div",{className:"text-center mb-10",children:[(0,a.jsxs)("div",{className:"flex items-center justify-center gap-4 mb-10 scale-110 group",children:[(0,a.jsx)("div",{className:"relative",children:(0,a.jsx)("img",{src:"/tradamind_icon_v2.png",alt:"TM",className:"h-20 w-20 object-contain rounded-2xl transition-all duration-500"})}),(0,a.jsxs)("div",{className:"flex flex-col items-start justify-center text-left",children:[(0,a.jsx)("div",{className:"text-3xl font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1.5 transition-colors duration-300 group-hover:text-blue-600 dark:group-hover:text-blue-400",children:"Tradamind"}),(0,a.jsxs)("div",{className:"flex items-center gap-1.5 text-blue-600 dark:text-blue-500 mb-2",children:[(0,a.jsx)("div",{className:"animate-pulse-soft",children:(0,a.jsx)(l.Z,{size:18,strokeWidth:2.5})}),(0,a.jsx)("div",{className:"text-[11px] font-black uppercase tracking-[0.3em]",children:"Professional"})]}),(0,a.jsxs)("div",{className:"text-[8px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-80 border-t border-slate-100 dark:border-slate-800 pt-2 w-full",children:["Trade Smarter. Follow your plan.",(0,a.jsx)("br",{}),"Win consistently."]})]})]}),(0,a.jsx)("div",{className:"page-label mb-3",children:"Welkom bij Tradamind"}),(0,a.jsx)("h1",{className:"text-3xl font-bold text-foreground dark:text-slate-100 tracking-tighter text-center",children:"Je AI Trading Coach"}),(0,a.jsx)("p",{className:"page-subtitle mx-auto mt-4",children:"Maak je professionele Tradamind-account aan"})]}),(0,a.jsxs)("form",{onSubmit:A,className:"space-y-6",children:[(0,a.jsxs)("div",{className:"space-y-3",children:[(0,a.jsx)("label",{className:"metric-label ml-1",children:"Volledige Naam"}),(0,a.jsxs)("div",{className:"relative group",children:[(0,a.jsx)(c.Z,{size:18,className:"absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10"}),(0,a.jsx)("input",{type:"text",required:!0,className:"trade-input pr-14",placeholder:"Je naam",value:b,onChange:e=>y(e.target.value)})]})]}),(0,a.jsxs)("div",{className:"space-y-3",children:[(0,a.jsx)("label",{className:"metric-label ml-1",children:"E-mail Adres"}),(0,a.jsxs)("div",{className:"relative group",children:[(0,a.jsx)(d.Z,{size:18,className:"absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10"}),(0,a.jsx)("input",{type:"email",required:!0,className:"trade-input pr-14",placeholder:"naam@voorraad.com",value:v,onChange:e=>k(e.target.value)})]})]}),(0,a.jsxs)("div",{className:"space-y-3",children:[(0,a.jsx)("label",{className:"metric-label ml-1",children:"Wachtwoord"}),(0,a.jsxs)("div",{className:"relative group",children:[(0,a.jsx)(u.Z,{size:18,className:"absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10"}),(0,a.jsx)("input",{type:"password",required:!0,minLength:6,className:"trade-input pr-14",placeholder:"•••••••••",value:w,onChange:e=>j(e.target.value)})]})]}),(0,a.jsx)("button",{type:"submit",disabled:N,className:"btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px] mt-4",children:N?(0,a.jsx)(a.Fragment,{children:"Aanmaken..."}):(0,a.jsxs)(a.Fragment,{children:[(0,a.jsx)(p,{size:18}),"ACCOUNT AANMAKEN"]})})]}),(0,a.jsx)("div",{className:"text-center mt-10 pt-8 border-t-2 border-slate-50",children:(0,a.jsxs)("p",{className:"metric-label text-slate-400 mb-0 lowercase normal-case tracking-normal",children:["Heb je al een account?",(0,a.jsx)(n(),{href:"/login",className:"text-blue-600 font-bold hover:underline ml-2 uppercase tracking-widest text-[10px]",children:"Log in →"})]})})]})})}},91080:function(e,t,r){"use strict";r.d(t,{H:function(){return u},a:function(){return c}});var a=r(57437),s=r(2265),i=r(14958);let n="tt_current_user";function o(){localStorage.removeItem(n)}let l=(0,s.createContext)(null);function c(){let e=(0,s.useContext)(l);if(!e)throw Error("useAuth must be used inside <AuthProvider>");return e}async function d(e){var t;let r=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{};return fetch(e,{credentials:"include",headers:{"Content-Type":"application/json",...null!==(t=r.headers)&&void 0!==t?t:{}},...r})}function u(e){var t;let{children:c}=e,u=null!==(t=function(){let e=localStorage.getItem(n);if(!e)return null;try{return JSON.parse(e)}catch(e){return null}}())&&void 0!==t?t:null,[m,p]=(0,s.useState)(u),[f,h]=(0,s.useState)(!0),[g,x]=(0,s.useState)(!1),b=(0,s.useRef)(!1),y=(0,s.useRef)(null),v=(0,s.useCallback)(async()=>{b.current=!0,y.current&&y.current.abort();let e=new AbortController;y.current=e;try{let t=await fetch("".concat(i.C,"/api/auth/me"),{credentials:"include",headers:{"Content-Type":"application/json"},signal:e.signal});if(t.ok){let e=await t.json();p(e),e&&localStorage.setItem(n,JSON.stringify(e))}else p(null),o();x(!0)}catch(e){(null==e?void 0:e.name)!=="AbortError"&&(console.error("❌ Auth /me error:",e),p(null),o(),x(!0))}finally{y.current===e&&(b.current=!1,h(!1))}},[]);(0,s.useEffect)(()=>(v(),()=>{y.current&&y.current.abort()}),[v]),(0,s.useEffect)(()=>{let e=setInterval(async()=>{try{await d("".concat(i.C,"/api/auth/refresh"),{method:"POST"})}catch(e){}},3e6);return()=>clearInterval(e)},[]);let k=(0,s.useCallback)(async(e,t)=>{try{let a=await d("".concat(i.C,"/api/auth/login"),{method:"POST",body:JSON.stringify({email:e,password:t})});if(!a.ok)return{success:!1,message:"Ongeldige inloggegevens"};return await v(),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.notification()}),{success:!0}}catch(e){return console.error("❌ Login fout:",e),{success:!1,message:"Serverfout"}}},[v]),w=(0,s.useCallback)(async()=>{p(null),o();try{await d("".concat(i.C,"/api/auth/logout"),{method:"POST"}),r.e(6123).then(r.bind(r,16123)).then(e=>{let{hapticFeedback:t}=e;t.impact()})}catch(e){}},[]);return(0,a.jsx)(l.Provider,{value:{user:m,loading:f,sessionChecked:g,isAuthenticated:!!m,login:k,logout:w,fetchWithAuth:d,reload:v},children:c})}},9323:function(e,t,r){"use strict";r.d(t,{D:function(){return c},d:function(){return l}});var a=r(57437),s=r(2265),i=r(5925),n=r(82549);let o=(0,s.createContext)(null);function l(){let e=(0,s.useContext)(o);if(!e)throw Error("❌ useModal must be used within a ModalProvider");return e}function c(e){let{children:t}=e,[r,n]=(0,s.useState)(null),[l,c]=(0,s.useState)(!1),u=(0,s.useCallback)(()=>{var e;l||(null==r||null===(e=r.onCancel)||void 0===e||e.call(r),n(null))},[r,l]),m=(0,s.useCallback)(e=>{c(!1),n(e)},[]),p=(0,s.useCallback)(function(e){let t=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"success",r={id:e};"success"===t?i.Am.success(e,r):"danger"===t?i.Am.error(e,r):(0,i.Am)(e,r)},[]);return(0,s.useEffect)(()=>{if(!r)return;let e=document.body.style.overflow;document.body.style.overflow="hidden";let t=e=>"Escape"===e.key&&u();return window.addEventListener("keydown",t),()=>{document.body.style.overflow=e,window.removeEventListener("keydown",t)}},[r,u]),(0,a.jsxs)(o.Provider,{value:{openConfirm:m,close:u,showSnackbar:p},children:[t,(0,a.jsx)(d,{modal:r,busy:l,setBusy:c,onClose:u})]})}function d(e){let{modal:t,busy:r,setBusy:s,onClose:i}=e;if(!t)return null;let{title:o="Confirm",description:l,icon:c,tone:d="primary",confirmText:u="Confirm",cancelText:m="Cancel",onConfirm:p}=t,f="danger"===d?{iconBg:"bg-red-100 dark:bg-red-900/40",iconText:"text-red-600 dark:text-red-400",confirm:"bg-red-600 hover:bg-red-700 shadow-red-600/20"}:"info"===d?{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"}:"success"===d?{iconBg:"bg-green-100 dark:bg-green-900/40",iconText:"text-green-600 dark:text-green-400",confirm:"bg-green-600 hover:bg-green-700 shadow-green-600/20"}:{iconBg:"bg-blue-100 dark:bg-blue-900/40",iconText:"text-blue-600 dark:text-blue-400",confirm:"bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"},h=async()=>{if(!p){i();return}try{s(!0),await p(),i()}catch(e){console.error("❌ Modal onConfirm error:",e)}finally{s(!1)}};return(0,a.jsx)("div",{className:"fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in",children:(0,a.jsxs)("div",{className:"w-full max-w-md bg-card dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors",children:[(0,a.jsx)("button",{onClick:i,className:"absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10",children:(0,a.jsx)(n.Z,{className:"w-5 h-5"})}),(0,a.jsxs)("div",{className:"px-8 pt-8 pb-6 flex items-center gap-4",children:[c&&(0,a.jsx)("div",{className:"rounded-2xl p-3 ".concat(f.iconBg),children:(0,a.jsx)("div",{className:f.iconText,children:c})}),(0,a.jsx)("h2",{className:"text-2xl font-black text-foreground dark:text-white tracking-tight",children:o})]}),l&&(0,a.jsx)("div",{className:"flex-1 overflow-y-auto px-8 py-2 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed",children:l}),(0,a.jsxs)("div",{className:"px-8 py-8 flex justify-end gap-4 mt-4",children:[(0,a.jsx)("button",{onClick:i,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 disabled:opacity-50",children:m}),(0,a.jsxs)("button",{onClick:h,disabled:r,className:"px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest text-white shadow-lg transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 ".concat(f.confirm),children:[r&&(0,a.jsx)("div",{className:"w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full"}),r?"Processing…":u]})]})]})})}},14958:function(e,t,r){"use strict";r.d(t,{C:function(){return a}});let a="http://localhost:8000"},24033:function(e,t,r){e.exports=r(68165)},5925:function(e,t,r){"use strict";let a,s;r.d(t,{x7:function(){return es},Am:function(){return M}});var i,n=r(2265);let o={data:""},l=e=>"object"==typeof window?((e?e.querySelector("#_goober"):window._goober)||Object.assign((e||document.head).appendChild(document.createElement("style")),{innerHTML:" ",id:"_goober"})).firstChild:e||o,c=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,d=/\/\*[^]*?\*\/|  +/g,u=/\n+/g,m=(e,t)=>{let r="",a="",s="";for(let i in e){let n=e[i];"@"==i[0]?"i"==i[1]?r=i+" "+n+";":a+="f"==i[1]?m(n,i):i+"{"+m(n,"k"==i[1]?"":t)+"}":"object"==typeof n?a+=m(n,t?t.replace(/([^,])+/g,e=>i.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+" "+t:t)):i):null!=n&&(i=/^--/.test(i)?i:i.replace(/[A-Z]/g,"-$&").toLowerCase(),s+=m.p?m.p(i,n):i+":"+n+";")}return r+(t&&s?t+"{"+s+"}":s)+a},p={},f=e=>{if("object"==typeof e){let t="";for(let r in e)t+=r+f(e[r]);return t}return e},h=(e,t,r,a,s)=>{var i;let n=f(e),o=p[n]||(p[n]=(e=>{let t=0,r=11;for(;t<e.length;)r=101*r+e.charCodeAt(t++)>>>0;return"go"+r})(n));if(!p[o]){let t=n!==e?e:(e=>{let t,r,a=[{}];for(;t=c.exec(e.replace(d,""));)t[4]?a.shift():t[3]?(r=t[3].replace(u," ").trim(),a.unshift(a[0][r]=a[0][r]||{})):a[0][t[1]]=t[2].replace(u," ").trim();return a[0]})(e);p[o]=m(s?{["@keyframes "+o]:t}:t,r?"":"."+o)}let l=r&&p.g?p.g:null;return r&&(p.g=p[o]),i=p[o],l?t.data=t.data.replace(l,i):-1===t.data.indexOf(i)&&(t.data=a?i+t.data:t.data+i),o},g=(e,t,r)=>e.reduce((e,a,s)=>{let i=t[s];if(i&&i.call){let e=i(r),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;i=t?"."+t:e&&"object"==typeof e?e.props?"":m(e,""):!1===e?"":e}return e+a+(null==i?"":i)},"");function x(e){let t=this||{},r=e.call?e(t.p):e;return h(r.unshift?r.raw?g(r,[].slice.call(arguments,1),t.p):r.reduce((e,r)=>Object.assign(e,r&&r.call?r(t.p):r),{}):r,l(t.target),t.g,t.o,t.k)}x.bind({g:1});let b,y,v,k=x.bind({k:1});function w(e,t){let r=this||{};return function(){let a=arguments;function s(i,n){let o=Object.assign({},i),l=o.className||s.className;r.p=Object.assign({theme:y&&y()},o),r.o=/ *go\d+/.test(l),o.className=x.apply(r,a)+(l?" "+l:""),t&&(o.ref=n);let c=e;return e[0]&&(c=o.as||e,delete o.as),v&&c[0]&&v(o),b(c,o)}return t?t(s):s}}var j=e=>"function"==typeof e,N=(e,t)=>j(e)?e(t):e,C=(a=0,()=>(++a).toString()),E=()=>{if(void 0===s&&"u">typeof window){let e=matchMedia("(prefers-reduced-motion: reduce)");s=!e||e.matches}return s},A=(e,t)=>{switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,20)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return A(e,{type:e.toasts.find(e=>e.id===r.id)?1:0,toast:r});case 3:let{toastId:a}=t;return{...e,toasts:e.toasts.map(e=>e.id===a||void 0===a?{...e,dismissed:!0,visible:!1}:e)};case 4:return void 0===t.toastId?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let s=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+s}))}}},S=[],O={toasts:[],pausedAt:void 0},T=e=>{O=A(O,e),S.forEach(e=>{e(O)})},z={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},$=(e={})=>{let[t,r]=(0,n.useState)(O),a=(0,n.useRef)(O);(0,n.useEffect)(()=>(a.current!==O&&r(O),S.push(r),()=>{let e=S.indexOf(r);e>-1&&S.splice(e,1)}),[]);let s=t.toasts.map(t=>{var r,a,s;return{...e,...e[t.type],...t,removeDelay:t.removeDelay||(null==(r=e[t.type])?void 0:r.removeDelay)||(null==e?void 0:e.removeDelay),duration:t.duration||(null==(a=e[t.type])?void 0:a.duration)||(null==e?void 0:e.duration)||z[t.type],style:{...e.style,...null==(s=e[t.type])?void 0:s.style,...t.style}}});return{...t,toasts:s}},P=(e,t="blank",r)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:"status","aria-live":"polite"},message:e,pauseDuration:0,...r,id:(null==r?void 0:r.id)||C()}),Z=e=>(t,r)=>{let a=P(t,e,r);return T({type:2,toast:a}),a.id},M=(e,t)=>Z("blank")(e,t);M.error=Z("error"),M.success=Z("success"),M.loading=Z("loading"),M.custom=Z("custom"),M.dismiss=e=>{T({type:3,toastId:e})},M.remove=e=>T({type:4,toastId:e}),M.promise=(e,t,r)=>{let a=M.loading(t.loading,{...r,...null==r?void 0:r.loading});return"function"==typeof e&&(e=e()),e.then(e=>{let s=t.success?N(t.success,e):void 0;return s?M.success(s,{id:a,...r,...null==r?void 0:r.success}):M.dismiss(a),e}).catch(e=>{let s=t.error?N(t.error,e):void 0;s?M.error(s,{id:a,...r,...null==r?void 0:r.error}):M.dismiss(a)}),e};var D=(e,t)=>{T({type:1,toast:{id:e,height:t}})},_=()=>{T({type:5,time:Date.now()})},I=new Map,L=1e3,B=(e,t=L)=>{if(I.has(e))return;let r=setTimeout(()=>{I.delete(e),T({type:4,toastId:e})},t);I.set(e,r)},H=e=>{let{toasts:t,pausedAt:r}=$(e);(0,n.useEffect)(()=>{if(r)return;let e=Date.now(),a=t.map(t=>{if(t.duration===1/0)return;let r=(t.duration||0)+t.pauseDuration-(e-t.createdAt);if(r<0){t.visible&&M.dismiss(t.id);return}return setTimeout(()=>M.dismiss(t.id),r)});return()=>{a.forEach(e=>e&&clearTimeout(e))}},[t,r]);let a=(0,n.useCallback)(()=>{r&&T({type:6,time:Date.now()})},[r]),s=(0,n.useCallback)((e,r)=>{let{reverseOrder:a=!1,gutter:s=8,defaultPosition:i}=r||{},n=t.filter(t=>(t.position||i)===(e.position||i)&&t.height),o=n.findIndex(t=>t.id===e.id),l=n.filter((e,t)=>t<o&&e.visible).length;return n.filter(e=>e.visible).slice(...a?[l+1]:[0,l]).reduce((e,t)=>e+(t.height||0)+s,0)},[t]);return(0,n.useEffect)(()=>{t.forEach(e=>{if(e.dismissed)B(e.id,e.removeDelay);else{let t=I.get(e.id);t&&(clearTimeout(t),I.delete(e.id))}})},[t]),{toasts:t,handlers:{updateHeight:D,startPause:_,endPause:a,calculateOffset:s}}},F=w("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||"#ff4b4b"};
  position: relative;
  transform: rotate(45deg);

  animation: ${k`
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
    animation: ${k`
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
    animation: ${k`
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
`,R=w("div")`
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border: 2px solid;
  border-radius: 100%;
  border-color: ${e=>e.secondary||"#e0e0e0"};
  border-right-color: ${e=>e.primary||"#616161"};
  animation: ${k`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
`} 1s linear infinite;
`,J=w("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||"#61d345"};
  position: relative;
  transform: rotate(45deg);

  animation: ${k`
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
    animation: ${k`
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
`,W=w("div")`
  position: absolute;
`,q=w("div")`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-width: 20px;
  min-height: 20px;
`,U=w("div")`
  position: relative;
  transform: scale(0.6);
  opacity: 0.4;
  min-width: 20px;
  animation: ${k`
from {
  transform: scale(0.6);
  opacity: 0.4;
}
to {
  transform: scale(1);
  opacity: 1;
}`} 0.3s 0.12s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
`,V=({toast:e})=>{let{icon:t,type:r,iconTheme:a}=e;return void 0!==t?"string"==typeof t?n.createElement(U,null,t):t:"blank"===r?null:n.createElement(q,null,n.createElement(R,{...a}),"loading"!==r&&n.createElement(W,null,"error"===r?n.createElement(F,{...a}):n.createElement(J,{...a})))},K=e=>`
0% {transform: translate3d(0,${-200*e}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,X=e=>`
0% {transform: translate3d(0,0,-1px) scale(1); opacity:1;}
100% {transform: translate3d(0,${-150*e}%,-1px) scale(.6); opacity:0;}
`,Y=w("div")`
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
`,G=w("div")`
  display: flex;
  justify-content: center;
  margin: 4px 10px;
  color: inherit;
  flex: 1 1 auto;
  white-space: pre-line;
`,Q=(e,t)=>{let r=e.includes("top")?1:-1,[a,s]=E()?["0%{opacity:0;} 100%{opacity:1;}","0%{opacity:1;} 100%{opacity:0;}"]:[K(r),X(r)];return{animation:t?`${k(a)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${k(s)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}},ee=n.memo(({toast:e,position:t,style:r,children:a})=>{let s=e.height?Q(e.position||t||"top-center",e.visible):{opacity:0},i=n.createElement(V,{toast:e}),o=n.createElement(G,{...e.ariaProps},N(e.message,e));return n.createElement(Y,{className:e.className,style:{...s,...r,...e.style}},"function"==typeof a?a({icon:i,message:o}):n.createElement(n.Fragment,null,i,o))});i=n.createElement,m.p=void 0,b=i,y=void 0,v=void 0;var et=({id:e,className:t,style:r,onHeightUpdate:a,children:s})=>{let i=n.useCallback(t=>{if(t){let r=()=>{a(e,t.getBoundingClientRect().height)};r(),new MutationObserver(r).observe(t,{subtree:!0,childList:!0,characterData:!0})}},[e,a]);return n.createElement("div",{ref:i,className:t,style:r},s)},er=(e,t)=>{let r=e.includes("top"),a=e.includes("center")?{justifyContent:"center"}:e.includes("right")?{justifyContent:"flex-end"}:{};return{left:0,right:0,display:"flex",position:"absolute",transition:E()?void 0:"all 230ms cubic-bezier(.21,1.02,.73,1)",transform:`translateY(${t*(r?1:-1)}px)`,...r?{top:0}:{bottom:0},...a}},ea=x`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`,es=({reverseOrder:e,position:t="top-center",toastOptions:r,gutter:a,children:s,containerStyle:i,containerClassName:o})=>{let{toasts:l,handlers:c}=H(r);return n.createElement("div",{id:"_rht_toaster",style:{position:"fixed",zIndex:9999,top:16,left:16,right:16,bottom:16,pointerEvents:"none",...i},className:o,onMouseEnter:c.startPause,onMouseLeave:c.endPause},l.map(r=>{let i=r.position||t,o=er(i,c.calculateOffset(r,{reverseOrder:e,gutter:a,defaultPosition:t}));return n.createElement(et,{id:r.id,key:r.id,onHeightUpdate:c.updateHeight,className:r.visible?ea:"",style:o},"custom"===r.type?N(r.message,r):s?s(r):n.createElement(ee,{toast:r,position:i}))}))}}},function(e){e.O(0,[1176,2971,596,1744],function(){return e(e.s=81646)}),_N_E=e.O()}]);