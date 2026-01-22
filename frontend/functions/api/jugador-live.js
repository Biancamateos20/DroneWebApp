function getStore() {
  if (!globalThis.__players) globalThis.__players = new Map();
  return globalThis.__players;
}

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export async function onRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: cors });
  }

  const data = await request.json().catch(() => null);
  if (!data || !data.alias || data.lat == null || data.lon == null) {
    return new Response(JSON.stringify({ error: "Faltan alias/lat/lon" }), {
      status: 400,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  }

  const store = getStore();

  const prev = store.get(data.alias) || { alias: data.alias };
  const jugador = {
    ...prev,
    alias: data.alias,
    lat: Number(data.lat),
    lon: Number(data.lon),
    precision: data.precision ?? prev.precision ?? null,
    ts: data.ts ?? Date.now(),
    updatedAt: Date.now(),
  };

  store.set(data.alias, jugador);

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
