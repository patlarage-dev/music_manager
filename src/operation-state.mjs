// The synchronous gate closes before React rerenders, so rapid clicks share one request.
export function createActionGate() {
  let pending = false;
  return {
    isPending: () => pending,
    async run(work) {
      if (pending) return;
      pending = true;
      try {
        return await work();
      } finally {
        pending = false;
      }
    },
  };
}

export async function waitForIndex(
  read,
  baseline,
  onRetry,
  delay = () => new Promise((resolve) => setTimeout(resolve, 1200)),
) {
  let observedRunning = false;
  let idleFailures = 0;
  for (;;) {
    await delay();
    let state;
    try {
      state = await read();
    } catch {
      onRetry(
        "Connexion interrompue. Vérification en cours ; l’opération ne sera pas relancée.",
      );
      continue;
    }
    onRetry(
      "Mise à jour de la bibliothèque… Patientez avant une nouvelle action.",
    );
    observedRunning ||= state.running;
    if (!state.running && state.lastScan && state.lastScan !== baseline) return;
    idleFailures =
      !state.running && state.errors?.length ? idleFailures + 1 : 0;
    if (
      (observedRunning || idleFailures >= 2) &&
      !state.running &&
      state.errors?.length
    ) {
      throw new Error(
        "Les fichiers ont été traités, mais l’analyse a échoué. Relancez l’analyse depuis l’accueil.",
      );
    }
  }
}
