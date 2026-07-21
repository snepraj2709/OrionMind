type SessionCleanup = () => void | Promise<void>;

const cleanupCallbacks = new Set<SessionCleanup>();
const pendingControllers = new Set<AbortController>();
const userScopedStoragePrefix = 'orion:user:';

export function registerSessionCleanup(cleanup: SessionCleanup) {
  cleanupCallbacks.add(cleanup);
  return () => cleanupCallbacks.delete(cleanup);
}

export function createSessionAbortController() {
  const controller = new AbortController();
  pendingControllers.add(controller);
  controller.signal.addEventListener(
    'abort',
    () => pendingControllers.delete(controller),
    { once: true },
  );
  return controller;
}

export function releaseSessionAbortController(controller: AbortController) {
  pendingControllers.delete(controller);
}

function removeUserScopedKeys(storage: Storage) {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(userScopedStoragePrefix)) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}

export async function clearUserScopedState() {
  pendingControllers.forEach((controller) =>
    controller.abort('session-boundary'),
  );
  pendingControllers.clear();

  if (typeof window !== 'undefined') {
    removeUserScopedKeys(window.localStorage);
    removeUserScopedKeys(window.sessionStorage);
  }

  await Promise.allSettled(
    [...cleanupCallbacks].map(async (cleanup) => cleanup()),
  );
}
