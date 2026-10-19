import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
test('le déploiement ne monte ni musique ni socket Docker',()=>{const compose=readFileSync('compose.yaml','utf8');assert.ok(!compose.includes('volumes:'));assert.ok(!compose.includes('docker.sock'));assert.match(compose,/127\.0\.0\.1/);assert.match(compose,/read_only: true/);assert.match(compose,/no-new-privileges:true/)});
test('le navigateur ne possède aucune API serveur de mutation',()=>{const source=readFileSync('src/main.tsx','utf8');assert.ok(!/\bfetch\s*\(/.test(source));assert.match(source,/Données de démonstration/);assert.match(source,/Restaurer/)});
