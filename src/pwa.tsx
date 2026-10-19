import { useEffect, useState } from 'react';
import { Download, RefreshCw, Disc3, ExternalLink } from 'lucide-react';

type InstallPrompt = Event & {prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>};
let prompt:InstallPrompt|null=null;
let registration:ServiceWorkerRegistration|null=null;
let activating=false;
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();prompt=event as InstallPrompt;window.dispatchEvent(new Event('music-manager-install'))});
window.addEventListener('appinstalled',()=>{prompt=null;window.dispatchEvent(new Event('music-manager-install'))});
if(import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext){
  navigator.serviceWorker.addEventListener('controllerchange',()=>{if(activating)location.reload()});
  const register=()=>navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'}).then(value=>{
    registration=value;
    const notify=()=>window.dispatchEvent(new Event('music-manager-install'));
    notify();
    value.addEventListener('updatefound',()=>value.installing?.addEventListener('statechange',notify));
  }).catch(()=>{/* Installation remains optional if browser storage is restricted. */});
  if(document.readyState==='complete')void register();else window.addEventListener('load',()=>void register(),{once:true});
}
export function InstallApp(){
  const [,render]=useState(0);
  const [failure,setFailure]=useState('');
  useEffect(()=>{const change=()=>render(n=>n+1);window.addEventListener('music-manager-install',change);return()=>window.removeEventListener('music-manager-install',change)},[]);
  const standalone=window.matchMedia('(display-mode: standalone)').matches || Boolean((navigator as Navigator&{standalone?:boolean}).standalone);
  return <section><h2><Disc3 size={21}/> Installer Music Manager</h2>{!window.isSecureContext?<><p>Ouvrez l’adresse HTTPS privée pour installer l’application avec son icône.</p><a className="button-link" href="https://macmini-server.tail9ed71f.ts.net:9444/">Ouvrir l’adresse sécurisée <ExternalLink size={16}/></a></>:standalone?<p>Music Manager est ouvert comme une application sur cet appareil.</p>:prompt?<><p>Retrouvez votre bibliothèque depuis l’écran d’accueil, avec son icône disque.</p><button onClick={async()=>{try{const pending=prompt;if(!pending)return;await pending.prompt();await pending.userChoice;prompt=null;render(n=>n+1)}catch{setFailure('Utilisez le menu du navigateur pour installer l’application.')}}}><Download size={17}/>Installer l’application</button></>:<><p>Sur iPhone ou iPad : dans Safari, ouvrez le menu de partage, puis choisissez « Sur l’écran d’accueil » et activez « Ouvrir comme app » si proposé.</p><p>Sur Android ou ordinateur : utilisez « Installer l’application » dans le menu de votre navigateur.</p></>}{failure&&<p role="status">{failure}</p>}<p className="muted">Tailscale doit rester actif pour accéder au serveur. La musique reste sur votre serveur ; une page de reconnexion s’affiche lorsque celui-ci est inaccessible.</p>{registration?.waiting&&<button onClick={()=>{activating=true;registration?.waiting?.postMessage({type:'ACTIVATE_UPDATE'})}}><RefreshCw size={17}/>Appliquer la mise à jour</button>}</section>
}
