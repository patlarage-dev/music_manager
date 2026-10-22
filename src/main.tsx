import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  FolderOpen,
  Disc3,
  ListMusic,
  Copy,
  Compass,
  Radio,
  History,
  Settings,
  Search,
  ArrowUpRight,
  ArrowRight,
  Check,
  X,
  ChevronRight,
  Heart,
  Play,
  Trash2,
  RotateCcw,
  Download,
  HardDrive,
  Plus,
  CheckCircle2,
  MoreHorizontal,
  ArrowLeft,
  ExternalLink,
  LogIn,
  AlertCircle,
  Folder,
  FileAudio,
  Move,
  PenLine,
  Loader2,
} from "lucide-react";
import {
  api,
  duration,
  bytes,
  type Album,
  type Song,
  type Status,
} from "./api";
import "./style.css";
import { InstallApp } from "./pwa";
const pages = [
  "Tableau de bord",
  "Explorateur",
  "Albums",
  "Albums incomplets",
  "Doublons",
  "Découverte",
  "Radio locale",
  "Historique et corbeille",
  "Paramètres",
];
const routes = [
  "accueil",
  "explorateur",
  "albums",
  "incomplets",
  "doublons",
  "decouverte",
  "radio",
  "historique",
  "parametres",
];
const icons = [
  LayoutDashboard,
  FolderOpen,
  Disc3,
  ListMusic,
  Copy,
  Compass,
  Radio,
  History,
  Settings,
];
const zones = ["Téléchargements", "Bibliothèque", "Quarantaine"];
function pageFromHash() {
  const i = routes.indexOf(location.hash.slice(1));
  return i < 0 ? 0 : i;
}
function useResource<T>(url: string | null, revision = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    api<T>(url, undefined, undefined, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [url, revision]);
  return { data, error, loading };
}
function Cover({ album, small = false }: { album: Album; small?: boolean }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`real-cover ${small ? "small" : ""}`}>
      {album.cover && !failed ? (
        <img
          loading="lazy"
          src={album.cover}
          alt=""
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="cover-fallback">
          <Disc3 aria-hidden="true" />
          <span>{album.title}</span>
        </div>
      )}
    </div>
  );
}
function Dialog({
  title,
  onClose,
  children,
  className = "",
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const d = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    d?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      d?.close();
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`native-dialog ${className}`}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        closeRef.current();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) closeRef.current();
      }}
    >
      <div className="dialog-content">
        <div className="dialog-heading">
          <h2>{title}</h2>
          <button
            autoFocus
            className="icon-button"
            aria-label="Fermer"
            onClick={onClose}
          >
            <X />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Disc3 size={32} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function ErrorMessage({ message }: { message: string }) {
  return message ? (
    <p className="error" role="alert">
      <AlertCircle size={18} />
      {message}
    </p>
  ) : null;
}
function App() {
  const [page, setPage] = useState(pageFromHash),
    [more, setMore] = useState(false),
    [revision, setRevision] = useState(0),
    [status, setStatus] = useState<Status | null>(null),
    [statusError, setStatusError] = useState(""),
    [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [genre, setGenre] = useState(""),
    [formatFilter, setFormatFilter] = useState(""),
    [stateFilter, setStateFilter] = useState(""),
    [zone, setZone] = useState("Téléchargements"),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<string[]>([]),
    [detail, setDetail] = useState<string | null>(null),
    [toast, setToast] = useState(""),
    [busy, setBusy] = useState(false),
    [action, setAction] = useState<{ ids: string[]; name: string } | null>(
      null,
    );
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tell = (text: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(text);
    toastTimer.current = setTimeout(() => setToast(""), 7000);
  };
  const refresh = () => setRevision((r) => r + 1);
  const indexedAt = useRef<string | null>(null);
  useEffect(() => {
    const value = status?.scan.lastScan;
    if (value && indexedAt.current !== value) {
      const previous = indexedAt.current;
      indexedAt.current = value;
      if (previous) setRevision((r) => r + 1);
    }
  }, [status?.scan.lastScan]);
  useEffect(() => {
    const changed = () => {
      setPage(pageFromHash());
      setMore(false);
      setQuery("");
      setSearch("");
      setGenre("");
      setFormatFilter("");
      setStateFilter("");
      setOffset(0);
      setSelected([]);
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query);
      setOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api<Status>("/status")
        .then((s) => {
          if (!cancelled) {
            setStatus(s);
            setStatusError("");
          }
        })
        .catch((e) => {
          if (!cancelled) setStatusError(e.message);
        });
    load();
    const interval = setInterval(load, 7000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [revision]);
  const navigate = (index: number) => {
    setMore(false);
    if (page === index) {
      window.scrollTo({ top: 0 });
      return;
    }
    location.hash = routes[index];
  };
  const albumUrl = `/albums?q=${encodeURIComponent(search)}&genre=${encodeURIComponent(genre)}&zone=${encodeURIComponent(page === 1 ? zone : "Bibliothèque")}&format=${encodeURIComponent(page === 1 ? formatFilter : "")}&state=${encodeURIComponent(page === 1 ? stateFilter : "")}&offset=${offset}&limit=60`;
  const library = useResource<{
    items: Album[];
    total: number;
    genres: string[];
    formats: string[];
  }>([0, 1, 2, 3, 5, 6].includes(page) ? albumUrl : null, revision);
  const albums = library.data?.items || [];
  const artistList = useResource<{ items: string[] }>(
    [5, 6].includes(page) ? "/artists" : null,
    revision,
  );
  const selectedVisible = albums.filter((a) => selected.includes(a.id)).length;
  const selectionControls = (position: "top" | "bottom") => (
    <div
      className={`selection-bar explorer-selection ${position} ${selected.length ? "has-selection" : ""}`}
      role="region"
      aria-label={
        position === "top"
          ? "Sélection avant la liste"
          : "Sélection après la liste"
      }
    >
      <div className="selection-summary">
        <strong>{selected.length} album(s) sélectionné(s)</strong>
        {selected.length > selectedVisible && (
          <small>
            {selected.length - selectedVisible} hors de cette page ou des
            filtres
          </small>
        )}
      </div>
      <div className="selection-actions">
        <button
          className="text-button"
          disabled={
            !albums.some((a) => !selected.includes(a.id)) ||
            selected.length >= 20 ||
            library.loading ||
            !!library.error
          }
          onClick={() =>
            setSelected((ids) =>
              Array.from(new Set([...ids, ...albums.map((a) => a.id)])).slice(
                0,
                20,
              ),
            )
          }
        >
          Sélectionner la page (20 max)
        </button>
        <button
          className="text-button"
          disabled={!selected.length}
          onClick={() => setSelected([])}
        >
          Tout désélectionner
        </button>
        <button
          className="primary"
          disabled={!selected.length || library.loading}
          onClick={() =>
            setAction({ ids: selected, name: `${selected.length} album(s)` })
          }
        >
          Gérer la sélection <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
  const task = async (work: () => Promise<unknown>, message?: string) => {
    setBusy(true);
    try {
      await work();
      refresh();
      if (message) tell(message);
    } catch (e) {
      tell((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const grid = (items: Album[]) => (
    <div className="album-grid">
      {items.map((a) => (
        <button className="album" key={a.id} onClick={() => setDetail(a.id)}>
          <Cover album={a} />
          <strong>{a.title}</strong>
          <span>{a.artist}</span>
          <small>
            {a.year || "Année inconnue"} <b>{a.format}</b>
          </small>
        </button>
      ))}
      {!items.length && !library.loading && (
        <Empty title="Aucun album à afficher">
          <p>
            {status?.scan.running
              ? "L’indexation est en cours. Les albums apparaîtront après l’analyse."
              : "Aucun album ne correspond à cette sélection."}
          </p>
        </Empty>
      )}
    </div>
  );
  const scan = () =>
    task(() => api("/scan", {}), "Analyse lancée en arrière-plan.");
  return (
    <div
      className={page === 1 && selected.length ? "app with-selection" : "app"}
    >
      <aside>
        <a className="brand" href="#accueil">
          <span className="brand-symbol">
            <Disc3 />
          </span>
          music manager
          <span className="brand-dot" />
        </a>
        <p className="sidebar-label">Votre collection, à votre rythme.</p>
        <nav aria-label="Navigation principale">
          {pages.map((name, i) => {
            const Icon = icons[i];
            return (
              <button
                key={name}
                aria-current={page === i ? "page" : undefined}
                className={page === i ? "active" : ""}
                onClick={() => navigate(i)}
              >
                <Icon size={19} />
                <span>{name}</span>
                {i === 3 && !!status?.stats.incomplete && (
                  <em>{status.stats.incomplete}</em>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div>
            <HardDrive size={18} />
            <span>Bibliothèque personnelle</span>
          </div>
          <p>
            {status?.disk
              ? `${bytes(status.disk.free)} disponibles`
              : "Connexion au serveur…"}
          </p>
          {status?.disk && (
            <div className="disk">
              <span
                style={{
                  width: `${(1 - status.disk.free / status.disk.total) * 100}%`,
                }}
              />
            </div>
          )}
          <small>
            {status?.navidrome.connected
              ? "Navidrome connecté"
              : "Index local des fichiers"}
          </small>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <a className="mobile-brand" href="#accueil">
            <Disc3 size={24} />
            music manager
          </a>
          <div className="breadcrumb">
            Ma collection <ChevronRight size={14} />
            <span>{pages[page]}</span>
          </div>
          <div className="header-right">
            <span className="connection-dot" />
            {status?.scan.running ? "Analyse en cours" : "Bibliothèque réelle"}
            <button
              className="avatar"
              aria-label="Ouvrir les paramètres"
              onClick={() => navigate(8)}
            >
              {status?.session?.username.charAt(0).toUpperCase() || "P"}
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <h1>{pages[page]}</h1>
              <p>
                {
                  [
                    "Une place pour chaque disque. De nouvelles pistes à explorer.",
                    "Parcourez vos dossiers et gérez vos albums.",
                    "Tous vos disques, réunis au même endroit.",
                    "Comparez vos pistes à une édition identifiée.",
                    "Comparez les fichiers avant de faire votre choix.",
                    "Suivez les liens entre les artistes de votre collection.",
                    "Une sélection composée de vos propres morceaux.",
                    "Chaque déplacement garde une trace et un chemin de retour.",
                    "Votre bibliothèque et vos connexions.",
                  ][page]
                }
              </p>
            </div>
            {page === 0 && (
              <button
                className="primary"
                disabled={busy || status?.scan.running}
                onClick={scan}
              >
                <RotateCcw
                  size={16}
                  className={status?.scan.running ? "spinning" : ""}
                />
                {status?.scan.running
                  ? "Analyse en cours…"
                  : "Analyser la bibliothèque"}
              </button>
            )}
          </div>
          <ErrorMessage message={statusError} />
          {status?.scan.running && (
            <p role="status" className="scan-notice">
              <Loader2 size={16} className="spinning" />
              {status.scan.processed} fichiers lus · l’interface reste
              disponible
            </p>
          )}
          {!!status?.scan.errors.length && (
            <details className="scan-errors">
              <summary>
                {status.scan.errors.length} problème(s) pendant l’analyse
              </summary>
              {status.scan.errors.map((e) => (
                <p key={e}>{e}</p>
              ))}
            </details>
          )}
          {page === 0 && (
            <>
              <div className="stats">
                {[
                  ["Artistes", status?.stats.artists],
                  ["Albums", status?.stats.albums],
                  ["Morceaux", status?.stats.tracks],
                  ["En quarantaine", status?.stats.quarantine],
                ].map(([label, value], i) => (
                  <button
                    key={label}
                    onClick={() => {
                      if (i === 3) setZone("Quarantaine");
                      navigate(i === 3 ? 1 : 2);
                    }}
                  >
                    <span>{label}</span>
                    <strong>{value ?? "…"}</strong>
                    <ArrowUpRight size={17} />
                  </button>
                ))}
              </div>
              <section className="feature">
                <div>
                  <span className="feature-icon">
                    <Compass size={22} />
                  </span>
                  <h2>Une collection à redécouvrir.</h2>
                  <p>
                    Retrouvez les albums de votre bibliothèque et composez une
                    sélection à partir des morceaux que vous possédez.
                  </p>
                  <button onClick={() => navigate(6)}>
                    Créer ma radio locale <ArrowRight size={17} />
                  </button>
                </div>
                <div className="feature-real-art">
                  {albums.slice(0, 2).map((a) => (
                    <Cover album={a} key={a.id} />
                  ))}
                </div>
              </section>
              <section>
                <div className="section-heading">
                  <h2>Dans votre bibliothèque</h2>
                  <button className="text-button" onClick={() => navigate(2)}>
                    Tous les albums <ArrowRight size={16} />
                  </button>
                </div>
                <ErrorMessage message={library.error} />
                {grid(albums.slice(0, 5))}
              </section>
              <div className="dashboard-bottom">
                <section>
                  <h2>À votre attention</h2>
                  {[
                    [
                      ListMusic,
                      `${status?.stats.incomplete ?? "…"} album(s) incomplet(s)`,
                      "À partir des tags ou d’une édition MusicBrainz.",
                      3,
                    ],
                    [
                      Copy,
                      "Vérifier les doublons",
                      "Empreintes de fichiers et titres comparables.",
                      4,
                    ],
                    [
                      FolderOpen,
                      `${status?.stats.incoming ?? "…"} album(s) téléchargé(s)`,
                      "Contenu réel du dossier Deemix.",
                      1,
                    ],
                  ].map(([Icon, title, sub, n]) => {
                    const I = Icon as typeof ListMusic;
                    return (
                      <button
                        className="action-row"
                        key={String(title)}
                        onClick={() => navigate(Number(n))}
                      >
                        <I size={20} />
                        <div>
                          <strong>{String(title)}</strong>
                          <span>{String(sub)}</span>
                        </div>
                        <ChevronRight size={18} />
                      </button>
                    );
                  })}
                </section>
                <section className="collection-note">
                  <Disc3 size={28} />
                  <h2>Votre musique reste chez vous.</h2>
                  <p>
                    {status?.stats.albums ?? "…"} albums indexés depuis vos
                    fichiers. Écoutez-les dans Navidrome ou préécoutez une piste
                    ici.
                  </p>
                  <a
                    className="button-link"
                    target="_blank"
                    rel="noreferrer"
                    href={status?.navidrome.url || "http://100.120.247.35:4533"}
                  >
                    Ouvrir Navidrome <ExternalLink size={16} />
                  </a>
                </section>
              </div>
            </>
          )}
          {(page === 1 || page === 2) && (
            <>
              <div className="toolbar">
                {page === 1 ? (
                  <div className="tabs" aria-label="Espaces de fichiers">
                    {zones.map((z) => (
                      <button
                        key={z}
                        className={zone === z ? "selected" : ""}
                        onClick={() => {
                          setZone(z);
                          setOffset(0);
                          setSelected([]);
                        }}
                      >
                        {z}
                      </button>
                    ))}
                  </div>
                ) : (
                  <select
                    aria-label="Filtrer par genre"
                    value={genre}
                    onChange={(e) => {
                      setGenre(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">Tous les genres</option>
                    {library.data?.genres.map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                )}
                <label className="search">
                  <Search size={17} />
                  <input
                    aria-label="Rechercher un album ou un artiste"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Artiste, album…"
                  />
                </label>
              </div>
              <ErrorMessage message={library.error} />
              {library.loading && (
                <p role="status" className="muted">
                  Chargement des albums…
                </p>
              )}
              {page === 2 ? (
                grid(albums)
              ) : (
                <>
                  <Explorer zone={zone} revision={revision} />
                  <div className="explorer-results">
                    <div className="section-heading">
                      <h2>Albums dans cet espace</h2>
                      <span className="muted">
                        {library.data?.total ?? 0} album(s)
                      </span>
                    </div>
                    <div
                      className="explorer-filters"
                      role="group"
                      aria-label="Filtrer les albums de cet espace"
                    >
                      <label>
                        Genre
                        <select
                          value={genre}
                          onChange={(e) => {
                            setGenre(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">Tous les genres</option>
                          {library.data?.genres.map((g) => (
                            <option key={g}>{g}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Format
                        <select
                          value={formatFilter}
                          onChange={(e) => {
                            setFormatFilter(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">Tous les formats</option>
                          {library.data?.formats?.map((f) => (
                            <option key={f}>{f}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        État
                        <select
                          value={stateFilter}
                          onChange={(e) => {
                            setStateFilter(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">Tous les états</option>
                          <option value="incomplete">Incomplets</option>
                          <option value="unknown">À identifier</option>
                          <option value="complete">
                            Complets selon la référence
                          </option>
                        </select>
                      </label>
                      {(query || genre || formatFilter || stateFilter) && (
                        <button
                          className="text-button"
                          onClick={() => {
                            setQuery("");
                            setSearch("");
                            setGenre("");
                            setFormatFilter("");
                            setStateFilter("");
                            setOffset(0);
                          }}
                        >
                          Effacer les filtres
                        </button>
                      )}
                    </div>
                    <p className="muted selection-limit">
                      20 albums maximum par opération. La sélection est
                      conservée entre les pages et les filtres.
                    </p>
                    {selectionControls("top")}
                    <div
                      className="real-album-list"
                      aria-busy={library.loading}
                    >
                      {albums.map((a) => (
                        <div className="explorer-album" key={a.id}>
                          <input
                            aria-label={`Sélectionner ${a.title}`}
                            type="checkbox"
                            checked={selected.includes(a.id)}
                            disabled={
                              library.loading ||
                              (!selected.includes(a.id) &&
                                selected.length >= 20)
                            }
                            onChange={() =>
                              setSelected((s) =>
                                s.includes(a.id)
                                  ? s.filter((id) => id !== a.id)
                                  : [...s, a.id],
                              )
                            }
                          />
                          <button
                            className="table-album"
                            onClick={() => setDetail(a.id)}
                          >
                            <Cover album={a} small />
                            <span>
                              <strong>{a.title}</strong>
                              <small>
                                {a.artist} · {a.tracks} pistes · {a.format}
                              </small>
                            </span>
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Gérer ${a.title}`}
                            onClick={() =>
                              setAction({ ids: [a.id], name: a.title })
                            }
                          >
                            <MoreHorizontal />
                          </button>
                        </div>
                      ))}
                      {!albums.length && !library.loading && (
                        <p className="muted">
                          Aucun album ne correspond à ces filtres dans cet
                          espace.
                        </p>
                      )}
                    </div>
                    {selectionControls("bottom")}
                  </div>
                </>
              )}
              {!!library.data && library.data.total > 60 && (
                <div className="pagination">
                  <button
                    disabled={!offset}
                    onClick={() => setOffset((o) => o - 60)}
                  >
                    Précédent
                  </button>
                  <span>
                    {offset + 1}–{Math.min(offset + 60, library.data.total)} /{" "}
                    {library.data.total}
                  </span>
                  <button
                    disabled={offset + 60 >= library.data.total}
                    onClick={() => setOffset((o) => o + 60)}
                  >
                    Suivant
                  </button>
                </div>
              )}
            </>
          )}
          {page === 3 && (
            <Completeness revision={revision} onOpen={setDetail} />
          )}
          {page === 4 && <Duplicates revision={revision} onOpen={setDetail} />}
          {page === 5 && (
            <Discovery
              artists={artistList.data?.items || []}
              onOpenArtist={(name) => {
                navigate(2);
                setTimeout(() => setQuery(name), 0);
              }}
              tell={tell}
            />
          )}
          {page === 6 && (
            <RadioPanel artists={artistList.data?.items || []} tell={tell} />
          )}
          {page === 7 && (
            <HistoryPanel revision={revision} refresh={refresh} tell={tell} />
          )}
          {page === 8 && (
            <SettingsPanel status={status} refresh={refresh} tell={tell} />
          )}
          <footer>
            Music Manager{" "}
            <span>Une collection personnelle. Un peu plus de curiosité.</span>
            <span>Version 0.2 · Bibliothèque réelle</span>
          </footer>
        </main>
      </div>
      <nav className="bottom-nav" aria-label="Navigation mobile">
        {[
          [0, "Accueil", LayoutDashboard],
          [2, "Albums", Disc3],
          [1, "Explorateur", FolderOpen],
        ].map(([n, label, Icon]) => {
          const I = Icon as typeof Disc3;
          return (
            <button
              key={Number(n)}
              aria-current={page === n ? "page" : undefined}
              className={page === n && !more ? "active" : ""}
              onClick={() => navigate(Number(n))}
            >
              <I size={22} />
              <span>{String(label)}</span>
            </button>
          );
        })}
        <button
          className={more || ![0, 1, 2].includes(page) ? "active" : ""}
          aria-expanded={more}
          onClick={() => setMore(true)}
        >
          <MoreHorizontal size={24} />
          <span>Plus</span>
        </button>
      </nav>
      {more && (
        <Dialog
          title="Votre collection"
          className="more-sheet"
          onClose={() => setMore(false)}
        >
          <p className="muted">Explorez et prenez soin de votre musique.</p>
          <nav aria-label="Toutes les sections">
            {pages.map((name, i) => {
              const Icon = icons[i];
              return (
                <button
                  key={name}
                  className={page === i ? "active" : ""}
                  aria-current={page === i ? "page" : undefined}
                  onClick={() => navigate(i)}
                >
                  <Icon size={21} />
                  <span>{name}</span>
                  <ChevronRight size={17} />
                </button>
              );
            })}
          </nav>
        </Dialog>
      )}
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={20} />
          {toast}
          <button
            aria-label="Fermer la notification"
            onClick={() => setToast("")}
          >
            <X size={18} />
          </button>
        </div>
      )}
      {detail && (
        <AlbumDialog
          id={detail}
          revision={revision}
          onClose={() => setDetail(null)}
          refresh={refresh}
          tell={tell}
          onManage={(id, name) => {
            setDetail(null);
            setAction({ ids: [id], name });
          }}
        />
      )}
      {action && (
        <ManageDialog
          {...action}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null);
            setSelected([]);
            refresh();
            setTimeout(refresh, 1500);
          }}
          tell={tell}
        />
      )}
    </div>
  );
}
function Explorer({ zone, revision }: { zone: string; revision: number }) {
  const [path, setPath] = useState(""),
    [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => {
    setPath("");
    setPlaying(null);
  }, [zone]);
  const { data, error } = useResource<{
    items: {
      name: string;
      path: string;
      directory: boolean;
      size: number | null;
      trackId: string | null;
    }[];
    path: string;
  }>(
    `/explorer?zone=${encodeURIComponent(zone)}&path=${encodeURIComponent(path)}`,
    revision,
  );
  return (
    <section className="folder-browser">
      <div className="folder-path">
        <button
          disabled={!path}
          onClick={() => setPath(path.split("/").slice(0, -1).join("/"))}
          aria-label="Dossier parent"
        >
          <ArrowLeft size={18} />
        </button>
        <button onClick={() => setPath("")}>{zone}</button>
        {path && <span> / {path}</span>}
      </div>
      <ErrorMessage message={error} />
      <div className="file-list">
        {data?.items.map((item) => (
          <button
            key={item.path}
            disabled={!item.directory && !item.trackId}
            onClick={() =>
              item.directory ? setPath(item.path) : setPlaying(item.trackId)
            }
          >
            {item.directory ? <Folder size={20} /> : <FileAudio size={20} />}
            <span>{item.name}</span>
            {item.directory ? (
              <ChevronRight size={17} />
            ) : item.trackId ? (
              <Play size={17} />
            ) : null}
          </button>
        ))}
        {data?.items.length === 0 && (
          <p className="muted">Ce dossier est vide.</p>
        )}
      </div>
      {playing && (
        <audio
          aria-label="Préécoute du fichier"
          controls
          autoPlay
          src={`/api/tracks/${playing}/stream`}
        />
      )}
    </section>
  );
}
function AlbumDialog({
  id,
  revision,
  onClose,
  refresh,
  tell,
  onManage,
}: {
  id: string;
  revision: number;
  onClose: () => void;
  refresh: () => void;
  tell: (s: string) => void;
  onManage: (id: string, name: string) => void;
}) {
  const { data: a, error } = useResource<Album>(`/albums/${id}`, revision);
  const [playing, setPlaying] = useState<Song | null>(null),
    [matches, setMatches] = useState<
      | {
          id: string;
          title: string;
          artist: string;
          date: string;
          country: string;
          tracks: number;
          disambiguation: string;
        }[]
      | null
    >(null),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const find = async () => {
    setBusy(true);
    setFailure("");
    try {
      const r = await api<{ items: NonNullable<typeof matches> }>(
        `/albums/${id}/matches`,
      );
      setMatches(r.items);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const identify = async (mbid: string) => {
    setBusy(true);
    try {
      await api(`/albums/${id}/identify`, { mbid });
      setMatches(null);
      refresh();
      setTimeout(refresh, 1200);
      tell("Édition MusicBrainz enregistrée. Comparaison des pistes en cours.");
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={a?.title || "Fiche album"} onClose={onClose}>
      <ErrorMessage message={error || failure} />
      {a ? (
        <>
          <div className="album-detail">
            <Cover album={a} />
            <div>
              <span className="badge">{a.zone}</span>
              <h3>{a.artist}</h3>
              <p>
                {a.year || "Année inconnue"} · {a.genre}
              </p>
              <p>
                {a.tracks} pistes · {duration(a.duration)} · {a.format}
              </p>
              <span
                className={`badge ${a.completeness === "complete" ? "good" : ""}`}
              >
                {a.completeness === "complete"
                  ? "Complet selon la référence"
                  : a.completeness === "incomplete"
                    ? `${a.missing.length} piste(s) manquante(s)`
                    : "Édition à identifier"}
              </span>
            </div>
          </div>
          <div className="detail-actions">
            <button disabled={busy} onClick={find}>
              <Search size={17} />
              {busy ? "Recherche…" : "Identifier avec MusicBrainz"}
            </button>
            <button onClick={() => onManage(a.id, a.title)}>
              <MoreHorizontal size={18} /> Gérer l’album
            </button>
          </div>
          {a.mbid && (
            <p className="muted">
              Référence :{" "}
              <a
                target="_blank"
                rel="noreferrer"
                href={`https://musicbrainz.org/release/${a.mbid}`}
              >
                voir l’édition MusicBrainz
              </a>
            </p>
          )}
          {matches && (
            <section className="matches">
              <h3>Choisissez l’édition qui correspond à votre album</h3>
              <p className="muted">
                Cette référence sert à comparer les pistes. Elle ne modifie pas
                les tags de vos fichiers.
              </p>
              {matches.map((m) => (
                <button
                  key={m.id}
                  disabled={busy}
                  onClick={() => identify(m.id)}
                >
                  <span>
                    <strong>{m.title}</strong>
                    <small>
                      {m.artist} · {m.date} · {m.country} · {m.tracks} pistes{" "}
                      {m.disambiguation}
                    </small>
                  </span>
                  <ChevronRight size={18} />
                </button>
              ))}
              {!matches.length && (
                <p>
                  Aucune édition trouvée. Vérifiez les tags artiste et album.
                </p>
              )}
            </section>
          )}
          <h3>Pistes présentes</h3>
          <div className="song-list">
            {a.songs?.map((t) => (
              <button
                className={playing?.id === t.id ? "playing" : ""}
                key={t.id}
                onClick={() => setPlaying(t)}
                aria-label={`Préécouter ${t.title}`}
              >
                <span>
                  {t.disc > 1 ? `${t.disc}.` : ""}
                  {t.number || "–"}
                </span>
                <span>
                  <strong>{t.title}</strong>
                  <small>
                    {t.artist} · {t.format} · {t.bitrate} kb/s
                  </small>
                </span>
                <span>{duration(t.duration)}</span>
                <Play size={16} />
              </button>
            ))}
          </div>
          {playing && (
            <div className="audio-player">
              <strong>{playing.title}</strong>
              <audio
                controls
                autoPlay
                src={`/api/tracks/${playing.id}/stream`}
                onError={() =>
                  setFailure(
                    "La préécoute de ce format est indisponible dans ce navigateur. Utilisez Navidrome.",
                  )
                }
              />
            </div>
          )}
          {a.missing.length > 0 && (
            <section className="missing">
              <h3>Pistes manquantes</h3>
              {a.missing.map((t) => (
                <p key={`${t.disc}-${t.number}`}>
                  Disque {t.disc}, piste {t.number} : {t.title}
                </p>
              ))}
            </section>
          )}
          <MetadataEditor album={a} refresh={refresh} tell={tell} />
        </>
      ) : (
        <p>Chargement de l’album…</p>
      )}
    </Dialog>
  );
}
function Completeness({
  revision,
  onOpen,
}: {
  revision: number;
  onOpen: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const { data, error } = useResource<{ items: Album[]; total: number }>(
    `/albums?limit=60&attention=true&offset=${offset}`,
    revision,
  );
  return (
    <>
      <p className="muted">
        Les totaux inscrits dans les fichiers donnent une première indication.
        Choisissez une édition MusicBrainz dans la fiche album pour une
        comparaison précise, disque par disque.
      </p>
      <ErrorMessage message={error} />
      {data?.items.map((a) => (
        <section className="incomplete" key={a.id}>
          <Cover album={a} />
          <div>
            <span
              className={`badge ${a.completeness === "complete" ? "good" : ""}`}
            >
              {a.completeness === "complete"
                ? "Complet selon la référence"
                : a.completeness === "incomplete"
                  ? "Pistes manquantes"
                  : "Référence à vérifier"}
            </span>
            <h2>{a.title}</h2>
            <p>{a.artist}</p>
            {a.expected && (
              <>
                <div className="progress">
                  <span
                    style={{
                      width: `${Math.min(100, (a.tracks / a.expected) * 100)}%`,
                    }}
                  />
                </div>
                <p>
                  {a.tracks} pistes présentes / {a.expected} attendues
                </p>
              </>
            )}
            {a.missing.map((t) => (
              <p key={`${t.disc}-${t.number}`}>
                {t.disc}.{t.number} · {t.title}
              </p>
            ))}
            <button onClick={() => onOpen(a.id)}>
              Voir et identifier l’album <ArrowRight size={16} />
            </button>
          </div>
        </section>
      ))}
      {data && data.total > 60 && (
        <div className="pagination">
          <button disabled={!offset} onClick={() => setOffset((o) => o - 60)}>
            Précédent
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 60, data.total)} / {data.total}
          </span>
          <button
            disabled={offset + 60 >= data.total}
            onClick={() => setOffset((o) => o + 60)}
          >
            Suivant
          </button>
        </div>
      )}
      {data && !data.items.length && <Empty title="Aucun album à vérifier" />}
    </>
  );
}
function Duplicates({
  revision,
  onOpen,
}: {
  revision: number;
  onOpen: (id: string) => void;
}) {
  const { data, error, loading } = useResource<{
    items: { type: string; tracks: Song[] }[];
    total: number;
  }>("/duplicates", revision);
  return (
    <>
      <p className="muted">
        Un doublon exact partage la même empreinte SHA-256. Les versions portant
        le même artiste et titre restent à comparer : le débit seul ne prouve
        pas la qualité.
      </p>
      <ErrorMessage message={error} />
      {loading && <p>Lecture des empreintes…</p>}
      {data && !data.items.length && (
        <Empty title="Aucun doublon détecté">
          <p>
            Les fichiers indexés ne présentent pas de doublon selon ces
            critères.
          </p>
        </Empty>
      )}
      {data?.items.map((group, i) => (
        <section key={i}>
          <div className="section-heading">
            <h2>
              {group.tracks[0].artist} — {group.tracks[0].title}
            </h2>
            <span className="badge">
              {group.type === "exact"
                ? "Fichiers identiques"
                : "Versions à comparer"}
            </span>
          </div>
          <div className="compare">
            {group.tracks.map((t) => (
              <div key={t.id}>
                <h3>
                  {t.format} · {t.bitrate} kb/s
                </h3>
                <p>
                  {duration(t.duration)} · {t.sampleRate / 1000} kHz ·{" "}
                  {t.bitDepth || "–"} bits
                </p>
                <p className="file-location">
                  {t.zone} / {t.rel}
                </p>
                <audio
                  controls
                  preload="none"
                  src={`/api/tracks/${t.id}/stream`}
                />
                <button onClick={() => onOpen(t.albumId)}>
                  Ouvrir l’album
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
function Discovery({
  artists,
  onOpenArtist,
  tell,
}: {
  artists: string[];
  onOpenArtist: (name: string) => void;
  tell: (s: string) => void;
}) {
  const [artist, setArtist] = useState(""),
    [rev, setRev] = useState(0);
  const seed = artist || artists[0] || "";
  const { data, error, loading } = useResource<{
    items: { name: string; present: boolean; mbid?: string }[];
    source: string;
    followed: string[];
  }>(seed ? `/discover?artist=${encodeURIComponent(seed)}` : null, rev);
  return (
    <>
      <label className="field">
        Artiste de départ
        <select value={seed} onChange={(e) => setArtist(e.target.value)}>
          {artists.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
      </label>
      <ErrorMessage message={error} />
      {loading && <p>Recherche d’artistes proches…</p>}
      {data && <p className="muted">{data.source}</p>}
      {data?.items.map((a) => (
        <div className="action-row" key={a.name}>
          <Compass size={24} />
          <div>
            <strong>{a.name}</strong>
            <span>
              {a.present ? "Présent dans votre bibliothèque" : "À découvrir"}
            </span>
          </div>
          {a.present ? (
            <button onClick={() => onOpenArtist(a.name)}>Mes albums</button>
          ) : (
            <a
              className="button-link"
              href={`https://musicbrainz.org/search?query=${encodeURIComponent(a.name)}&type=artist&method=indexed`}
              target="_blank"
              rel="noreferrer"
            >
              Discographie <ExternalLink size={15} />
            </a>
          )}
          <button
            aria-label={`${data.followed.includes(a.name) ? "Ne plus suivre" : "Suivre"} ${a.name}`}
            onClick={async () => {
              try {
                await api("/follow", { name: a.name });
                setRev((r) => r + 1);
              } catch (e) {
                tell((e as Error).message);
              }
            }}
          >
            <Heart
              size={17}
              fill={data.followed.includes(a.name) ? "currentColor" : "none"}
            />
          </button>
        </div>
      ))}
      {data && !data.items.length && (
        <Empty title="Pas encore de suggestion">
          <p>
            Connectez Navidrome dans Paramètres pour interroger ses artistes
            similaires. Une petite collection peut aussi ne contenir aucun autre
            artiste du même genre.
          </p>
        </Empty>
      )}
      {!!data?.followed.length && (
        <section className="following">
          <h2>Artistes à découvrir</h2>
          {data.followed.map((n) => (
            <p key={n}>{n}</p>
          ))}
        </section>
      )}
    </>
  );
}
function RadioPanel({
  artists,
  tell,
}: {
  artists: string[];
  tell: (s: string) => void;
}) {
  const [artist, setArtist] = useState(""),
    [songs, setSongs] = useState<Song[]>([]),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const seed = artist || artists[0] || "";
  const generate = async () => {
    setLoading(true);
    setError("");
    try {
      setSongs(
        (
          await api<{ items: Song[] }>(
            `/radio?artist=${encodeURIComponent(seed)}`,
          )
        ).items,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <section className="radio-panel">
      <div className="radio-symbol">
        <Radio size={52} />
      </div>
      <h2>Vos disques, un autre chemin.</h2>
      <p>
        Une sélection locale, à partir d’un artiste et des genres présents dans
        votre collection.
      </p>
      <label>
        Artiste de départ
        <select
          value={seed}
          onChange={(e) => {
            setArtist(e.target.value);
            setSongs([]);
          }}
        >
          {artists.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
      </label>
      <button
        className="primary"
        disabled={!seed || loading}
        onClick={generate}
      >
        <Plus size={18} />
        {loading ? "Création…" : "Créer la sélection"}
      </button>
      <ErrorMessage message={error} />
      {songs.length > 0 && (
        <div className="playlist">
          <div className="section-heading">
            <h2>
              {songs.length} morceaux autour de {seed}
            </h2>
          </div>
          <div className="detail-actions">
            <button
              onClick={() => {
                const text =
                  "#EXTM3U\n" +
                  songs
                    .map(
                      (t) =>
                        `#EXTINF:${Math.round(t.duration)},${t.artist.replace(/[\r\n]/g, " ")} - ${t.title.replace(/[\r\n]/g, " ")}\n/music/${t.rel}`,
                    )
                    .join("\n");
                const url = URL.createObjectURL(
                  new Blob([text], { type: "audio/x-mpegurl" }),
                );
                const link = document.createElement("a");
                link.href = url;
                link.download = "music-manager.m3u";
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download size={16} />
              Exporter M3U
            </button>
            <button
              onClick={async () => {
                setLoading(true);
                try {
                  await api("/navidrome/playlist", {
                    name: `Music Manager — ${seed}`,
                    trackIds: songs.map((t) => t.id),
                  });
                  tell(
                    "Playlist créée dans Navidrome. Retrouvez-la aussi dans Amperfy.",
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setLoading(false);
                }
              }}
              disabled={loading}
            >
              <ListMusic size={17} />
              Envoyer à Navidrome
            </button>
          </div>
          {songs.map((t, i) => (
            <div className="playlist-row" key={t.id}>
              <span>{i + 1}</span>
              <strong>{t.title}</strong>
              <span>
                {t.artist} · {duration(t.duration)}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
type HistoryItem = {
  id: string;
  created: string;
  action: string;
  source: string;
  target: string;
  status: string;
  error: string | null;
};
function HistoryPanel({
  revision,
  refresh,
  tell,
}: {
  revision: number;
  refresh: () => void;
  tell: (s: string) => void;
}) {
  const { data, error } = useResource<{ items: HistoryItem[] }>(
    "/history",
    revision,
  );
  const [busy, setBusy] = useState(false);
  const restore = async (op: HistoryItem) => {
    setBusy(true);
    try {
      await api(`/history/${op.id}/restore`, {});
      tell("Restauration effectuée. L’index se met à jour.");
      refresh();
      setTimeout(refresh, 1500);
    } catch (e) {
      tell((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <h2>Historique et éléments récupérables</h2>
      <p className="muted">
        La corbeille conserve les fichiers écartés. Aucune suppression
        définitive ni purge automatique n’est activée. La restauration refuse
        les collisions.
      </p>
      <ErrorMessage message={error} />
      {data && !data.items.length && (
        <Empty title="Aucune opération pour le moment">
          <p>
            Les déplacements, renommages, éditions de tags et restaurations
            seront consignés ici.
          </p>
        </Empty>
      )}
      {data?.items.map((op) => (
        <section className="operation" key={op.id}>
          <div className="section-heading">
            <h3>
              {(
                {
                  trash: "Mise à la corbeille",
                  move: "Déplacement",
                  move_file: "Déplacement d’une piste",
                  rename: "Renommage",
                  metadata: "Modification des tags",
                } as Record<string, string>
              )[op.action] || op.action}
            </h3>
            <span className="badge">
              {(
                {
                  applied: "Effectuée",
                  restored: "Restaurée",
                  failed: "Échec",
                  rolled_back: "Annulée",
                  pending: "À vérifier",
                  needs_review: "Contrôle requis",
                  restoring: "Restauration interrompue",
                } as Record<string, string>
              )[op.status] || op.status}
            </span>
          </div>
          <p>{new Date(op.created).toLocaleString("fr-FR")}</p>
          <p className="file-location">{op.source}</p>
          <p className="file-location">Destination : {op.target}</p>
          {op.error && <p className="error">{op.error}</p>}
          {op.status === "applied" && (
            <button disabled={busy} onClick={() => restore(op)}>
              <RotateCcw size={17} />
              Restaurer l’état précédent
            </button>
          )}
        </section>
      ))}
    </>
  );
}
function SettingsPanel({
  status,
  refresh,
  tell,
}: {
  status: Status | null;
  refresh: () => void;
  tell: (s: string) => void;
}) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [minutes, setMinutes] = useState<number | null>(null);
  return (
    <div className="settings">
      <InstallApp />
      <section>
        <h2>Connexion Navidrome</h2>
        <p>
          Utilisez votre compte actuel. Le mot de passe sert à authentifier la
          connexion ; il n’est pas conservé en clair. Un jeton Subsonic
          équivalent reste dans les données privées de l’application sur le
          serveur.
        </p>
        <div className="connection">
          <span>Service</span>
          <span
            className={`badge ${status?.navidrome.connected ? "good" : ""}`}
          >
            {status?.navidrome.connected
              ? "Connecté"
              : status?.navidrome.configured
                ? "Indisponible"
                : "Compte à connecter"}
          </span>
        </div>
        {status?.session ? (
          <>
            <p>
              Connecté comme <strong>{status.session.username}</strong> ·{" "}
              {status.session.admin ? "administrateur" : "utilisateur"}
            </p>
            <button
              onClick={async () => {
                await api("/session", undefined, "DELETE");
                refresh();
              }}
            >
              Déconnecter ce navigateur
            </button>
            {status.session.admin && (
              <button
                className="secondary-action"
                onClick={async () => {
                  try {
                    await api("/navidrome/scan", {});
                    tell("Analyse de Navidrome lancée.");
                  } catch (e) {
                    tell((e as Error).message);
                  }
                }}
              >
                <RotateCcw size={16} />
                Analyser dans Navidrome
              </button>
            )}
          </>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api("/session", { username, password });
                setPassword("");
                refresh();
                tell("Connexion Navidrome établie.");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Nom d’utilisateur
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label>
              Mot de passe
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <ErrorMessage message={error} />
            <button className="primary" disabled={busy}>
              <LogIn size={17} />
              {busy ? "Connexion…" : "Connecter mon compte"}
            </button>
          </form>
        )}
        <p className="muted">
          Les modifications de fichiers demandent un compte administrateur
          Navidrome et une confirmation pour chaque opération.
        </p>
        <a
          className="button-link"
          target="_blank"
          rel="noreferrer"
          href={status?.navidrome.url || "http://100.120.247.35:4533"}
        >
          Ouvrir Navidrome <ExternalLink size={16} />
        </a>
      </section>
      <section>
        <h2>Répertoires connectés</h2>
        {status &&
          Object.entries(status.roots).map(([name, path]) => (
            <label key={name}>
              {name}
              <input readOnly value={path} />
            </label>
          ))}
        <p className="muted">
          Montage contrôlé côté serveur. Les liens symboliques et chemins hors
          de ces espaces sont refusés.
        </p>
      </section>
      <section>
        <h2>Indexation</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await api(
                "/preferences",
                { scanMinutes: minutes ?? status?.scanMinutes ?? 0 },
                "PUT",
              );
              refresh();
              tell("Fréquence d’analyse enregistrée.");
            } catch (e) {
              tell((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Fréquence
            <select
              value={minutes ?? status?.scanMinutes ?? 0}
              onChange={(e) => setMinutes(Number(e.target.value))}
            >
              <option value={0}>Manuelle</option>
              <option value={60}>Chaque heure</option>
              <option value={1440}>Chaque jour</option>
              <option value={10080}>Chaque semaine</option>
            </select>
          </label>
          <button disabled={busy || !status?.session?.admin}>
            <Check size={16} />
            Enregistrer
          </button>
        </form>
        <p>
          Dernière analyse :{" "}
          {status?.scan.lastScan
            ? new Date(status.scan.lastScan).toLocaleString("fr-FR")
            : "en attente"}
        </p>
      </section>
      <section>
        <h2>Sources musicales</h2>
        <div className="connection">
          <span>MusicBrainz</span>
          <span>Recherche d’édition à la demande</span>
        </div>
        <div className="connection">
          <span>Artistes similaires</span>
          <span>Via Navidrome, sinon genres locaux</span>
        </div>
        <div className="connection">
          <span>Deemix</span>
          <span>Dossier incoming surveillé par l’index</span>
        </div>
        <div className="connection">
          <span>Amperfy</span>
          <span>Playlists via votre serveur Navidrome</span>
        </div>
      </section>
    </div>
  );
}
type Plan = {
  token: string;
  action: string;
  items: { album: string; source: string; target: string; files: number }[];
};
function ManageDialog({
  ids,
  name,
  onClose,
  onDone,
  tell,
}: {
  ids: string[];
  name: string;
  onClose: () => void;
  onDone: () => void;
  tell: (s: string) => void;
}) {
  const [action, setAction] = useState("move"),
    [destination, setDestination] = useState("Bibliothèque"),
    [newName, setNewName] = useState(""),
    [plan, setPlan] = useState<Plan | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Dialog title={`Gérer ${name}`} onClose={onClose}>
      <ErrorMessage message={error} />
      {!plan ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              setPlan(
                await api<Plan>("/operations/preview", {
                  albumIds: ids,
                  action,
                  destinationZone: destination,
                  newName,
                }),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            Action
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="move">Déplacer</option>
              {ids.length === 1 && (
                <option value="rename">Renommer le dossier</option>
              )}
              <option value="trash">Mettre à la corbeille</option>
            </select>
          </label>
          {action === "move" && (
            <label className="field">
              Destination
              <select
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </select>
            </label>
          )}
          {action === "rename" && (
            <label className="field">
              Nouveau nom
              <input
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </label>
          )}
          <p className="muted">
            Le dossier complet est déplacé lorsqu’il appartient à un seul album, y
            compris ses pochettes. Dans une compilation ou un dossier partagé,
            seuls les fichiers des albums sélectionnés sont déplacés, en conservant
            leurs tags. Aucune destination existante n’est écrasée.
          </p>
          <button className="primary" disabled={busy}>
            {busy ? "Vérification…" : "Prévisualiser l’opération"}
          </button>
        </form>
      ) : (
        <>
          <p>
            Vérifiez les chemins avant de confirmer. Cette opération concerne
            les fichiers réels du serveur.
          </p>
          {plan.items.map((item) => (
            <div className="plan-item" key={item.source}>
              <h3>{item.album}</h3>
              <p>{item.files} fichiers</p>
              <p className="file-location">De : {item.source}</p>
              <p className="file-location">Vers : {item.target}</p>
            </div>
          ))}
          <div className="detail-actions">
            <button onClick={() => setPlan(null)}>Modifier</button>
            <button
              className="primary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await api("/operations/apply", { token: plan.token });
                  tell("Opération terminée et consignée dans l’historique.");
                  onDone();
                } catch (e) {
                  setError((e as Error).message);
                  setPlan(null);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy
                ? "Opération en cours…"
                : "Confirmer sur les fichiers réels"}
            </button>
          </div>
        </>
      )}
    </Dialog>
  );
}
function MetadataEditor({
  album,
  refresh,
  tell,
}: {
  album: Album;
  refresh: () => void;
  tell: (s: string) => void;
}) {
  const [editing, setEditing] = useState(false),
    [values, setValues] = useState({
      artist: album.artist,
      album: album.title,
      year: String(album.year || ""),
      genre: album.genre === "Non renseigné" ? "" : album.genre,
    }),
    [plan, setPlan] = useState<{
      token: string;
      changes: Record<string, { before: string[]; after: string }>;
    } | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <section className="metadata-editor">
      <h3>Tags de l’album</h3>
      {!editing ? (
        <button onClick={() => setEditing(true)}>
          <PenLine size={17} />
          Modifier les tags
        </button>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              setPlan(
                await api(`/albums/${album.id}/metadata/preview`, values),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {Object.entries({
            artist: "Artiste de l’album",
            album: "Album",
            year: "Année",
            genre: "Genre",
          }).map(([key, label]) => (
            <label className="field" key={key}>
              {label}
              <input
                value={values[key as keyof typeof values]}
                onChange={(e) => {
                  setPlan(null);
                  setValues((v) => ({ ...v, [key]: e.target.value }));
                }}
                required={key === "album" || key === "artist"}
              />
            </label>
          ))}
          <ErrorMessage message={error} />
          {plan ? (
            <>
              <h3>Modifications prévues</h3>
              {Object.entries(plan.changes).map(([key, v]) => (
                <p key={key}>
                  {key} : {v.before.join(", ") || "vide"} →{" "}
                  <strong>{v.after || "vide"}</strong>
                </p>
              ))}
              <p className="muted">
                Une copie de sécurité complète est conservée avant écriture.
                Vous pourrez restaurer les fichiers depuis l’historique.
              </p>
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api("/metadata/apply", { token: plan.token });
                    setEditing(false);
                    refresh();
                    setTimeout(refresh, 1500);
                    tell(
                      "Tags enregistrés. Copie de sécurité disponible dans l’historique.",
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Confirmer l’écriture des tags
              </button>
            </>
          ) : (
            <button disabled={busy}>Prévisualiser les modifications</button>
          )}
          <button
            type="button"
            className="secondary-action"
            onClick={() => {
              setEditing(false);
              setPlan(null);
            }}
          >
            Annuler
          </button>
        </form>
      )}
    </section>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
