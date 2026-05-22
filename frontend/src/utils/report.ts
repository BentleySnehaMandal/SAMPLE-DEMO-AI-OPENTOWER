/**
 * Triggers a PDF download by assigning window.location.href.
 * The browser sees Content-Disposition: attachment on the response and
 * saves the file without navigating away from the current page.
 * This avoids both CORS (no fetch/XHR used) and the cross-origin
 * `download` attribute limitation (which browsers silently ignore).
 */
export function downloadReportBlob(sessionId: string): void {
  if (!sessionId) {
    console.warn('downloadReportBlob: no session ID');
    return;
  }
  window.location.href = `http://localhost:8000/session/${sessionId}/report`;
}
