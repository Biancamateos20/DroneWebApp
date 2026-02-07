// frontend/src/services/liveWS.js
// Versión robusta: NO rompe la app si falta VUE_APP_LIVE_URL.
// Si no hay URL, simplemente no conecta y loguea warning.

function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function toWsUrl(httpUrl) {
  if (!httpUrl) return ''
  const base = httpUrl.replace(/\/$/, '')
  if (base.startsWith('https://')) return base.replace('https://', 'wss://')
  if (base.startsWith('http://')) return base.replace('http://', 'ws://')
  return base
}

export class LiveWS {
  constructor() {
    // Vue CLI solo expone env con prefijo VUE_APP_
    this.baseUrl = (process.env.VUE_APP_LIVE_URL || '').trim()
    this.game = (process.env.VUE_APP_GAME || 'demo').trim()

    // no petar: si falta env, simplemente desactivamos
    this.enabled = !!this.baseUrl

    // Evitar mixed-content o localhost en producción
    try {
      const pageProtocol = window.location.protocol
      const pageHost = window.location.hostname
      const isHttpsPage = pageProtocol === 'https:'
      const isHttpBase = this.baseUrl.startsWith('http://')
      const isLocalBase = /^(http:\/\/|https:\/\/)?(localhost|127\.0\.0\.1)/i.test(this.baseUrl)
      const isLocalPage = /^(localhost|127\.0\.0\.1)$/i.test(pageHost)

      if ((isHttpsPage && isHttpBase) || (isLocalBase && !isLocalPage)) {
        this.enabled = false
        this.baseUrl = ''
      }
    } catch (e) {
      // si falla, no bloqueamos
    }

    this.ws = null
    this.role = 'player'
    this.isOpen = false

    this.onMessage = () => {}
    this.onOpen = () => {}
    this.onClose = () => {}

    this.backoff = 400
    this.maxBackoff = 8000
    this.pingTimer = null

    const raw = localStorage.getItem('player_session_v1')
    this.session = raw ? JSON.parse(raw) : { playerId: uuidv4(), alias: null }
    localStorage.setItem('player_session_v1', JSON.stringify(this.session))

    if (!this.enabled) {
      console.warn('[LiveWS] Falta VUE_APP_LIVE_URL. WS desactivado en este entorno.')
    }
  }

  setAlias(alias) {
    this.session.alias = alias
    localStorage.setItem('player_session_v1', JSON.stringify(this.session))
  }

  _wsUrl() {
    if (!this.enabled) return ''
    const wsBase = toWsUrl(this.baseUrl)
    return `${wsBase}/ws?game=${encodeURIComponent(this.game)}`
  }

  connect({ role = 'player', alias } = {}) {
    this.role = role
    if (alias) this.setAlias(alias)

    if (!this.enabled) return // ✅ no rompe nada

    const url = this._wsUrl()
    if (!url) return

    try { this.ws?.close() }  catch(e) { console.warn(e)}

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.backoff = 400
      this.isOpen = true
      this.send({
        type: 'join',
        role: this.role,
        alias: this.session.alias,
        playerId: this.session.playerId
      })
      this._startPing()
      this.onOpen()
    }

    this.ws.onmessage = (evt) => {
      let msg
      try { msg = JSON.parse(evt.data) } catch { return }
      this.onMessage(msg)
    }

    this.ws.onclose = () => {
      this._stopPing()
      this.isOpen = false
      this.onClose()
      this._reconnect()
    }

    this.ws.onerror = () => {
      // onclose maneja reconnect
    }
  }

  _reconnect() {
    if (!this.enabled) return
    const wait = this.backoff
    this.backoff = Math.min(Math.floor(this.backoff * 1.7), this.maxBackoff)
    setTimeout(() => this.connect({ role: this.role }), wait)
  }

  _startPing() {
    this._stopPing()
    this.pingTimer = setInterval(() => this.send({ type: 'ping' }), 25000)
  }

  _stopPing() {
    if (this.pingTimer) clearInterval(this.pingTimer)
    this.pingTimer = null
  }

  send(obj) {
    if (!this.enabled) return
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(obj))
        return true
      }
    } catch(e) {console.warn(e)}
    return false
  }

  sendLocation({ lat, lon, precision }) {
    return this.send({
      type: 'loc',
      alias: this.session.alias,
      lat,
      lon,
      precision,
      ts: Date.now()
    })
  }

  startGame() {
    this.send({ type: 'start' })
  }

  reset() {
    this.send({ type: 'reset' })
  }

  disconnect() {
    this._stopPing()
    try { this.ws?.close() } catch(e) {console.warn(e)}
    this.ws = null
  }
}
