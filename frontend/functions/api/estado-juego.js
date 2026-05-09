const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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

  if (request.method !== "GET" && request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
  }

  const game = getGameState();

  if (request.method === "POST") {
    const data = await request.json().catch(() => null);
    if (!data || typeof data !== "object") {
      return new Response(JSON.stringify({ error: "Body invalido" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if ("juego_en_curso" in data) {
      game.juego_en_curso = !!data.juego_en_curso;
    }

    if ("dron_despegado" in data) {
      game.dron_despegado = !!data.dron_despegado;
    }

    if ("jugador_actual_alias" in data) {
      game.jugador_actual_alias = data.jugador_actual_alias == null
        ? null
        : (String(data.jugador_actual_alias).trim().toUpperCase() || null);
    }

    if ("siguiente_jugador_alias" in data) {
      game.siguiente_jugador_alias = data.siguiente_jugador_alias == null
        ? null
        : (String(data.siguiente_jugador_alias).trim().toUpperCase() || null);
    }

    if ("foto_tomada_alias" in data) {
      game.foto_tomada_alias = data.foto_tomada_alias == null
        ? null
        : (String(data.foto_tomada_alias).trim().toUpperCase() || null);
    }

    if ("voz_objetivo_alias" in data) {
      game.voz_objetivo_alias = data.voz_objetivo_alias == null
        ? null
        : (String(data.voz_objetivo_alias).trim().toUpperCase() || null);
    }

    if ("voz_comando_id" in data) {
      game.voz_comando_id = Number(data.voz_comando_id || 0);
    }
  }

  return new Response(JSON.stringify({
    juego_en_curso: !!game.juego_en_curso,
    dron_despegado: !!game.dron_despegado,
    jugador_actual_alias: game.jugador_actual_alias || null,
    siguiente_jugador_alias: game.siguiente_jugador_alias || null,
    foto_tomada_alias: game.foto_tomada_alias || null,
    voz_objetivo_alias: game.voz_objetivo_alias || null,
    voz_comando_id: Number(game.voz_comando_id || 0),
    reset_id: Number(game.reset_id || 0),
    game_start_id: Number(game.game_start_id || 0),
  }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
