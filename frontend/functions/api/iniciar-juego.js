const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

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

  const game = getGameState();
  game.juego_en_curso = true;
  game.game_start_id = Number(game.game_start_id || 0) + 1;

  return new Response(JSON.stringify({
    ok: true,
    juego_en_curso: game.juego_en_curso,
    game_start_id: game.game_start_id,
    reset_id: Number(game.reset_id || 0),
  }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
