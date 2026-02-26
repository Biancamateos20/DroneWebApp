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
  if (!data || !data.alias) {
    return new Response(JSON.stringify({ error: "Falta alias" }), {
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

  const existing = store.get(alias) || null;
  const existingPlayerId = existing?.playerId == null ? null : (String(existing.playerId).trim() || null);
  if (existing && existingPlayerId && existingPlayerId !== playerId) {
    return new Response(JSON.stringify({ error: "Color ya ocupado" }), {
      status: 409,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const prev = existing || { alias };

  const jugador = {
    ...prev,
    alias,
    playerId: playerId ?? prev.playerId ?? null,
    lat: data.lat ?? prev.lat ?? null,
    lon: data.lon ?? prev.lon ?? null,
    precision: data.precision ?? prev.precision ?? null,
    ts: data.ts ?? prev.ts ?? null,
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
