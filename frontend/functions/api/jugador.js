const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getStore() {
  // Memoria (vale para pruebas)
  if (!globalThis.__players) globalThis.__players = new Map();
  return globalThis.__players;
}

export async function onRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
  }

  const data = await request.json().catch(() => null);
  if (!data || !data.alias) {
    return new Response(JSON.stringify({ error: "Falta alias" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const store = getStore();
  const prev = store.get(data.alias) || { alias: data.alias };

  const jugador = {
    ...prev,
    alias: data.alias,
    lat: data.lat ?? prev.lat ?? null,
    lon: data.lon ?? prev.lon ?? null,
    precision: data.precision ?? prev.precision ?? null,
    ts: data.ts ?? prev.ts ?? null,
    updatedAt: Date.now(),
  };

  store.set(data.alias, jugador);

  return new Response(JSON.stringify({ ok: true, jugador }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
