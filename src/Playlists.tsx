import { useEffect, useState } from "react";
import { ListMusic, RotateCcw } from "lucide-react";
import { api, type Song } from "./api";

type Source = { id: string; name: string; zone: string; rel: string };
type Preview = Source & {
  total: number;
  ready: number;
  items: { entry: string; status: string; track: Song | null }[];
};
type NavList = {
  items: { id: string; name: string; songCount: number }[];
  username: string;
  url: string;
};
export function Playlists({ revision }: { revision: number }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [navError, setNavError] = useState("");
  const [nav, setNav] = useState<NavList | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<{ items: Source[] }>(
      "/playlist-files",
      undefined,
      undefined,
      controller.signal,
    )
      .then((d) => setSources(d.items))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    setNavError("");
    api<NavList>(
      "/navidrome/playlists",
      undefined,
      undefined,
      controller.signal,
    )
      .then(setNav)
      .catch((e) => {
        if (e.name !== "AbortError") setNavError(e.message);
      });
    return () => controller.abort();
  }, [revision, version]);
  useEffect(() => {
    setPreview(null);
    setNotice("");
    setError("");
    if (!selected) return;
    const controller = new AbortController();
    api<Preview>(
      `/playlist-files/${selected}`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((d) => {
        setPreview(d);
        setName(d.name.slice(0, 120));
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [selected, revision, version]);
  const visible =
    nav?.items.filter((p) =>
      p.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
    ) || [];
  return (
    <div className="playlist-workspace">
      <section aria-labelledby="import-heading">
        <div className="section-heading">
          <h2 id="import-heading">Importer une playlist téléchargée</h2>
          <button disabled={busy} onClick={() => setVersion((v) => v + 1)}>
            <RotateCcw size={16} />
            Actualiser
          </button>
        </div>
        <p className="muted">
          Les fichiers M3U, M3U8 et PLS de Téléchargements et Bibliothèque sont
          détectés automatiquement. Les pistes doivent être dans Bibliothèque
          avant l’envoi à Navidrome.
        </p>
        <label className="field">
          Fichier de playlist
          <select
            value={selected}
            disabled={busy}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choisir une playlist ({sources.length})</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.zone} / {s.rel}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {preview && (
          <>
            <p className="file-location">
              {preview.zone} / {preview.rel}
            </p>
            <p role="status">
              {preview.ready} / {preview.total} pistes prêtes. L’ordre du
              fichier sera conservé.
            </p>
            {preview.ready !== preview.total && (
              <p className="muted">
                Déplacez les pistes en attente depuis l’Explorateur, puis
                analysez Bibliothèque dans Music Manager et Navidrome. Les
                pistes introuvables doivent être retéléchargées ou leur chemin
                corrigé dans le fichier. Aucun import partiel n’est effectué.
              </p>
            )}
            <form
              className="playlist-import-form"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                setNotice("");
                try {
                  const result = await api<{
                    username: string;
                    playlist: { name: string; songCount: number };
                  }>("/playlist-files/import", { sourceId: selected, name });
                  setNotice(
                    `« ${result.playlist.name} » : ${result.playlist.songCount} pistes enregistrées et vérifiées pour ${result.username}. Actualisez les playlists de Substreamer sur ce même compte.`,
                  );
                  const updated = await api<NavList>("/navidrome/playlists");
                  setNav(updated);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="field">
                Nom dans Navidrome
                <input
                  value={name}
                  maxLength={120}
                  required
                  disabled={busy}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <button
                className="primary"
                disabled={busy || preview.ready !== preview.total}
              >
                {busy
                  ? "Enregistrement et vérification…"
                  : "Enregistrer dans Navidrome"}
              </button>
            </form>
            <details>
              <summary>Vérifier les {preview.total} pistes</summary>
              <ol className="playlist-import-tracks">
                {preview.items.map((item, i) => (
                  <li key={i}>
                    <span>
                      {item.track
                        ? `${item.track.artist} — ${item.track.title}`
                        : item.entry}
                    </span>
                    <small>
                      {
                        (
                          {
                            ready: "Prête",
                            incoming: "À déplacer dans Bibliothèque",
                            missing: "Introuvable ou non indexée",
                            unsupported: "Adresse externe non prise en charge",
                          } as Record<string, string>
                        )[item.status]
                      }
                    </small>
                  </li>
                ))}
              </ol>
            </details>
          </>
        )}
        {notice && (
          <p className="scan-notice" role="status">
            {notice}
          </p>
        )}
      </section>
      <section aria-labelledby="nav-playlists-heading">
        <div className="section-heading">
          <h2 id="nav-playlists-heading">Dans Navidrome</h2>
        </div>
        {navError && (
          <p className="error" role="alert">
            {navError}
          </p>
        )}
        {nav && (
          <>
            <p className="muted">
              {nav.items.length} playlists accessibles au compte{" "}
              <strong>{nav.username}</strong>. Cette liste vient directement de
              l’API utilisée par Substreamer. La radio locale doit être
              enregistrée dans Navidrome pour figurer ici.
            </p>
            <label className="field">
              Rechercher une playlist
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Nom de la playlist"
              />
            </label>
            <ul className="nav-playlist-list">
              {visible.slice(0, 50).map((p) => (
                <li key={p.id}>
                  <ListMusic size={18} aria-hidden="true" />
                  <strong>{p.name}</strong>
                  <span>{p.songCount} pistes</span>
                </li>
              ))}
            </ul>
            {!visible.length && <p>Aucune playlist trouvée.</p>}
            {visible.length > 50 && (
              <p className="muted">
                50 playlists sur {visible.length}. Précisez la recherche pour
                voir les suivantes.
              </p>
            )}
            <a
              className="button-link"
              href={nav.url}
              target="_blank"
              rel="noreferrer"
            >
              Ouvrir Navidrome
            </a>
          </>
        )}
      </section>
    </div>
  );
}
