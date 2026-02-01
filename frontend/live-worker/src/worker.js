import { PartyDO } from "./party_do.js";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function withCors(resp) {
  const headers = new Headers(resp.headers);
  for (const [k, v] of Object.entries(cors)) headers.set(k, v);
  return new Response(resp.body, { status: resp.status, headers });
}

export { PartyDO };

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    const url = new URL(request.url);
    const game = url.searchParams.get("game") || "demo";

    const id = env.PARTY.idFromName(game);
    const stub = env.PARTY.get(id);

    const resp = await stub.fetch(request);
    return withCors(resp);
  },
};
