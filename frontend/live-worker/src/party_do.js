export class PartyDO {
  constructor(state, env) {
    this.state = state;
    this.env = env;

    this.sockets = new Map();   // connId -> WebSocket
    this.connMeta = new Map();  // connId -> { role, alias, playerId }

    this.players = new Map();   // alias -> {alias, lat, lon, precision, ts, ...}
    this.gameState = { juego_en_curso: false, reset_id: 0 };

    this.pendingPersist = false;

    state.blockConcurrencyWhile(async () => {
      const storedPlayers = await this.state.storage.get("players");
      if (storedPlayers && Array.isArray(storedPlayers)) {
        for (const p of storedPlayers) if (p?.alias) this.players.set(p.alias, p);
      }

      const storedState = await this.state.storage.get("gameState");
      if (storedState && typeof storedState === "object") {
        this.gameState = {
          juego_en_curso: !!storedState.juego_en_curso,
          reset_id: Number(storedState.reset_id ?? 0),
        };
      }
    });
  }

  // ---------------- utils
  getSnapshot() {
    return Array.from(this.players.values());
  }

  getAliases() {
    return this.getSnapshot().map(p => p.alias);
  }

  send(ws, obj) {
    try { ws.send(JSON.stringify(obj)); } catch {}
  }

  broadcastAll(obj) {
    const msg = JSON.stringify(obj);
    for (const ws of this.sockets.values()) {
      try { ws.send(msg); } catch {}
    }
  }

  broadcastToAdmins(obj) {
    const msg = JSON.stringify(obj);
    for (const [id, ws] of this.sockets.entries()) {
      const meta = this.connMeta.get(id);
      if (meta?.role === "admin") {
        try { ws.send(msg); } catch {}
      }
    }
  }

  schedulePersist() {
    if (this.pendingPersist) return;
    this.pendingPersist = true;
    this.state.storage.setAlarm(Date.now() + 1000);
  }

  async alarm() {
    await this.state.storage.put("players", this.getSnapshot());
    await this.state.storage.put("gameState", this.gameState);
    this.pendingPersist = false;

    // Limpieza players stale (10 min)
    const cutoff = Date.now() - 10 * 60 * 1000;
    for (const [alias, p] of this.players.entries()) {
      const ts = Number(p?.ts ?? 0);
      if (ts && ts < cutoff) this.players.delete(alias);
    }
  }

  // ---------------- handlers
  handleJoin(connId, data) {
    const role = data.role === "admin" ? "admin" : "player";
    const alias = data.alias ? String(data.alias) : null;
    const playerId = data.playerId ? String(data.playerId) : null;

    this.connMeta.set(connId, { role, alias, playerId });

    const ws = this.sockets.get(connId);
    if (!ws) return;

    // snapshot + estado juego al conectar
    this.send(ws, { type: "snapshot", players: this.getSnapshot() });
    this.send(ws, { type: "game_state", ...this.gameState });

    // ocupación a todos
    this.broadcastAll({ type: "occupancy", aliases: this.getAliases() });
  }

  handleLoc(connId, data) {
    const meta = this.connMeta.get(connId);
    if (!meta || meta.role !== "player") return;

    const alias = meta.alias || (data.alias ? String(data.alias) : null);
    if (!alias) return;

    const lat = Number(data.lat);
    const lon = Number(data.lon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;

    const precision = data.precision == null ? null : Number(data.precision);
    const ts = data.ts ? Number(data.ts) : Date.now();

    const prev = this.players.get(alias) || { alias };

    const updated = {
      ...prev,
      alias,
      playerId: meta.playerId || prev.playerId || null,
      lat,
      lon,
      precision,
      ts,
      updatedAt: Date.now(),
    };

    // si era la primera vez, queda ocupado el color
    this.players.set(alias, updated);
    this.schedulePersist();

    // update instantáneo a admins
    this.broadcastToAdmins({ type: "player_update", player: updated });

    // occupancy a todos
    this.broadcastAll({ type: "occupancy", aliases: this.getAliases() });
  }

  handleStart(connId) {
    const meta = this.connMeta.get(connId);
    if (!meta || meta.role !== "admin") return;

    this.gameState.juego_en_curso = true;
    this.schedulePersist();
    this.broadcastAll({ type: "game_state", ...this.gameState });
  }

  handleReset(connId) {
    const meta = this.connMeta.get(connId);
    if (!meta || meta.role !== "admin") return;

    this.players.clear();
    this.gameState.juego_en_curso = false;
    this.gameState.reset_id += 1;

    this.schedulePersist();

    this.broadcastAll({ type: "reset", reset_id: this.gameState.reset_id });
    this.broadcastAll({ type: "occupancy", aliases: [] });
    this.broadcastAll({ type: "game_state", ...this.gameState });
  }

  // ---------------- router
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    // WebSocket
    const upgrade = request.headers.get("Upgrade");
    if (upgrade && upgrade.toLowerCase() === "websocket") {
      const pair = new WebSocketPair();
      const client = pair[0];
      const server = pair[1];

      server.accept();

      const connId = crypto.randomUUID();
      this.sockets.set(connId, server);

      this.send(server, { type: "hello", t: Date.now() });

      const cleanup = () => {
        this.sockets.delete(connId);
        this.connMeta.delete(connId);
      };

      server.addEventListener("close", cleanup);
      server.addEventListener("error", cleanup);

      server.addEventListener("message", (evt) => {
        let data;
        try { data = JSON.parse(evt.data); } catch { return; }

        if (data.type === "join") this.handleJoin(connId, data);
        else if (data.type === "loc") this.handleLoc(connId, data);
        else if (data.type === "start") this.handleStart(connId);
        else if (data.type === "reset") this.handleReset(connId);
        else if (data.type === "ping") this.send(server, { type: "pong", t: Date.now() });
      });

      return new Response(null, { status: 101, webSocket: client });
    }

    // Debug HTTP: ver jugadores
    if (path.endsWith("/jugadores") && request.method === "GET") {
      return new Response(JSON.stringify(this.getSnapshot()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Debug HTTP: ver estado juego
    if (path.endsWith("/estado-juego") && request.method === "GET") {
      return new Response(JSON.stringify(this.gameState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not Found", { status: 404 });
  }
}
