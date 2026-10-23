import test from "node:test";
import assert from "node:assert/strict";
import { createActionGate, waitForIndex } from "../src/operation-state.mjs";

test("un double clic ne relance pas une opération, même avant le rendu React", async () => {
  const gate = createActionGate();
  let finish;
  let calls = 0;
  const first = gate.run(async () => {
    calls++;
    await new Promise((resolve) => {
      finish = resolve;
    });
  });
  assert.equal(gate.isPending(), true);
  await gate.run(async () => {
    calls++;
  });
  assert.equal(calls, 1);
  finish();
  await first;
  assert.equal(gate.isPending(), false);
  await gate.run(async () => {
    calls++;
  });
  assert.equal(calls, 2);
});

test("le verrou attend la fin de la nouvelle indexation et non un statut ancien", async () => {
  const states = [
    { running: false, lastScan: "before" },
    { running: true, lastScan: "before" },
    { running: true, lastScan: "after" },
    { running: false, lastScan: "after" },
  ];
  let reads = 0;
  await waitForIndex(
    async () => {
      reads++;
      return states.shift();
    },
    "before",
    () => {},
    async () => {},
  );
  assert.equal(reads, 4);
});

test("une coupure réseau pendant l’indexation ne relance pas les fichiers", async () => {
  let reads = 0,
    writes = 0;
  const notices = [];
  const gate = createActionGate();
  await gate.run(async () => {
    writes++;
    await waitForIndex(
      async () => {
        if (++reads === 1) throw new Error("offline");
        return { running: false, lastScan: "new" };
      },
      "old",
      (s) => notices.push(s),
      async () => {},
    );
  });
  assert.equal(writes, 1);
  assert.equal(reads, 2);
  assert.ok(notices.some((s) => s.includes("Connexion interrompue")));
  assert.equal(gate.isPending(), false);
});

test("une erreur rend le verrou disponible et signale un échec d’indexation", async () => {
  const gate = createActionGate();
  await assert.rejects(
    gate.run(async () => {
      throw new Error("refused");
    }),
    /refused/,
  );
  assert.equal(gate.isPending(), false);
  const states = [
    { running: true, lastScan: "old" },
    { running: false, lastScan: "old", errors: ["failure"] },
  ];
  await assert.rejects(
    waitForIndex(
      async () => states.shift(),
      "old",
      () => {},
      async () => {},
    ),
    /analyse a échoué/,
  );
});

test('une analyse échouée avant le premier sondage ne laisse pas le loader bloqué',async()=>{
 let reads=0;
 await assert.rejects(waitForIndex(async()=>{reads++;return {running:false,lastScan:'old',errors:['failed']};},'old',()=>{},async()=>{}),/analyse a échoué/);
 assert.equal(reads,2);
});
