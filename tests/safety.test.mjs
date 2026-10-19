import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('le backend reste privé et le socket Docker est absent',()=>{const compose=readFileSync('compose.yaml','utf8');assert.ok(!compose.includes('docker.sock'));const backend=compose.split('\n  backend:')[1];assert.ok(!backend.includes('ports:'));assert.match(compose,/127\.0\.0\.1/);assert.match(compose,/no-new-privileges:true/)});
test('les requêtes API passent par le même serveur HTTP',()=>{const nginx=readFileSync('nginx.conf','utf8');assert.match(nginx,/location \/api\//);assert.match(nginx,/proxy_pass http:\/\/backend:8000/);assert.match(nginx,/proxy_set_header Host \$http_host/)});
