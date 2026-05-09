const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getGameState() {
  if (!globalThis.__gameState) {
    globalThis.__gameState = {
      juego_en_curso: false,
      dron_despegado: false,
      jugador_actual_alias: null,
      siguiente_jugador_alias: null,
      foto_tomada_alias: null,
      voz_objetivo_alias: null,
      voz_comando_id: 0,
      reset_id: 0,
      game_start_id: 0
    };
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
    dron_despegado: !!game.dron_despegado,
    jugador_actual_alias: game.jugador_actual_alias || null,
    siguiente_jugador_alias: game.siguiente_jugador_alias || null,
    foto_tomada_alias: game.foto_tomada_alias || null,
    voz_objetivo_alias: game.voz_objetivo_alias || null,
    voz_comando_id: Number(game.voz_comando_id || 0),
    game_start_id: game.game_start_id,
    reset_id: Number(game.reset_id || 0),
  }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
