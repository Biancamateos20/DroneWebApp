export async function onRequestPost({ request }) {
  const data = await request.json().catch(() => null);

  if (!data) {
    return new Response(JSON.stringify({ error: "JSON inválido" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Para la demo: confirmamos recepción
  return new Response(JSON.stringify({ ok: true, received: data }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
