import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import vm from 'node:vm';
const manifest=JSON.parse(readFileSync('public/manifest.webmanifest','utf8'));
test('le manifeste fournit une identité stable et les icônes installables',()=>{
 assert.equal(manifest.id,'/');assert.equal(manifest.scope,'/');assert.equal(manifest.display,'standalone');
 for(const size of [192,512]){const icon=manifest.icons.find(i=>i.sizes===`${size}x${size}`&&i.purpose==='any');assert.ok(icon);const png=readFileSync('public'+icon.src);assert.equal(png.toString('hex',0,8),'89504e470d0a1a0a');assert.equal(png.readUInt32BE(16),size);assert.equal(png.readUInt32BE(20),size)}
 assert.ok(manifest.icons.some(i=>i.purpose==='maskable'));assert.ok(existsSync('public/icons/icon-180.png'));
});
function worker(){const handlers={};const fallback={offline:true};vm.runInNewContext(readFileSync('public/sw.js','utf8').replace('__VERSION__','test').replace('__PRECACHE__',JSON.stringify(['/offline.html','/assets/app.js'])),{URL,self:{location:{origin:'https://music.test'},addEventListener:(name,handler)=>handlers[name]=handler},caches:{match:async()=>fallback},fetch:async()=>{throw new Error('offline')}});return {handlers,fallback}}
test('le worker ne conserve jamais API, musique, requêtes POST ou domaines externes',()=>{const {handlers}=worker();for(const [url,method] of [['/api/status','GET'],['/api/tracks/id/stream','GET'],['/api/session','POST'],['https://other.test/image','GET']]){let intercepted=false;handlers.fetch({request:{url:new URL(url,'https://music.test').href,method},respondWith:()=>intercepted=true});assert.equal(intercepted,false)}});
test('une ouverture hors ligne renvoie la page de reconnexion',async()=>{const {handlers,fallback}=worker();let result;handlers.fetch({request:{url:'https://music.test/',method:'GET',mode:'navigate'},respondWith:p=>result=p});assert.equal(await result,fallback)});
test('le worker livré référence uniquement des fichiers existants du build',()=>{const source=readFileSync('dist/sw.js','utf8');assert.ok(!source.includes('__VERSION__'));assert.ok(!source.includes('__PRECACHE__'));const list=JSON.parse(source.match(/const PRECACHE = (\[.*\]);/)[1]);for(const path of list)assert.ok(existsSync('dist'+path),path)});
