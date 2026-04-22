declare global {
  interface Window {
    __AIASK_CAPTURE_EXCEPTION__?: (error: unknown) => void;
  }
}

export function reportClientException(error: unknown) {
  if (typeof window === 'undefined') return;
  try {
    window.__AIASK_CAPTURE_EXCEPTION__?.(error);
  } catch {
    // Ignore telemetry failures on the client recovery path.
  }
}
