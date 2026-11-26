// The only place that talks to the server.

const TIMEOUT_MS = 45_000; // the server may try several AI models before it answers

export class ApiError extends Error {}

export async function postJson(path, body, { networkMessage, genericMessage }) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(networkMessage);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // fall through to the generic message below
  }
  if (!response.ok) throw new ApiError(typeof data?.error === "string" ? data.error : genericMessage);
  if (data === null || typeof data !== "object") throw new ApiError(genericMessage);
  return data;
}
