const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8');
const payload=html.match(/<script type="application\/json" id=payload>(.*?)<\/script>/s)[1];
const scripts=html.match(/<script>(.*?)<\/script>/s)[1];
class N{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.events={};this.dataset={};this.attrs={};this.value='';this.textContent='';this.hidden=false}
 append(...x){this.children.push(...x)}
 replaceChildren(...x){this.children=x;if(this.tag==='select')this.value=x[0]?.value??''}
 addEventListener(n,f){this.events[n]=f}
 setAttribute(k,v){this.attrs[k]=v}
 querySelectorAll(tag){return this.children.filter(x=>tag==='details[open]'?x.tag==='details'&&x.open:x.tag===tag)}
 querySelector(tag){return this.querySelectorAll(tag)[0]}
 scrollIntoView(){}
 click(){this.onclick?.();if(this.parent)this.parent.events.click?.({target:this})}
}
const elements={};for(const m of html.matchAll(/<(\w+)[^<>]*?\bid="?([a-z]+)"?/g))elements[m[2]]=new N(m[1]);
const d=JSON.parse(payload);elements.payload.textContent=payload;
for(const view of ['oone','history','variance','agency','pipeline']){const b=new N('button');b.dataset.view=view;b.parent=elements.nav;elements.nav.append(b)}
vm.runInNewContext(scripts,{document:{getElementById:id=>elements[id],createElement:t=>new N(t),createElementNS:(ns,t)=>new N(t)},Node:N,Intl,URL});
assert.equal(d.history.length,760);
assert.equal(d.request.length,749);
const rendered=n=>[n.textContent,...n.children.map(rendered)].join(' ');
assert.equal(elements.oone.hidden,false);
assert.equal(d.o1.detail.length,1238);
const compare=()=>rendered(elements.ocompare);
assert.match(elements.ocontext.textContent,/Funding FY2025 · O&M Title \+ Indefinite Accounts · as-published total obligational authority/);
for(const row of elements.ocompare.children){
 assert.match(rendered(row.children[0]),/FY2025 · PB(25|26|27) · .* · TOA \$[\d.]+B/);
}
assert.match(rendered(elements.oother),/FY2025 · PB26 · Supplemental · TOA \$3\.940452B/);
elements.oscope.value='om_title';elements.oscope.events.change();
assert.match(elements.ocontext.textContent,/FY2025 · O&M Title ·/);
elements.oscope.value='om_title_plus_indefinite';elements.oscope.events.change();
for(const amount of ['$338.098474B','$338.459009B','$342.358161B','$350.101702B'])assert.ok(compare().includes(amount));
assert.match(rendered(elements.oother),/3.940452B/);
assert.match(elements.oguide.textContent,/41.3M/);
elements.ofiscal.value='2026';elements.ofiscal.events.change();
assert.match(rendered(elements.oother),/FY2026 · PB26 · Reconciliation request · TOA \$22\.708023B.*FY2026 · PB27 · P\.L\. 119-21 spend plan · TOA \$19\.991335B/);
elements.ofiscal.value='2024';elements.ofiscal.events.change();
assert.match(elements.oguide.textContent,/not an enacted or actual amount/);
elements.ovintage.value='pb25';elements.ovintage.events.change();
assert.match(elements.ocount.textContent,/20 of 434/);
elements.omore.click();
assert.match(elements.ocount.textContent,/40 of 434/);
elements.oorganization.value='DEFW';elements.oorganization.events.change();
assert.match(elements.ocount.textContent,/matching lines/);
elements.oorganization.value='';elements.oorganization.events.change();
elements.oaccount.value='0100D';elements.oaccount.events.change();
elements.osearch.value='490';elements.osearch.events.input();
assert.match(rendered(elements.olines),/FY2024 · PB25 · CR-adjusted request · TOA.*−\$1,288.238M/);
assert.match(elements.olines.children[0].children[3].href,/#page=\d+$/);
elements.osearch.value='impossible match token';elements.osearch.events.input();
assert.match(elements.ocount.textContent,/No matching lines/);
elements.nav.children[1].click();
assert.equal(elements.chart.children[0].tag,'svg');
elements.dep.value='Defense-Wide';elements.dep.events.change();
assert.equal(elements.hcontext.hidden,false);
assert.match(elements.hcontext.children[0].textContent,/10\.636B/);
elements.nav.children[2].click();
assert.equal(elements.history.hidden,true); assert.equal(elements.variance.hidden,false);
assert.equal(elements.vt.children[1].children.length,4);
elements.vy.value='2003';elements.vb.value='Current';elements.vy.events.change();
const defenseWide=()=>elements.vt.children[1].children.find(r=>r.children[0].textContent==="Defense-Wide").children;
assert.equal(defenseWide()[3].textContent,"+10,258");
elements.vy.value="2011";elements.vy.events.change();
assert.equal(defenseWide()[1].textContent,"110,407");
assert.equal(defenseWide()[3].textContent,"-2,005");
assert.equal(d.history.find(r=>r.year===2003&&r.dep==="DoD total"&&r.basis==="Current").v,437801);
elements.vy.value="1991";elements.vy.events.change();
assert.equal(defenseWide()[1].textContent,"-10,636");
assert.equal(defenseWide()[3].textContent,"-32,034");
assert.equal(elements.vcontext.hidden,false);
assert.equal(defenseWide()[4].textContent,"Unavailable");
elements.vy.value="1992";elements.vy.events.change();
assert.equal(defenseWide()[3].textContent,"+45,858");
assert.equal(defenseWide()[4].textContent,"Unavailable");
// Renderer-only boundary check: FY1948 has no prior year and is not an option
// in the real variance dropdown. This fake select can exercise that fallback.
elements.vy.value="1948";elements.vy.events.change();
assert.ok(elements.vt.children[1].children.every(r=>r.children[3].textContent==="Unavailable"));
elements.nav.children[3].click();
assert.ok(elements.at.children[1].children.length>0);
elements.at.children[1].children[0].children[0].children[0].click();
assert.equal(elements.detail.hidden,false);
assert.ok(elements.detail.children.at(-1).href.startsWith('https://comptroller.'));
elements.aq.value='nonsuch search phrase';elements.aq.events.input();
assert.equal(elements.at.children[1].children.length,0);
elements.nav.children[4].click();
assert.equal(elements.pipeline.hidden,false);assert.ok(elements.pc.children.length>=5);
assert.ok(!/<(?:script|link)[^>]+(?:src|href)=/i.test(html));
console.log('Offline DOM smoke passed: O-1 exact stage comparisons, organization/account/search, pagination, source links, legacy tabs, nominal FY2003 and FY2011 corrections, historical gaps, program click, no-match search, sources.');
