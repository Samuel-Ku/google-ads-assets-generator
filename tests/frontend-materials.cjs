'use strict';
// Run the production app helpers with a minimal DOM and the real scene generator.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const element=()=>({innerHTML:'',textContent:'',disabled:false,hidden:false,querySelectorAll(){return [];},addEventListener(){},scrollIntoView(){},showModal(){},classList:{toggle(){}},click(){},remove(){},close(){}});
const nodes=new Map(['#app','#dialog','#toast','#export-summary','#export-issues','#export-progress','#download-list','#properties'].map(key=>[key,element()]));
const document={querySelector:s=>nodes.get(s)||null,querySelectorAll:()=>[],addEventListener(){},createElement:()=>element(),body:{append(){}}};
let syncCall;
const context={console,document,URL,setTimeout:()=>0,clearTimeout(){},requestAnimationFrame:callback=>callback(),FormData:class{constructor(){this.parts=[];}append(...args){this.parts.push(args);}},window:{addEventListener(){},StudioSync:{applyEdit(state,edit){syncCall={state,edit};}}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'static/canvas.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'static/template-recipes.js'),'utf8'),context);
let source=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
source=source.replace('  boot();',`  window.__test={R,normalizeState,sceneBase,currentScene,storeScene,initComposition,undoSceneEdit,snapshotSceneState,toggleMaterial,replaceMaterial,originalMaterial,materialKind,selectedMaterialIds,templateMaterials,assetCard,materialsMarkup,brandDialog,removeBackground,maskDialog,renderLayers,renderProperties,action,exportPlan,exportScene,runExport,deleteMaterialDialog,deleteMaterial,deletionImpact,compositionNames,reconcileUnavailableMedia,openCampaign,useServices(services){api=services.api;saveCampaign=services.saveCampaign;refreshStorage=async()=>{};}};`);
vm.runInContext(source,context);
const api=context.window.__test;
const {R}=api;
const clone=value=>JSON.parse(JSON.stringify(value));
const ids=scene=>scene.layers.filter(layer=>layer.role==='product').map(layer=>String(layer.asset_id));
const asset=(id,kind='product',parent_id=null)=>({id,kind,parent_id,url:'/api/assets/'+id+'/file',name:id+'.png',width:1000,height:800,size:200});
R.brands=[{id:'brand',name:'AMSO',color:'#ff7700',secondary_color:'#fafafa',text_color:'#111111',font_family:'Arial'}];
const p1=asset('p1'),p2=asset('p2'),p3=asset('p3'),p4=asset('p4'),sticker=asset('label','element');
R.campaign={id:'test',brand_id:'brand',assets:[p1,p2,p3,p4,sticker],exports:[],state:api.normalizeState({product_asset_id:'p1',headlines:['Oferta'],ctas:['Sprawdź'],descriptions:['Opis'],long_headline:'Długa oferta',business_name:'AMSO',confirmed:true})};
assert.deepEqual(clone(R.campaign.state.product_asset_ids),['p1'],'Legacy single product migrates.');
assert.equal(R.campaign.state.sync_formats,true);
assert.equal(api.normalizeState({sync_formats:false}).sync_formats,false);
api.toggleMaterial('product',p2);api.toggleMaterial('product',p3);api.toggleMaterial('element',sticker);
assert.deepEqual(clone(R.campaign.state.product_asset_ids),['p1','p2','p3']);
let master=api.sceneBase();
assert.deepEqual(clone(ids(master)),['p1','p2','p3']);
assert(master.layers.some(layer=>layer.role==='element'&&layer.asset_id==='label'));
R.campaign.state.template_scenes.split=clone(master);
R.campaign.state.scene=clone(master);
R.campaign.state.scenes['split:display_300x250']=context.window.StudioCanvas.adaptScene(master,300,250);
R.campaign.state.scenes['split:rda_1200x1200']=context.window.StudioCanvas.adaptScene(master,1200,1200,{clean:true});
const p2Cut=asset('p2-cut','cutout','p2');R.campaign.assets.push(p2Cut);
const stableLayer=master.layers.find(layer=>layer.asset_id==='p2').id;
api.replaceMaterial(p2,p2Cut);
assert.deepEqual(clone(R.campaign.state.product_asset_ids),['p1','p2-cut','p3']);
for(const scene of [R.campaign.state.scene,...Object.values(R.campaign.state.template_scenes),...Object.values(R.campaign.state.scenes)]){
 assert.deepEqual(clone(ids(scene)),['p1','p2-cut','p3'],'Only the matching product is replaced in every scene.');
 assert.equal(scene.layers.find(layer=>layer.asset_id==='p2-cut').id,stableLayer,'Layer identity is stable for synchronization.');
}
api.toggleMaterial('product',p1);
assert.deepEqual(clone(R.campaign.state.product_asset_ids),['p2-cut','p3']);
assert.equal(R.campaign.state.product_asset_id,'p2-cut');
api.toggleMaterial('product',p4);
assert.deepEqual(clone(ids(R.campaign.state.scene)),['p2-cut','p3','p4']);
const cutLabel=asset('label-cut','element','label');R.campaign.assets.push(cutLabel);api.replaceMaterial(sticker,cutLabel);
assert.deepEqual(clone(R.campaign.state.element_asset_ids),['label-cut']);
assert.equal(api.materialKind(cutLabel),'element');
const editedLabel=asset('label-edit','element','label-cut');R.campaign.assets.push(editedLabel);api.replaceMaterial(cutLabel,editedLabel);
assert.equal(api.originalMaterial(editedLabel).id,'label','Original remains recoverable through parent chain.');
assert.equal(api.materialKind(editedLabel),'element');
assert(!R.campaign.state.scenes['split:rda_1200x1200'].layers.some(layer=>layer.role==='element'),'Labels stay out of clean assets.');
api.toggleMaterial('element',editedLabel);
assert.equal(R.campaign.state.element_asset_ids.length,0);
assert(!R.campaign.state.scene.layers.some(layer=>layer.role==='element'));
assert(api.assetCard(p2Cut).includes('aria-pressed="true"'));
assert(api.assetCard(p2Cut).includes('data-action="edit-mask"'),'Raster cutouts keep mask editing.');
const svg=asset('vector','element');svg.mime='image/svg+xml';svg.name='label.svg';R.campaign.assets.push(svg);
const svgCard=api.assetCard(svg);
assert(svgCard.includes('Element · SVG'),'SVG materials are identified as vectors.');
assert(svgCard.includes('data-action="select-asset"'),'SVG remains usable in compositions.');
assert(!svgCard.includes('data-action="remove-background"')&&!svgCard.includes('data-action="edit-mask"'),'Vector cards must not offer raster processing.');
assert(svgCard.includes('Zmień tło w pliku źródłowym.'));
assert(api.materialsMarkup().includes('image/svg+xml,.svg'),'Campaign uploader accepts SVG.');
assert(api.materialsMarkup().includes('SVG · do 2 MB'),'SVG size limit is visible.');
api.brandDialog();
assert(nodes.get('#dialog').innerHTML.includes('image/svg+xml,.svg'),'Brand logo uploader accepts SVG.');
assert(nodes.get('#dialog').innerHTML.includes('SVG do 2 MB'));
const before=api.currentScene();const after=clone(before);after.background='#abcdef';api.storeScene(after);
assert.equal(syncCall.edit.before.background,before.background);
assert.equal(syncCall.edit.after.background,'#abcdef');
assert.equal(syncCall.edit.masterScene.width,1200);
assert.equal(syncCall.edit.masterScene.height,900);
R.editor={getScene:()=>before};api.renderProperties(before.layers.find(layer=>layer.role==='cta'));R.editor=null;
assert(nodes.get('#properties').innerHTML.includes('data-prop="cornerRadius"'));
assert(nodes.get('#properties').innerHTML.includes('data-prop="backgroundColor"'));
assert(nodes.get('#properties').innerHTML.includes('data-prop="borderWidth"'));
// Saved slots bind by material order, never by the independently edited stacking
// order of each format. A deliberately absent override slot stays absent.
{
 const previousCampaign=R.campaign,C=context.window.StudioCanvas,T=context.window.StudioTemplates;
 const sourceScene=C.makeScene({brand:R.brands[0],products:[p1,p2,p3],elements:[sticker,asset('label2','element')],headline:'Old source copy'});
 const sourceOverride=C.adaptScene(sourceScene,300,250);sourceOverride.layers.reverse();
 const omittedOverride=C.adaptScene(sourceScene,160,600);omittedOverride.layers=omittedOverride.layers.filter(layer=>String(layer.asset_id)!=='p2');
 const recipe=T.capture({master:sourceScene,formats:{display_300x250:sourceOverride,display_160x600:omittedOverride}});
 const bound=T.instantiate(recipe,{brand:R.brands[0],products:[p1],headline:'Nowa oferta'});
 const expiredBackground={...asset('expired-background','background'),expired:true};
 const secondElement=asset('label2','element');
 R.campaign={id:'slot-regression',brand_id:'brand',assets:[p1,p2,p3,sticker,secondElement,expiredBackground],exports:[],state:api.normalizeState({product_asset_ids:['p1'],background_asset_id:expiredBackground.id,scene:clone(bound.master),template_scenes:{split:clone(bound.master)},scenes:{'split:display_300x250':bound.formats.display_300x250,'split:display_160x600':bound.formats.display_160x600}})};
 assert.equal(api.templateMaterials().background,null,'Expired current campaign background is an empty slot, not a stale file URL.');
 api.toggleMaterial('product',p2);
 for(const scene of [R.campaign.state.scene,R.campaign.state.template_scenes.split,R.campaign.state.scenes['split:display_300x250']]){
  assert.equal(scene.layers.find(layer=>layer.id==='product-slot-2').asset_id,'p2','Second selected product fills slot 2 even when stacking order is reversed.');
  assert.equal(scene.layers.find(layer=>layer.id==='product-slot-3').missingSlot,'product:2');
 }
 assert(!R.campaign.state.scenes['split:display_160x600'].layers.some(layer=>layer.asset_id==='p2'),'A slot omitted in one override must not fill a different placeholder or be recreated.');
 api.toggleMaterial('product',p3);
 for(const scene of [R.campaign.state.scene,...Object.values(R.campaign.state.scenes)])assert.equal(scene.layers.find(layer=>layer.id==='product-slot-3').asset_id,'p3');
 api.toggleMaterial('element',sticker);
 for(const scene of [R.campaign.state.scene,...Object.values(R.campaign.state.scenes)]){
  assert.equal(scene.layers.find(layer=>layer.id==='element-slot-1').asset_id,'label');
  assert.equal(scene.layers.find(layer=>layer.id==='element-slot-2').missingSlot,'element:1');
 }
 api.toggleMaterial('element',secondElement);
 for(const scene of [R.campaign.state.scene,...Object.values(R.campaign.state.scenes)])assert.equal(scene.layers.find(layer=>layer.id==='element-slot-2').asset_id,'label2');
 R.campaign=previousCampaign;
}
R.formats={display:[{id:'display_300x250',width:300,height:250,profile:'display',label:'300 × 250',max_bytes:153600}],rda:[{id:'rda_1200x1200',width:1200,height:1200,profile:'rda',label:'Kwadrat',max_bytes:5000000}]};
const click=action=>api.action({target:{closest:()=>({dataset:{action}})}});
async function main(){
 const dialogBeforeSVG=nodes.get('#dialog').innerHTML;
 await api.removeBackground(svg.id);
 assert(nodes.get('#toast').textContent.includes('Zmień tło w pliku źródłowym.'),'SVG background removal exits before making an API call.');
 await api.maskDialog(svg.id);
 assert.equal(nodes.get('#dialog').innerHTML,dialogBeforeSVG,'SVG does not enter the raster mask editor.');
 // Use the real propagation module for undo: reverse deltas cannot recover
 // geometry lost when deleting a layer or clamping a linked format at an edge.
 vm.runInContext(fs.readFileSync(path.join(root,'static/sync.js'),'utf8'),context);
 R.undo=[];R.editorFormat='master';
 const overridden=R.campaign.state.scenes['split:display_300x250'].layers.find(layer=>layer.asset_id==='p3');
 overridden.x=.77;overridden.y=.31;overridden.w=.17;overridden.h=.29;overridden.cropX=.24;
 const savedOverrides=clone(api.snapshotSceneState());
 let visible=api.currentScene();
 R.editor={getScene:()=>clone(visible),setScene:scene=>{visible=clone(scene);}};
 const withoutThird=api.currentScene();withoutThird.layers=withoutThird.layers.filter(layer=>layer.asset_id!=='p3');
 api.storeScene(withoutThird);
 assert(!R.campaign.state.scenes['split:display_300x250'].layers.some(layer=>layer.asset_id==='p3'));
 R.campaign.state.business_name='Unrelated change';
 // Re-create the actual editor in another format before invoking undo.
 for(const id of ['#scene-size','#sync-formats','#scene-background','#editor-format','#editor-canvas'])nodes.set(id,element());
 const realCanvas=context.window.StudioCanvas;
 context.window.StudioCanvas={...realCanvas,render:async()=>{},Editor:class{constructor(node,options){this.scene=clone(options.scene);}getScene(){return clone(this.scene);}setScene(scene){this.scene=clone(scene);}destroy(){}}};
 R.editorFormat='display_300x250';
 await api.initComposition();
 assert.equal(R.undo.length,1,'Recreating the editor for another format must preserve undo history.');
 api.undoSceneEdit();
 assert.equal(R.editor.getScene().width,300,'Undo keeps the currently viewed format.');
 assert.equal(R.editor.getScene().layers.find(layer=>layer.asset_id==='p3').cropX,.24,"Undo from another format restores that format's original crop.");
 R.editorFormat='master';
 assert.deepEqual(clone(api.snapshotSceneState()),savedOverrides,'Undo deletion restores every original format override exactly.');
 assert.equal(R.campaign.state.business_name,'Unrelated change','Undo must preserve unrelated campaign fields.');
 const edgeEdit=api.currentScene();edgeEdit.layers.find(layer=>layer.asset_id==='p3').x=.95;
 edgeEdit.layers.find(layer=>layer.role==='headline').text='Changed headline';
 api.storeScene(edgeEdit);
 assert.equal(R.campaign.state.headlines[0],'Changed headline');
 const linked=R.campaign.state.scenes['split:display_300x250'].layers.find(layer=>layer.asset_id==='p3');
 assert(linked.x+linked.w<=1.000001,'The target format hits its geometry bound.');
 api.undoSceneEdit();
 assert.deepEqual(clone(api.snapshotSceneState()),savedOverrides,'Undo restores pre-clamp geometry and text library, not an inverse delta.');
 assert.equal(R.undo.length,0);
 R.editor=null;R.campaign.state.business_name='AMSO';
 await click('formats-all');assert.equal(R.campaign.state.selected_formats.length,2);
 await click('formats-none');assert.equal(R.campaign.state.selected_formats.length,0);
 await click('templates-all');assert.deepEqual(clone(R.campaign.state.selected_templates),clone(context.window.StudioCanvas.templates.map(t=>t.id)),'Bulk selection includes every built-in layout.');
 await click('templates-none');assert.equal(R.campaign.state.selected_templates.length,0);
 R.busy=true;await click('formats-all');assert.equal(R.campaign.state.selected_formats.length,0,'Busy export blocks bulk changes.');R.busy=false;
 R.campaign.state.selected_templates=['split'];R.campaign.state.selected_formats=['display_300x250'];R.campaign.state.ctas=['Sprawdź','Kup teraz'];
 let submitted;
 api.useServices({saveCampaign:async()=>true,api:async(url,options)=>{submitted=options.body;return {id:'export',url:'/download',size:100,file_count:2};}});
 const canvas=context.window.StudioCanvas;context.window.StudioCanvas={...canvas,renderBlob:async()=>({blob:{size:25}})};
 await api.runExport();
 assert(submitted,'Export should submit its rendered files.');
 const fileParts=submitted.parts.filter(part=>part[0]==='files');
 assert.deepEqual(fileParts.map(part=>part[2]),['300x250.jpg','300x250.jpg'],'Variants retain dimension-only filenames.');
 const manifest=JSON.parse(submitted.parts.find(part=>part[0]==='manifest')[1]);
 assert.deepEqual(manifest.map(item=>item.variant),['h1-cta1','h1-cta2'],'Variant identity remains in manifest for separate ZIP directories.');
 assert.equal(R.busy,false);
 // ---- Issue #2: distinct Polish delete-file action on campaign material cards ----
 {
  const card=api.assetCard(p2Cut);
  assert(card.includes('data-action="delete-asset"'),'Material cards expose a delete-file action.');
  assert(card.includes('Usuń plik'),'The delete action is labelled in Polish.');
  const brandCard={id:'brand-logo',kind:'logo',brand_id:'brand',name:'logo.png',url:'/api/assets/brand-logo/file',mime:'image/png',width:10,height:10,size:5};
  assert(!api.assetCard(brandCard).includes('data-action="delete-asset"'),'Brand Kit files must not offer campaign deletion.');
 }
 // Cancel resolves without any change; confirm carries the disclosure payload.
 {
  const dialogEl=nodes.get('#dialog');
  dialogEl.close=()=>{};
  nodes.set('#confirm-ok',element());nodes.set('#confirm-cancel',element());
  const pending=api.deleteMaterialDialog({id:'p3-cut',name:'p3-cut.png',kind:'cutout',parent_id:'p3',size:120,width:1000,height:800,url:'/api/assets/p3-cut/file'},[{id:'p3-cut',name:'p3-cut.png',kind:'cutout',parent_id:'p3',size:120,width:1000,height:800,url:'/api/assets/p3-cut/file'}],['Kompozycja bazowa','split:display_300x250']);
  await Promise.resolve();
  const shown=dialogEl.innerHTML;
  assert(shown.includes('p3-cut.png'),'Confirmation identifies the selected file.');
  assert(shown.includes('Kompozycja bazowa'),'Confirmation lists affected compositions.');
  assert(shown.includes('trwale')||shown.includes('trwałe'),'Confirmation explains permanence.');
  nodes.get('#confirm-cancel').onclick();
  assert.equal(await pending,false,'Dialog resolves false when the editor cancels.');
 }
 // Deleting a selected leaf cutout reconciles selections and scenes.
 {
  R.campaign.version=6;
  R.campaign.state.product_asset_ids=['p2-cut','p3'];R.campaign.state.product_asset_id='p2-cut';
  for(const scene of [R.campaign.state.scene,R.campaign.state.template_scenes.split,R.campaign.state.scenes['split:display_300x250']]){
   scene.layers=scene.layers.filter(layer=>layer.role!=='product'||layer.asset_id!=='p3');
  }
  let calledApi=null;
  function services_saveCampaignStub(){throw new Error('Deletion must not trigger an extra save roundtrip.');}
  api.useServices({saveCampaign:services_saveCampaignStub,api:async(url,options)=>{
   calledApi={url,method:options?.method,body:options?.body};
   return {version:7,deleted_ids:['p2-cut'],updated_by:'admin'};
  }});
  const p2cut=asset('p2-cut','cutout','p2');
  const pendingDelete=api.deleteMaterial(p2cut,api.deletionImpact(p2cut));
  await Promise.resolve();await Promise.resolve();
  const dialogEl=nodes.get('#dialog');
  assert(dialogEl.innerHTML.includes('Usuń plik'),'Confirm button uses the Polish delete wording.');
  nodes.get('#confirm-ok').onclick();
  await pendingDelete;
  assert(calledApi&&calledApi.method==='DELETE'&&calledApi.url==='/api/campaigns/test/assets/p2-cut','Deletion calls the campaign-scoped asset endpoint.');
  assert.equal(calledApi.body.version,6,'Deletion sends the current campaign version.');
  assert.deepEqual(clone(R.campaign.state.product_asset_ids),['p3'],'Selection drops the deleted id only.');
  assert.equal(R.campaign.state.product_asset_id,'p3','Legacy mirror follows the first survivor.');
  assert.equal(R.campaign.version,7,'The authored revision from the server is adopted.');
  for(const scene of [R.campaign.state.scene,R.campaign.state.template_scenes.split,R.campaign.state.scenes['split:display_300x250']]){
   const layer=scene.layers.find(layer=>String(layer.asset_id)==='p2-cut'||layer.asset_id===null&&layer.src===null&&layer.role==='product');
   assert(layer,'The emptied layer keeps its slot in every stored scene.');
   assert(scene.layers.every(entry=>String(entry.asset_id)!=='p2-cut'),'No scene keeps a usable reference to the deleted file.');
  }
  assert(nodes.get('#toast').textContent.includes('Usunięto'),'A Polish success toast confirms deletion.');
 }
 // Unavailable references are reconciled on open, restore and undo, with a warning.
 {
  R.user={id:1,username:'admin',role:'admin'};
  const state={confirmed:true,product_asset_ids:['ghost'],product_asset_id:'ghost',scene:{template:'split',width:1200,height:900,background:'#ffffff',layers:[{id:'product-slot-1',type:'image',role:'product',x:.1,y:.1,w:.4,h:.5,src:'/api/assets/ghost/file',asset_id:'ghost'}]},template_scenes:{},scenes:{},selected_templates:['split'],selected_formats:[]};
  api.useServices({saveCampaign:async()=>true,api:async(url)=>({version:9,state})});
  R.dirty=false;
  await api.openCampaign('test');
  const s=R.campaign.state;
  assert.deepEqual(clone(s.product_asset_ids),[],'Selections of deleted files are cleared on open.');
  const layer=s.scene.layers.find(layer=>layer.id==='product-slot-1');
  assert(layer&&layer.src===null&&layer.asset_id===null,'Saved layers keep their slot without a usable file reference.');
  assert(!R.dirty,'Reconciliation is persisted through the follow-up save, not flagged as local edits.');
 }
 // ---- Issue #6: native Shape layers are independent, editable and undoable ----
 {
  const C=context.window.StudioCanvas;
  R.campaign.brand_id='brand';
  R.editorFormat='master';R.undo=[];
  let visible=api.currentScene();
  // Mirror the real Editor wiring: addLayer/select notify through onChange/storeScene.
  R.editor={getScene:()=>clone(visible),setScene:scene=>{visible=clone(scene);},select:()=>{},
    addLayer:layer=>{visible.layers.push(clone(layer));api.storeScene(clone(visible));},
    removeSelected:()=>{}};
  await api.action({target:{closest:()=>({dataset:{action:'add-shape',shape:'square'}})}});
  const added=visible.layers.find(layer=>layer.role==='shape');
  assert(added&&added.id==='shape-1','Add-shape creates a stably identified layer.');
  assert.equal(added.shape,'square');
  assert.equal(added.color,'#ff7700','New shapes start from the Brand Kit accent.');
  assert(!('src' in added)&&!('asset_id' in added),'Shapes consume no uploaded-material slots.');
  assert(R.campaign.state.template_scenes.split.layers.some(layer=>layer.id==='shape-1'),'Added shapes persist through the sync seam.');
  // Layer list and properties distinguish shapes from uploaded Elements.
  nodes.set('#layer-list',element());
  R.selectedLayer=null;api.renderLayers();
  assert(nodes.get('#layer-list').innerHTML.includes('Kształt · Kwadrat'),'Layer list names the shape kind.');
  api.renderProperties(added);
  const props=nodes.get('#properties').innerHTML;
  assert(props.includes('Kwadrat')&&props.includes('data-prop="color"')&&props.includes('data-prop="opacity"')&&props.includes('data-prop="radius"'),'Shape properties expose fill, opacity and corner styling.');
  // Display export keeps shapes; clean RDA strips them.
  const displayScene=api.exportScene({f:{id:'display_300x250',width:300,height:250,profile:'display',label:'Display',max_bytes:153600},template:'split',headline:'H',description:'D',cta:'C',variant:'h1-cta1',mode:''});
  assert(displayScene.layers.some(layer=>layer.id==='shape-1'),'Display output matches visible shape geometry.');
  const cleanScene=api.exportScene({f:{id:'rda_1200x1200',width:1200,height:1200,profile:'rda',label:'RDA',max_bytes:5000000},template:'split',headline:'',description:'',cta:'',variant:'obraz',mode:''});
  assert(!cleanScene.layers.some(layer=>layer.role==='shape'),'Clean outputs exclude shape overlays.');
  // Delete then undo restores the exact prior state.
  const withoutShape=clone(visible);withoutShape.layers=withoutShape.layers.filter(layer=>layer.id!=='shape-1');
  visible=clone(withoutShape);api.storeScene(clone(withoutShape));
  assert(!R.campaign.state.template_scenes.split.layers.some(layer=>layer.id==='shape-1'));
  api.undoSceneEdit();
  assert(R.campaign.state.template_scenes.split.layers.some(layer=>layer.id==='shape-1'),'Undo restores deleted shapes.');
  api.undoSceneEdit();
  assert(!api.currentScene().layers.some(layer=>layer.id==='shape-1'),'Second undo removes the added shape again.');
  // Every shape button keeps its own kind instead of collapsing to a rectangle.
  for(const kind of ['rectangle','square','circle','ellipse','triangle','diamond']){
    await api.action({target:{closest:()=>({dataset:{action:'add-shape',shape:kind}})}});
    const created=visible.layers.find(layer=>layer.id==='shape-1');
    assert.equal(created&&created.shape,kind,'Add-shape creates a '+kind+' layer.');
    const cleaned=clone(visible);cleaned.layers=cleaned.layers.filter(layer=>layer.id!=='shape-1');
    visible=clone(cleaned);api.storeScene(clone(cleaned));
  }
  R.undo=[];
  R.editor=null;
 }
 // ---- Issue #3: cascade deletion with disclosed derived files ----
 {
  R.campaign={id:'test',brand_id:'brand',assets:[asset('p1'),asset('p2')],exports:[],version:8,state:api.normalizeState({product_asset_ids:['p1','p2'],headlines:['Oferta'],ctas:['Sprawdź'],descriptions:['Opis'],long_headline:'Długa oferta',business_name:'AMSO',confirmed:true})};
  R.campaign.state.template_scenes={split:{template:'split',width:1200,height:900,background:'#ffffff',layers:[{id:'cutout-slot',type:'image',role:'product',x:.1,y:.1,w:.3,h:.3,src:'/api/assets/p2-cut/file',asset_id:'p2-cut'},{id:'mask-slot',type:'image',role:'product',x:.5,y:.1,w:.2,h:.2,src:'/api/assets/p2-mask/file',asset_id:'p2-mask'}]}};
  R.campaign.state.scenes={};
  R.campaign.state.scene=clone(R.campaign.state.template_scenes.split);
  // Multi-generation subtree: p2 → p2-cut → p2-mask; sibling p2-side survives.
  const p2cut=asset('p2-cut','cutout','p2'),p2mask=asset('p2-mask','cutout','p2-cut'),p2side=asset('p2-side','cutout','p2');
  R.campaign.assets=[...R.campaign.assets,p2cut,p2mask,p2side];
  R.campaign.version=8;
  R.campaign.state.template_scenes.split.layers.push({id:'cutout-slot',type:'image',role:'product',x:.1,y:.1,w:.3,h:.3,src:p2cut.url,asset_id:'p2-cut'});
  R.campaign.state.template_scenes.split.layers.push({id:'mask-slot',type:'image',role:'product',x:.5,y:.1,w:.2,h:.2,src:p2mask.url,asset_id:'p2-mask'});
  const impact=api.deletionImpact(asset('p2'));
  assert.deepEqual(clone(impact.descendants),['p2-cut.png','p2-mask.png','p2-side.png'],'Impact discloses every derived generation by name.');
  assert.deepEqual(clone(impact.descendantIds),['p2-cut','p2-mask','p2-side'],'Impact ids cover the whole subtree.');
  assert(impact.compositions.includes('Kompozycja bazowa'),'Compositions using affected files are disclosed.');
  const leafImpact=api.deletionImpact(p2cut);
  assert.deepEqual(clone(leafImpact.descendants),['p2-mask.png'],'Deleting a cutout discloses only its own descendants.');
  // Dialog shows the cascade warning.
  {
   const dialogEl=nodes.get('#dialog');
   const pending=api.deleteMaterialDialog(asset('p2'),impact.descendants,impact.compositions);
   await Promise.resolve();
   const shown=dialogEl.innerHTML;
   assert(shown.includes('razem z plikami pochodnymi')||shown.includes('pliki pochodne'),'Dialog title discloses the cascade.');
   assert(shown.includes('p2-mask.png'),'Dialog lists the nested derived file.');
   nodes.get('#confirm-cancel').onclick();
   assert.equal(await pending,false,'Cancellation stays side-effect free.');
  }
  // Confirmed cascade sends the exact affected set and reconciles everything.
  let sentBody=null;
  api.useServices({saveCampaign:()=>{throw new Error('No extra save on cascade.');},api:async(url,options)=>{
   sentBody={url,method:options?.method,body:options?.body};
   return {version:9,deleted_ids:['p2','p2-cut','p2-mask','p2-side'],updated_by:'admin'};
  }});
  const p2asset=asset('p2');
  const cascade=api.deleteMaterial(p2asset,api.deletionImpact(p2asset));
  await Promise.resolve();await Promise.resolve();
  nodes.get('#confirm-ok').onclick();
  await cascade;
  assert(sentBody&&sentBody.method==='DELETE'&&sentBody.url==='/api/campaigns/test/assets/p2','Cascade targets the selected original.');
  assert.deepEqual(clone(sentBody.body.confirmed_asset_ids),['p2','p2-cut','p2-mask','p2-side'],'Confirmation carries the exact affected set.');
  assert.equal(sentBody.body.version,8,'Cascade sends the current campaign version.');
  assert(!R.campaign.assets.some(x=>['p2','p2-cut','p2-mask','p2-side'].includes(String(x.id))),'All removed files leave the materials list.');
  assert(R.campaign.assets.some(x=>String(x.id)==='p2-side')===false,'Sibling cutouts inside the subtree are removed.');
  for(const slot of ['cutout-slot','mask-slot']){
   const layer=R.campaign.state.template_scenes.split.layers.find(layer=>layer.id===slot);
   assert(layer&&layer.src===null&&layer.asset_id===null,'Layer '+slot+' keeps its slot without a file reference.');
  }
  assert(nodes.get('#toast').textContent.includes('plikami pochodnymi')||nodes.get('#toast').textContent.includes('Usunięto'),'Success toast covers the cascade.');
 }
 // Changed impact: server requires refreshed confirmation with its exact list.
 {
  const p5=asset('p5'),p5cut=asset('p5-cut','cutout','p5'),p5new=asset('p5-new','cutout','p5-cut');
  R.campaign.assets=[...R.campaign.assets,p5,p5cut,p5new];
  R.campaign.version=10;
  R.campaign.state.template_scenes.split.layers.push({id:'p5-slot',type:'image',role:'product',x:.2,y:.2,w:.2,h:.2,src:p5.url,asset_id:'p5'});
  let attempts=0;
  api.useServices({saveCampaign:async()=>true,api:async(url,options)=>{
   attempts++;
   if(attempts===1)return Promise.reject(Object.assign(new Error('Konflikt'),{status:409,data:{code:'impact_changed',required_asset_ids:['p5','p5-cut','p5-new']}}));
   return {version:11,deleted_ids:['p5','p5-cut','p5-new'],updated_by:'admin'};
  }});
  // deletionImpact cannot see p5-new (stale client list) — the server corrects it.
  R.campaign.assets=R.campaign.assets.filter(x=>String(x.id)!=='p5-new');
  const flow=api.deleteMaterial(asset('p5'));
  await Promise.resolve();await Promise.resolve();
  nodes.get('#confirm-ok').onclick();
  for(let tick=0;tick<10;tick++)await Promise.resolve();
  assert(nodes.get('#toast').textContent.includes('ponownie')||nodes.get('#toast').textContent.includes('zmieni'),'The refreshed-confirmation requirement is disclosed to the editor.');
  nodes.get('#confirm-ok').onclick();
  await flow;
  assert.equal(attempts,2,'A second request reuses the server-provided scope.');
  assert(!R.campaign.assets.some(x=>['p5','p5-cut'].includes(String(x.id))),'Re-confirmed cascade removes the files.');
 }
 // A composition opened before any product was chosen keeps the template's own
 // product slot: selecting the first photo fills that slot instead of stacking
 // a duplicate layer that can never resolve and blocks export.
 {
  const C=context.window.StudioCanvas;
  const fresh=C.makeScene({brand:R.brands[0],products:[],template:'split',width:1200,height:900});
  const slot=fresh.layers.find(layer=>layer.role==='product');
  assert(slot&&!slot.asset_id&&!slot.src,'makeScene keeps the template product slot without a file.');
  R.campaign={id:'born-empty',brand_id:'brand',assets:[p1,p2],exports:[],state:api.normalizeState({product_asset_ids:[],headlines:['Oferta'],ctas:['Sprawdź'],descriptions:['Opis'],long_headline:'Długa oferta',business_name:'AMSO',confirmed:true,scene:clone(fresh),template_scenes:{split:clone(fresh)},scenes:{'split:display_300x250':C.adaptScene(fresh,300,250),'split:display_160x600':C.adaptScene(fresh,160,600)}})};
  api.toggleMaterial('product',p1);
  for(const scene of [R.campaign.state.scene,R.campaign.state.template_scenes.split,R.campaign.state.scenes['split:display_300x250'],R.campaign.state.scenes['split:display_160x600']]){
   const bound=scene.layers.filter(layer=>layer.role==='product');
   assert.equal(bound.length,1,'The born-empty template slot is filled, not duplicated in every scene.');
   assert.equal(String(bound[0].asset_id),'p1','The slot receives the selected photo.');
   assert(!scene.layers.some(layer=>layer.id==='product-p1'),'No suffixed duplicate layer is created.');
  }
  api.toggleMaterial('product',p2);
  assert.equal(R.campaign.state.scene.layers.filter(layer=>layer.role==='product').length,2,'A second selected product still adds its own layer.');
 }
 console.log('PASS: legacy migration, multiple products/elements, precise cutout replacement, original mask ancestry, clean exclusions, SVG upload/selection and raster-operation guards, sync seam, CTA properties, bulk selection/busy guard, dimension filenames and full-format undo after switching formats, delete action with disclosed confirmation and unavailable-reference reconciliation, native shape layers, cascade deletion with disclosed derived files and refreshed confirmation, template product slot fill for compositions opened before the first product.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
