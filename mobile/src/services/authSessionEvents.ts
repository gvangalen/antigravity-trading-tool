type Listener = () => void;

const listeners = new Set<Listener>();

export function subscribeAuthSessionInvalidated(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function notifyAuthSessionInvalidated(): void {
  for (const listener of listeners) listener();
}
