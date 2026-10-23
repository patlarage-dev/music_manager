export type Song = {
  id: string;
  albumId: string;
  title: string;
  artist: string;
  album: string;
  rel: string;
  zone: string;
  number: number;
  disc: number;
  duration: number;
  format: string;
  bitrate: number;
  sampleRate: number;
  bitDepth: number;
  size: number;
};
export type Missing = { disc: number; number: number; title: string };
export type Album = {
  id: string;
  artist: string;
  title: string;
  year: number;
  genre: string;
  tracks: number;
  expected: number | null;
  format: string;
  zone: string;
  folder: string;
  cover: string | null;
  duration: number;
  mbid: string;
  missing: Missing[];
  completeness: "complete" | "incomplete" | "unknown";
  reference?: { title: string; date: string };
  songs?: Song[];
};
export type Status = {
  scan: {
    running: boolean;
    processed: number;
    errors: string[];
    lastScan: string | null;
  };
  stats: {
    artists: number;
    albums: number;
    tracks: number;
    quarantine: number;
    incoming: number;
    incomplete: number;
  };
  navidrome: {
    configured: boolean;
    connected: boolean;
    username: string | null;
    url: string;
  };
  session: { username: string; admin: boolean; canManageFiles: boolean } | null;
  disk: { free: number; total: number } | null;
  scanMinutes: number;
  roots: Record<string, string>;
};
export async function api<T>(
  url: string,
  body?: unknown,
  method?: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api" + url, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers:
      body !== undefined || method
        ? { "Content-Type": "application/json", "X-Music-Manager": "1" }
        : undefined,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let message = "Le serveur ne répond pas. Réessayez.";
    try {
      const error = await response.json();
      if (typeof error.detail === "string") message = error.detail;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}
export const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
export const bytes = (size: number) =>
  new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(
    size / 1024 ** 3,
  ) + " Go";
