export type Album = { id: number; artist: string; title: string; year: number; genre: string; tracks: number; expected: number; format: string; color: string; art: string; zone: string };
export const albums: Album[] = [
{id:1,artist:'Radiohead',title:'OK Computer',year:1997,genre:'Rock alternatif',tracks:10,expected:12,format:'FLAC',color:'#aec9cc',art:'computer',zone:'Téléchargements'},
{id:2,artist:'Massive Attack',title:'Mezzanine',year:1998,genre:'Trip-hop',tracks:11,expected:11,format:'FLAC',color:'#bf8365',art:'mezzanine',zone:'Bibliothèque'},
{id:3,artist:'Air',title:'Moon Safari',year:1998,genre:'Downtempo',tracks:10,expected:10,format:'FLAC',color:'#dfb569',art:'moon',zone:'Bibliothèque'},
{id:4,artist:'Portishead',title:'Dummy',year:1994,genre:'Trip-hop',tracks:11,expected:11,format:'FLAC',color:'#4e94a3',art:'dummy',zone:'Bibliothèque'},
{id:5,artist:'Björk',title:'Homogenic',year:1997,genre:'Électronique',tracks:10,expected:10,format:'FLAC',color:'#bc7078',art:'homogenic',zone:'Bibliothèque'},
{id:6,artist:'Nicolas Jaar',title:'Space Is Only Noise',year:2011,genre:'Électronique',tracks:12,expected:14,format:'MP3',color:'#a5a794',art:'space',zone:'Quarantaine'},
{id:7,artist:'Bonobo',title:'Black Sands',year:2010,genre:'Downtempo',tracks:12,expected:12,format:'FLAC',color:'#91a1bd',art:'sands',zone:'Téléchargements'},
{id:8,artist:'Tricky',title:'Maxinquaye',year:1995,genre:'Trip-hop',tracks:12,expected:12,format:'MP3',color:'#ba976e',art:'tricky',zone:'Bibliothèque'}];
export const tracks = ['Airbag','Paranoid Android','Subterranean Homesick Alien','Exit Music (For a Film)','Let Down','Karma Police','Fitter Happier','Electioneering','Climbing Up the Walls','No Surprises','Lucky','The Tourist'];
