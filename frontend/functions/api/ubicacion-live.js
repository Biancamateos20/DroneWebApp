const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getStore() {
  if (!globalThis.__players) globalThis.__players = new Map();
  return globalThis.__players;
}

function getPlayerAliasMap() {
  if (!globalThis.__playerAliasById) globalThis.__playerAliasById = new Map();
  return globalThis.__playerAliasById;
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
  if (!data || !data.alias || data.lat == null || data.lon == null) {
    return new Response(JSON.stringify({ error: "Faltan alias/lat/lon" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const alias = String(data.alias || "").trim();
  if (!alias) {
    return new Response(JSON.stringify({ error: "Alias inválido" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const lat = Number(data.lat);
  const lon = Number(data.lon);
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    return new Response(JSON.stringify({ error: "Lat/Lon inválidos" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const rawPlayerId = data.playerId ?? data.player_id ?? null;
  const playerId = rawPlayerId == null ? null : (String(rawPlayerId).trim() || null);

  const store = getStore();
  const playerAlias = getPlayerAliasMap();

  if (playerId) {
    const prevAlias = playerAlias.get(playerId);
    if (prevAlias && prevAlias !== alias) {
      store.delete(prevAlias);
    }
  }

  const prev = store.get(alias) || { alias };
  const jugador = {
    ...prev,
    alias,
    playerId: playerId ?? prev.playerId ?? null,
    lat,
    lon,
    precision: data.precision ?? prev.precision ?? null,
    ts: data.ts ?? Date.now(),
    updatedAt: Date.now(),
  };

  store.set(alias, jugador);
  if (playerId) {
    playerAlias.set(playerId, alias);
  }

  return new Response(JSON.stringify({ ok: true, jugador }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
