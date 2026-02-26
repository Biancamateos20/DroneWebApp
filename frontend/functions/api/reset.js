const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getStore() {
  if (!globalThis.__players) globalThis.__players = new Map();
  return globalThis.__players;
}

function getGameState() {
  if (!globalThis.__gameState) {
    globalThis.__gameState = { juego_en_curso: false, reset_id: 0, game_start_id: 0 };
  }
  return globalThis.__gameState;
}

export async function onRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
  }

  const store = getStore();
  store.clear();
  if (globalThis.__playerAliasById) {
    globalThis.__playerAliasById.clear();
  }

  const game = getGameState();
  game.juego_en_curso = false;
  game.reset_id = Number(game.reset_id || 0) + 1;

  if (globalThis.__droneState) {
    globalThis.__droneState.connected = false;
  }

  return new Response(JSON.stringify({
    ok: true,
    reset_id: game.reset_id,
    players: 0,
  }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
