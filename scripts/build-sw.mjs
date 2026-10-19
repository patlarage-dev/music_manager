import {readdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const assets=(await readdir('dist/assets')).filter(name=>/\.(js|css|woff2)$/.test(name)).map(name=>'/assets/'+name);
const precache=['/offline.html','/manifest.webmanifest','/icon.svg','/icons/icon-180.png','/icons/icon-192.png','/icons/icon-512.png',...assets];
const hash=createHash('sha256');
for(const file of [...precache,'/index.html'])hash.update(await readFile('dist'+file));
const template=await readFile('public/sw.js','utf8');
await writeFile('dist/sw.js',template.replace('__VERSION__',hash.digest('hex').slice(0,16)).replace('__PRECACHE__',JSON.stringify(precache)));
