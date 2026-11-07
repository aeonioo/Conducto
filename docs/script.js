const CONFIG={SUPABASE_URL:"https://bkmofesvesfrdrikhyet.supabase.co",SUPABASE_ANON_KEY:"sb_publishable_wCniCrnngtvjRLy9yF5-jA_HOzX_9GN"};
const PIL=[["e","Environment"],["s","Social"],["g","Governance"]];
const DEMO=[["NVIDIA",55,47,52,64],["Microsoft",61,44,53,71],["Google",57,41,38,88],["Meta",49,36,40,93],["OpenAI",46,43,35,57],["Amazon",52,34,45,80],["Anthropic",58,54,56,39],["Apple",63,52,57,52],["Tesla",44,40,46,67],["IBM",66,58,62,28],["AMD",53,51,55,22],["Oracle",50,47,49,25],["Intel",56,50,48,31],["Baidu",48,45,41,12],["Alibaba",47,42,44,15]];
const lab=v=>v>=60?"Strong":v<40?"Weak":"Average";
const mk=(sc,n)=>{const neg=Math.round(n*(100-sc)/160),pos=Math.round(n*sc/160);return{score:sc,n,neg,pos,neu:n-neg-pos}};
const demo=()=>DEMO.map(([company,e,s,g,n])=>{const a=Math.round(n*.28),b=Math.round(n*.37),o=(e+s+g)/3;return{company,e:mk(e,a),s:mk(s,b),g:mk(g,n-a-b),overall:o,label:lab(o),articles:n}});
const P=(r,k)=>r[k]||{score:50,n:0,pos:0,neu:0,neg:0};
const esc=t=>String(t).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let rows=[],sort="overall",isDemo=true,updated=null,note="",first=true;

function sorted(){const k={overall:r=>-r.overall,name:r=>r.company,e:r=>-P(r,"e").score,s:r=>-P(r,"s").score,g:r=>-P(r,"g").score}[sort];
  return [...rows].sort((a,b)=>k(a)>k(b)?1:k(a)<k(b)?-1:0)}

function renderSorts(){
  const opts=[["overall","Overall",""],...PIL.map(([k,n])=>[k,n,`var(--${k})`]),["name","Name",""]];
  document.getElementById("sorts").innerHTML=opts.map(([k,n,c])=>
    `<button type="button" data-sort="${k}" aria-pressed="${sort===k}">${c?`<i style="background:${c}"></i>`:""}${n}</button>`).join("");
}
function renderStatus(){
  const total=rows.reduce((s,r)=>s+(r.articles||0),0);
  const d=updated?new Date(updated).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"Asia/Kolkata"})+" ("+new Date(updated).toLocaleTimeString("en-IN",{hour:"numeric",minute:"2-digit",hour12:true,timeZone:"Asia/Kolkata"})+" IST)":"";
  document.getElementById("status").innerHTML=(isDemo?`<b>Sample data.</b> ${note||"Add your Supabase details in the script to see live scores."}`:`<b>Live: </b> Updated ${d}.`)+` ${total.toLocaleString()} articles scored in the last 30 days.`;
}
function render(){
  renderSorts();renderStatus();
  const list=document.getElementById("list");
  list.className="list"+(first?" go":"");
  list.innerHTML=sorted().map(r=>{
    const vals=PIL.map(([k])=>P(r,k).score),lo=Math.min(...vals),hi=Math.max(...vals);
    const x=v=>first?50:v;
    const dots=PIL.map(([k,n])=>{const p=P(r,k);return `<i class="dot" data-x="${p.score}" style="background:var(--${k});left:${x(p.score)}%" title="${n}: ${Math.round(p.score)} (${p.n} articles)"></i>`}).join("");
    const det=PIL.map(([k,n])=>{const p=P(r,k);return `<div class="pd"><div class="pt"><i style="background:var(--${k})"></i>${n}<b>${Math.round(p.score)}</b></div>
      <div class="split"><i style="flex:${p.neg};background:var(--neg)"></i><i style="flex:${p.neu};background:var(--neu)"></i><i style="flex:${p.pos};background:var(--pos)"></i></div>
      <p>${p.n?`${p.n} articles: ${p.neg} negative, ${p.neu} neutral, ${p.pos} positive`:"No scored articles yet"}</p></div>`}).join("");
    return `<li class="row"><button class="head" type="button" aria-expanded="false">
      <span class="name">${esc(r.company)}</span>
      <span class="plot"><i class="mid"></i><i class="rail"></i><i class="span" data-l="${lo}" data-w="${hi-lo}" style="left:${first?50:lo}%;width:${first?0:hi-lo}%"></i>${dots}<i class="avg" data-x="${r.overall}" style="left:${x(r.overall)}%" title="Overall ${Math.round(r.overall)}"></i></span>
      <span class="tot"><b>${Math.round(r.overall)}</b><span class="pill ${r.label}">${r.label}</span></span><i class="chev"></i></button>
      <div class="detail" hidden>${det}</div></li>`}).join("");
  if(first){first=false;requestAnimationFrame(()=>requestAnimationFrame(()=>{
    list.querySelectorAll("[data-x]").forEach(e=>e.style.left=e.dataset.x+"%");
    list.querySelectorAll(".span").forEach(e=>{e.style.left=e.dataset.l+"%";e.style.width=e.dataset.w+"%"})}))}
}
async function load(){
  const {SUPABASE_URL:u,SUPABASE_ANON_KEY:k}=CONFIG;
  if(u&&k){try{
    const r=await fetch(`${u}/rest/v1/company_scores?select=*`,{headers:{apikey:k,Authorization:`Bearer ${k}`}});
    if(!r.ok)throw new Error(r.status);
    rows=await r.json();isDemo=false;updated=rows.map(x=>x.updated_at).filter(Boolean).sort().pop();
  }catch(e){rows=demo();note="Could not reach Supabase, so this is sample data."}}
  else rows=demo();
  render();
}
document.getElementById("sorts").addEventListener("click",e=>{const b=e.target.closest("[data-sort]");if(b){sort=b.dataset.sort;render()}});
document.getElementById("list").addEventListener("click",e=>{const h=e.target.closest(".head");if(!h)return;
  const open=h.getAttribute("aria-expanded")==="true";h.setAttribute("aria-expanded",!open);h.nextElementSibling.hidden=open});

load();
