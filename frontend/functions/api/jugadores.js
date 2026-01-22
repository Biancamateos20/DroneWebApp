const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getStore() {
  if (!globalThis.__players) globalThis.__players = new Map();
  return globalThis.__players;
}

export async function onRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (request.method !== "GET") {
    return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
  }

  const store = getStore();
  const jugadores = Array.from(store.values());

  return new Response(JSON.stringify(jugadores), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
