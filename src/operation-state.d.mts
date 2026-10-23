export function createActionGate(): {
  isPending(): boolean;
  run<T>(work: () => Promise<T>): Promise<T | undefined>;
};
export type IndexState = {
  running: boolean;
  lastScan: string | null;
  errors?: string[];
};
export function waitForIndex(
  read: () => Promise<IndexState>,
  baseline: string | null,
  onRetry: (message: string) => void,
  delay?: () => Promise<void>,
): Promise<void>;
