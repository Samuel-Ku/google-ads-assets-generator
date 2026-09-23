const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const window = {};
const context = vm.createContext({window, URL, console});
for (const file of ['canvas.js', 'sync.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../static', file), 'utf8'), context);
const C = window.StudioCanvas, S = window.StudioSync;
const copy = value => JSON.parse(JSON.stringify(value));
const formats = [
  {id:'display_300x250',width:300,height:250,profile:'display'},
  {id:'display_160x600',width:160,height:600,profile:'display'},
  {id:'rda_1200x628',width:1200,height:628,profile:'rda'},
  {id:'logo_1200x300',width:1200,height:300,profile:'logos'},
];
function setup() {
  const master = C.makeScene({width:1200,height:900,template:'split',product:{id:'one',url:'/api/assets/one/file'},headline:'Pierwszy',cta:'Sprawdź'});
  master.layers.push({id:'product-two',type:'image',role:'product',asset_id:'two',src:'/api/assets/two/file',x:.7,y:.5,w:.2,h:.2});
  const state = {sync_formats:true,template:'split',scene:copy(master),template_scenes:{split:copy(master),spotlight:{unchanged:true}},scenes:{},headlines:['Pierwszy','Drugi'],ctas:['Sprawdź'],descriptions:[]};
  return {state,master};
}
function edit(state, formatId, before, after, masterScene) {
  S.applyEdit(state,{template:'split',formatId,before,after,masterScene,formats,adaptScene:C.adaptScene});
}
function layer(scene,id) { return scene.layers.find(item=>item.id===id); }

{
  const {state,master}=setup(), after=copy(master);
  Object.assign(layer(after,'cta'),{cornerRadius:.5,borderWidth:4,borderColor:'#FF0000'});
  layer(after,'headline').text='Nowy tekst';
  layer(after,'product-two').x+=.05;
  edit(state,'master',master,after,master);
  for (const format of formats.filter(f=>f.profile==='display')) {
    const scene=state.scenes['split:'+format.id];
    assert.equal(layer(scene,'cta').cornerRadius,.5);
    assert.equal(layer(scene,'headline').text,'Nowy tekst');
    assert(Math.abs(layer(scene,'cta').borderWidth-4*format.height/900)<1e-9);
    assert(layer(scene,'product-two'));
  }
  assert.equal(state.headlines[0],'Nowy tekst');
  assert.equal(state.headlines[1],'Drugi');
  assert.equal(state.template_scenes.spotlight.unchanged,true);
  assert(!state.scenes['split:logo_1200x300']);
  assert(state.scenes['split:rda_1200x628'].layers.every(l=>['product','background'].includes(l.role)));
}
{
  const {state,master}=setup();
  const before=C.adaptScene(master,300,250),after=copy(before);
  const portrait=C.adaptScene(master,160,600);
  layer(portrait,'product').x=.123;
  state.scenes['split:display_160x600']=copy(portrait);
  layer(after,'cta').backgroundColor='#123456';
  layer(after,'product-two').src='/api/assets/cutout/file';
  layer(after,'product-two').asset_id='cutout';
  edit(state,'display_300x250',before,after,master);
  assert.equal(layer(state.template_scenes.split,'cta').backgroundColor,'#123456');
  assert.equal(layer(state.scenes['split:display_160x600'],'product').x,.123);
  assert.equal(layer(state.template_scenes.split,'product-two').asset_id,'cutout');
  assert.equal(layer(state.template_scenes.split,'product').asset_id,'one');
}
{
  const {state,master}=setup();state.sync_formats=false;
  const before=C.adaptScene(master,300,250),after=copy(before);
  layer(after,'headline').text='Tylko ten rozmiar';
  edit(state,'display_300x250',before,after,master);
  assert.equal(layer(state.scenes['split:display_300x250'],'headline').text,'Tylko ten rozmiar');
  assert.equal(layer(state.template_scenes.split,'headline').text,'Pierwszy');
  assert.equal(state.headlines[0],'Pierwszy');
  assert.equal(Object.keys(state.scenes).length,1);
}
{
  const {state,master}=setup();state.sync_formats=false;
  const beforePortrait=C.adaptScene(master,160,600),after=copy(master);
  const savedOverride=C.adaptScene(master,300,250);
  layer(savedOverride,'product').opacity=.77;
  state.scenes['split:display_300x250']=copy(savedOverride);
  layer(after,'product').opacity=.2;
  edit(state,'master',master,after,master);
  assert.equal(layer(state.template_scenes.split,'product').opacity,.2);
  assert(state.scenes['split:display_160x600'],'Previously lazy formats must receive a frozen snapshot.');
  assert.deepEqual(copy(state.scenes['split:display_160x600']),copy(beforePortrait),
    'An isolated master edit must freeze previously lazy formats before changing their source.');
  assert.deepEqual(copy(state.scenes['split:display_300x250']),copy(savedOverride),
    'Existing per-format overrides remain untouched during isolated master edits.');
  assert(!state.scenes['split:logo_1200x300']);
}
{
  const {state,master}=setup();
  const wide=C.adaptScene(master,728,90),after=copy(wide);
  layer(after,'product').x+=.15;
  assert(layer(after,'product').x+layer(after,'product').w<=1,'Source edit fits the wide banner.');
  edit(state,'display_728x90',wide,after,master);
  const portrait=state.scenes['split:display_160x600'];
  const original=C.adaptScene(master,160,600);
  assert(layer(portrait,'product').x+layer(portrait,'product').w<=1,
    'A valid wide-banner movement must not push the portrait product off canvas.');
  assert.equal(layer(portrait,'product').w,layer(original,'product').w);
  assert.equal(layer(portrait,'product').y,layer(original,'product').y);
  assert.equal(layer(portrait,'product').h,layer(original,'product').h);
}
{
  const {state,master}=setup(),after=copy(master);
  const portrait=C.adaptScene(master,160,600);
  layer(portrait,'product').x=.123;
  layer(portrait,'product').y=-.02;
  state.scenes['split:display_160x600']=copy(portrait);
  layer(after,'product').w*=2;
  edit(state,'master',master,after,master);
  const result=layer(state.scenes['split:display_160x600'],'product');
  assert.equal(result.w,1,'Linked resizes cap only the edited dimension to the target canvas.');
  assert.equal(result.x,0);
  assert.equal(result.y,-.02,'An unrelated pre-existing vertical override is retained.');
  assert.equal(result.h,layer(portrait,'product').h);
}
{
  const {state,master}=setup(),after=copy(master);
  after.layers=after.layers.filter(l=>l.id!=='product-two');
  after.layers.push({id:'element-badge',type:'image',role:'element',src:'/api/assets/badge/file',asset_id:'badge',x:.1,y:.1,w:.15,h:.1});
  edit(state,'master',master,after,master);
  assert(!layer(state.scenes['split:display_160x600'],'product-two'));
  assert(layer(state.scenes['split:display_160x600'],'element-badge'));
  assert(!layer(state.scenes['split:rda_1200x628'],'element-badge'));
}
{
  const {state,master}=setup(),before=C.adaptScene(master,1200,628,{clean:true}),after=copy(before);
  layer(after,'product').opacity=.6;
  delete state.template_scenes.split; delete state.scene;
  edit(state,'rda_1200x628',before,after,master);
  assert(layer(state.template_scenes.split,'headline'),'Clean-image edits must not erase master copy/CTA.');
  assert.equal(layer(state.template_scenes.split,'product').opacity,.6);
}
console.log('PASS: linked format edits, isolated edits, material identity, style scaling, clean profiles and master preservation.');
