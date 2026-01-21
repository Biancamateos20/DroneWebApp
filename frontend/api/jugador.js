export async function onRequestPost({ request }) {
  const data = await request.json().catch(() => null);

  if (!data || !data.alias) {
    return new Response(JSON.stringify({ error: "Falta alias" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ ok: true, alias: data.alias }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
