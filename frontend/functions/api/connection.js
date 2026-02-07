const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function getState() {
  if (!globalThis.__droneState) {
    globalThis.__droneState = { connected: false };
  }
  return globalThis.__droneState;
}

export async function onRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
  }

  const state = getState();
  state.connected = true;

  return new Response(JSON.stringify({ ok: true, connected: state.connected }), {
    status: 200,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
