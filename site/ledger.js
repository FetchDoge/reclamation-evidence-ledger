(function(){
"use strict";
var LEDGER = window.RECLAMATION_LEDGER_DATA || {sites: [], agg: {}};  // from ledger-data.js (generated)
var sites = LEDGER.sites, agg = LEDGER.agg;
var NS = 'http://www.w3.org/2000/svg';
function css(v){ return getComputedStyle(document.body).getPropertyValue(v).trim(); }
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function el(n, attrs, parent){
  var e = document.createElementNS(NS, n);
  for (var k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function txt(parent, x, y, s, attrs){
  var t = el('text', Object.assign({x:x, y:y}, attrs||{}), parent);
  t.textContent = s; return t;
}
/* diagonal-hatch pattern defs, injected per-chart (ids stay unique per svg) */
function addHatch(svg, p){
  var defs = el('defs', {}, svg);
  function pat(id, gap, w){
    var pt = el('pattern', {id:id, width:gap, height:gap, patternUnits:'userSpaceOnUse', patternTransform:'rotate(45)'}, defs);
    el('rect', {width:gap, height:gap, fill:css('--paper')}, pt);
    el('line', {x1:0, y1:0, x2:0, y2:gap, stroke:css('--ink'), 'stroke-width':w}, pt);
  }
  pat(p+'-hatch', 7, 1.6);
  pat(p+'-hatchlight', 12, 1);
}
function fmtD(d){ return (d>=0?'+':'') + d.toFixed(2); }
function fmtD4(d){ return (d>=0?'+':'') + d.toFixed(4); }
function ciStr(ci){ return ci==null ? '\u2014' : '['+fmtD(ci[0])+', '+fmtD(ci[1])+']'; }

/* ---------- histogram ---------- */
function renderHist(){
  var host = document.getElementById('hist'); if(!host) return; host.innerHTML='';
  var W=920, H=250, ml=54, mr=14, mt=14, mb=40;
  var ds = sites.map(function(s){return s.delta;}).filter(function(d){return d!=null;});
  var lo=Math.min.apply(null,ds), hi=Math.max.apply(null,ds);
  lo=Math.floor(lo*20)/20-0.01; hi=Math.ceil(hi*20)/20+0.01;
  var NB=16, bins=new Array(NB).fill(0), bw=(hi-lo)/NB;
  ds.forEach(function(d){ var b=Math.min(NB-1, Math.floor((d-lo)/bw)); bins[b]++; });
  var mx=Math.max.apply(null,bins);
  var svg=el('svg',{viewBox:'0 0 '+W+' '+H,'class':'chart',role:'img','aria-label':'Delta histogram'});
  host.appendChild(svg);
  var X=function(v){return ml+(v-lo)/(hi-lo)*(W-ml-mr);};
  var Y=function(c){return H-mb-(c/mx)*(H-mt-mb);};
  var ink=css('--ink'), paper=css('--paper'), grid=css('--grid');
  addHatch(svg, 'hist');
  // noise band |d|<0.08 — hatched, like forecast shading in the morning paper
  var nb=el('rect',{x:X(-0.08), y:mt, width:X(0.08)-X(-0.08), height:H-mb-mt, fill:'url(#hist-hatchlight)'},svg);
  txt(svg,(X(-0.08)+X(0.08))/2, mt+14, 'noise band \u00b10.08', {fill:ink,'font-size':'10.5','text-anchor':'middle','font-family':'ui-monospace,monospace',opacity:'.7'});
  bins.forEach(function(c,i){
    var x0=lo+i*bw, mid=x0+bw/2;
    var fill = Math.abs(mid)<0.08 ? 'url(#hist-hatch)' : ink;
    var r=el('rect',{x:X(x0)+1, y:Y(c), width:Math.max(1,(X(x0+bw)-X(x0))-2), height:H-mb-Y(c), fill:fill, opacity: c? '1':'0', stroke:ink,'stroke-width':'1'},svg);
    var tt=el('title',{},r); tt.textContent=fmtD(x0)+' to '+fmtD(x0+bw)+': '+c+' sites';
  });
  // zero line
  el('line',{x1:X(0),y1:mt,x2:X(0),y2:H-mb,stroke:ink,'stroke-width':'1.5','stroke-dasharray':'6 4'},svg);
  // axes
  el('line',{x1:ml,y1:H-mb,x2:W-mr,y2:H-mb,stroke:ink,'stroke-width':'1.5'},svg);
  for(var v=Math.ceil(lo*10)/10; v<=hi+1e-9; v+=0.1){
    var vv=Math.round(v*10)/10;
    el('line',{x1:X(vv),y1:H-mb,x2:X(vv),y2:H-mb+5,stroke:ink,'stroke-width':'1'},svg);
    txt(svg,X(vv),H-mb+20,fmtD(vv),{fill:ink,'font-size':'11','text-anchor':'middle','font-family':'ui-monospace,monospace'});
  }
  for(var c=0;c<=mx;c+=Math.max(1,Math.ceil(mx/4))){
    el('line',{x1:ml,y1:Y(c),x2:W-mr,y2:Y(c),stroke:grid,'stroke-width':'1','stroke-dasharray':'3 4'},svg);
    txt(svg,ml-8,Y(c)+4,String(c),{fill:ink,'font-size':'11','text-anchor':'end','font-family':'ui-monospace,monospace'});
  }
  txt(svg,W-mr,H-8,'median matched-month \u0394 NDVI',{fill:ink,'font-size':'11','text-anchor':'end','font-style':'italic'});
}

/* ---------- table ---------- */
var sortK='delta', sortDir=1;
function filtered(){
  var qEl = document.getElementById('fq'),
      tEl = document.getElementById('ftier'),
      cEl = document.getElementById('fconf');
  var q = (qEl && qEl.value) ? qEl.value.toLowerCase() : '',
      t = (tEl && tEl.value) ? tEl.value : '',
      c = (cEl && cEl.value) ? cEl.value : '';
  var rows=sites.filter(function(s){
    return (!q || s.id.toLowerCase().indexOf(q)>=0)
        && (!t || s.tier===t) && (!c || s.conf===c);
  });
  rows.sort(function(a,b){
    var va=a[sortK], vb=b[sortK];
    if(va==null) return 1; if(vb==null) return -1;
    return (va<vb?-1:va>vb?1:0)*sortDir;
  });
  return rows;
}
function renderTable(){
  var tb=document.querySelector('#sites tbody'); if(!tb) return; tb.innerHTML='';
  var rows=filtered();
  var fc = document.getElementById('fcount'); if(fc) fc.textContent='showing '+rows.length+' of '+sites.length;
  rows.forEach(function(s){
    var tr=document.createElement('tr'); tr.className='rowh';
    tr.innerHTML =
      '<td><b>'+esc(s.id)+'</b></td>'+
      '<td><span class="badge '+s.tier+'">'+esc(s.stmt)+'</span></td>'+
      '<td><span class="conf">'+s.conf+'</span></td>'+
      '<td class="num">'+fmtD(s.delta)+'</td>'+
      '<td class="num">'+esc(ciStr(s.ci))+'</td>'+
      '<td class="num">'+s.mm.join(',')+'</td>'+
      '<td><a href="https://fetchdoge.github.io/reclamation-evidence-ledger/'+s.page+'" target="_blank" rel="noopener">packet&nbsp;\u2197</a></td>';
    tr.addEventListener('click', function(ev){
      if(ev.target.tagName==='A') return;
      selectSite(s.id);
      var dosEl = document.getElementById('dossier');
      if(dosEl){
        var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        dosEl.scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth'});
      }
    });
    tb.appendChild(tr);
  });
}
document.querySelectorAll('#sites th[data-k]').forEach(function(th){
  th.addEventListener('click', function(){
    var k=th.getAttribute('data-k');
    if(sortK===k) sortDir*=-1; else {sortK=k; sortDir=1;}
    renderTable();
  });
});
['fq','ftier','fconf'].forEach(function(id){
  var el=document.getElementById(id);
  if(el) el.addEventListener('input', renderTable);
});
// Operator (licensee) names are not published; there is no licensee filter.

/* ---------- dossier ---------- */
var MONTHS={1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'};
function parseD(s){ var p=s.split('-'); return Date.UTC(+p[0],+p[1]-1,+p[2]); }
function renderDossier(s){
  var host=document.getElementById('dossier-body'); if(!host) return; host.innerHTML='';
  var ink=css('--ink'), soft=css('--ink-soft'), paper=css('--paper'), grid=css('--grid');
  // header line
  var h=document.createElement('div'); h.className='dossier-head';
  h.innerHTML='<span class="badge '+s.tier+'">'+esc(s.stmt)+'</span>'+
    '<span style="font-size:22px"><b>'+esc(s.id)+'</b></span>'+
    '<span class="conf">confidence: '+s.conf+' &middot; '+esc(s.stmt)+'</span>';
  host.appendChild(h);
  var dm=document.createElement('div'); dm.className='dmeta';
  dm.innerHTML='<span>'+s.lat+', '+s.lon+'</span>'+
    '<span>'+s.nobs+' scenes</span><span>'+s.nchips+' chips</span>'+
    '<span>matched months: '+s.mm.map(function(m){return MONTHS[m];}).join(', ')+'</span>'+
    '<span><a href="https://fetchdoge.github.io/reclamation-evidence-ledger/'+s.page+'" target="_blank" rel="noopener">full evidence packet \u2197</a></span>';
  host.appendChild(dm);
  // time series
  var W=920,H=360,ml=56,mr=16,mt=26,mb=46;
  var x0=parseD('2023-05-01'), x1=parseD('2026-09-30'), y0=-0.05, y1=1.0;
  var X=function(t){return ml+(t-x0)/(x1-x0)*(W-ml-mr);};
  var Y=function(v){return mt+(1-(v-y0)/(y1-y0))*(H-mt-mb);};
  var svg=el('svg',{viewBox:'0 0 '+W+' '+H,'class':'chart',role:'img','aria-label':'NDVI time series for '+s.id});
  host.appendChild(svg);
  var fl=document.createElement('div'); fl.className='fig-label';
  fl.textContent='Fig. 4 \u2014 NDVI per scene, baseline 2023\u20132024 vs current 2025\u20132026 (ringed = month-matched; these carry the \u0394)';
  host.insertBefore(fl, svg);
  [0,0.2,0.4,0.6,0.8,1.0].forEach(function(v){
    el('line',{x1:ml,y1:Y(v),x2:W-mr,y2:Y(v),stroke:grid,'stroke-width':'1','stroke-dasharray':'3 4'},svg);
    txt(svg,ml-8,Y(v)+4,v.toFixed(1),{fill:ink,'font-size':'11','text-anchor':'end','font-family':'ui-monospace,monospace'});
  });
  for(var yr=2023; yr<=2026; yr++){
    [5,6,7,8,9].forEach(function(m){
      var t=Date.UTC(yr,m-1,15);
      el('line',{x1:X(t),y1:H-mb,x2:X(t),y2:H-mb+4,stroke:ink,'stroke-width':'1'},svg);
    });
    var ty=X(Date.UTC(yr,6,1));
    txt(svg,ty,H-mb+20,String(yr),{fill:ink,'font-size':'12','text-anchor':'middle','font-family':'ui-monospace,monospace'});
  }
  el('line',{x1:ml,y1:H-mb,x2:W-mr,y2:H-mb,stroke:ink,'stroke-width':'1.5'},svg);
  txt(svg,ml-44,mt-8,'NDVI',{'font-size':'12','font-style':'italic',fill:soft});
  if(s.bmed!=null) el('line',{x1:ml,y1:Y(s.bmed),x2:W-mr,y2:Y(s.bmed),stroke:ink,'stroke-width':'1.5','stroke-dasharray':'8 5'},svg);
  if(s.cmed!=null) el('line',{x1:ml,y1:Y(s.cmed),x2:W-mr,y2:Y(s.cmed),stroke:ink,'stroke-width':'1.5','stroke-dasharray':'2 4'},svg);
  s.obs.forEach(function(o){
    var t=parseD(o[0]), fill=o[3]?paper:ink;
    var c=el('circle',{cx:X(t), cy:Y(o[1]), r:4.2, fill:fill, stroke:ink,'stroke-width':'0.7',opacity:o[2]<0.5?'0.45':'1'},svg);
    var tt=el('title',{},c);
    tt.textContent=o[0]+' \u00b7 NDVI '+o[1].toFixed(3)+' \u00b7 clear '+(o[2]*100).toFixed(0)+'%' +(o[3]?' \u00b7 baseline':' \u00b7 current')+(o[4]?' \u00b7 month-matched':'');
    if(o[4]) el('circle',{cx:X(t), cy:Y(o[1]), r:8, fill:'none', stroke:ink,'stroke-width':'1.6'},svg);
  });
  var lg=document.createElement('div'); lg.className='legend';
  lg.innerHTML='<span><span class="sw hollow"></span>baseline 2023\u20132024'+(s.bmed!=null?' (median '+s.bmed.toFixed(2)+')':'')+'</span>'+
    '<span><span class="sw dot"></span>current 2025\u20132026'+(s.cmed!=null?' (median '+s.cmed.toFixed(2)+')':'')+'</span>'+
    '<span><span class="sw ring"></span>month-matched observation</span>';
  host.appendChild(lg);
  var sl=document.createElement('div'); sl.className='src-line';
  sl.textContent='Sentinel-2 L2A scenes, NDVI per scene; ringed observations are month-matched and carry the delta.';
  host.appendChild(sl);
  // delta + CI strip
  var fl2=document.createElement('div'); fl2.className='fig-label';
  fl2.textContent='Fig. 5 \u2014 Median matched-month \u0394 with 95% bootstrap CI'; host.appendChild(fl2);
  if(s.ci==null){
    var hd=document.createElement('div'); hd.className='honest';
    hd.innerHTML='<b>NO INTERVAL PRINTED.</b> This site has '+s.mm.length+' matched months; below four, the bootstrap interval looks precise and means almost nothing. Median \u0394 '+fmtD4(s.delta)+' stands without a confidence interval \u2014 by rule, not by omission.';
    host.appendChild(hd);
  } else {
    var W2=920,H2=120,m2l=70,m2r=30;
    var lo2=-0.35, hi2=0.35;
    var X2=function(v){return m2l+(v-lo2)/(hi2-lo2)*(W2-m2l-m2r);};
    var svg2=el('svg',{viewBox:'0 0 '+W2+' '+H2,'class':'chart',role:'img','aria-label':'Delta with confidence interval'});
    host.appendChild(svg2);
    addHatch(svg2, 'ci');
    el('rect',{x:X2(-0.08),y:14,width:X2(0.08)-X2(-0.08),height:H2-58,fill:'url(#ci-hatchlight)'},svg2);
    txt(svg2,(X2(-0.08)+X2(0.08))/2,30,'noise \u00b10.08',{fill:ink,'font-size':'10.5','text-anchor':'middle','font-family':'ui-monospace,monospace',opacity:'.7'});
    el('line',{x1:X2(0),y1:14,x2:X2(0),y2:H2-44,stroke:ink,'stroke-width':'1.2','stroke-dasharray':'5 4'},svg2);
    [-0.3,-0.2,-0.1,0,0.1,0.2,0.3].forEach(function(v){
      el('line',{x1:X2(v),y1:H2-44,x2:X2(v),y2:H2-38,stroke:ink},svg2);
      txt(svg2,X2(v),H2-24,fmtD(v),{fill:ink,'font-size':'11','text-anchor':'middle','font-family':'ui-monospace,monospace'});
    });
    var cy=H2/2+4;
    el('line',{x1:X2(s.ci[0]),y1:cy,x2:X2(s.ci[1]),y2:cy,stroke:ink,'stroke-width':'2.5'},svg2);
    [s.ci[0],s.ci[1]].forEach(function(v){ el('line',{x1:X2(v),y1:cy-9,x2:X2(v),y2:cy+9,stroke:ink,'stroke-width':'2.5'},svg2); });
    el('circle',{cx:X2(s.delta),cy:cy,r:7,fill:ink,stroke:ink,'stroke-width':'1.5'},svg2);
    txt(svg2,X2(s.delta),cy-18,fmtD4(s.delta),{fill:ink,'font-size':'13','text-anchor':'middle','font-family':'ui-monospace,monospace','font-weight':'bold'});
  }
  var sl2=document.createElement('div'); sl2.className='src-line';
  sl2.textContent='Bootstrap 95% interval over matched-month deltas; no interval is printed below four matched months.';
  host.appendChild(sl2);
  // claim
  var cb=document.createElement('div'); cb.className='claimbox';
  cb.innerHTML='<div class="stmt">&ldquo;'+esc(s.stmt)+'&rdquo;</div><div class="rat">'+esc(s.rat)+'</div>';
  host.appendChild(cb);
  var cl=document.createElement('div'); cl.className='fig-label'; cl.textContent='Caveats carried on the packet'; host.appendChild(cl);
  var ul=document.createElement('ul'); ul.className='caveats';
  s.cav.forEach(function(c){ var li=document.createElement('li'); li.textContent=c; ul.appendChild(li); });
  host.appendChild(ul);
}
function selectSite(id){
  var sel = document.getElementById('sitesel');
  if(sel) sel.value=id;
  var s=sites.filter(function(x){return x.id===id;})[0];
  if(s) renderDossier(s);
}
(function(){
  var sel=document.getElementById('sitesel');
  if(!sel) return;
  sites.forEach(function(s){
    var o=document.createElement('option'); o.value=s.id;
    o.textContent=s.id+' \u2014 '+s.tier+' / '+s.conf+' ('+fmtD(s.delta)+')';
    sel.appendChild(o);
  });
  sel.addEventListener('change', function(){ selectSite(sel.value); });
})();

/* ---------- method diagram ---------- */
function renderMethod(){
  var g = document.getElementById('mmboxes');
  if(!g) return;
  var ink=css('--ink'), wash=css('--wash');
  var months=[[5,'MAY'],[6,'JUN'],[7,'JUL'],[8,'AUG'],[9,'SEP']];
  months.forEach(function(mm,i){
    var x=200+i*132;
    [[52,'none'],[212,wash]].forEach(function(r){
      el('rect',{x:x,y:r[0],width:104,height:64,fill:r[1],stroke:ink,'stroke-width':'2'},g);
      txt(g,x+52,r[0]+28,mm[1],{fill:ink,'font-size':'13','text-anchor':'middle','font-family':"ui-monospace,'SF Mono',Menlo,monospace"});
      txt(g,x+52,r[0]+48,'median NDVI',{fill:ink,'font-size':'10',opacity:'.65','text-anchor':'middle','font-family':"ui-monospace,'SF Mono',Menlo,monospace"});
    });
    el('line',{x1:x+52,y1:120,x2:x+52,y2:208,stroke:ink,'stroke-width':'1.5','stroke-dasharray':'5 4'},g);
    txt(g,x+60,168,'\u0394'+mm[0],{fill:ink,'font-size':'12','font-style':'italic','font-family':"ui-monospace,'SF Mono',Menlo,monospace"});
  });
}

/* ---------- boot ---------- */
if(document.getElementById('mmboxes')) renderMethod();
if(document.getElementById('hist')) renderHist();
if(document.querySelector('#sites tbody')) renderTable();
var showcase = sites[0];
if(showcase && document.getElementById('dossier-body')) {
  selectSite(showcase.id);
}

// Expose on window
window.RECLAMATION_LEDGER = LEDGER;
window.selectSite = selectSite;
window.renderHist = renderHist;
window.renderTable = renderTable;
window.renderMethod = renderMethod;
})();