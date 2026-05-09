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
    this.liveEnabledFlag = String(process.env.VUE_APP_LIVE_ENABLED || '').trim().toLowerCase() === 'true'
    this.game = (process.env.VUE_APP_GAME || 'demo').trim()

    // no petar: live queda desactivado salvo opt-in explicito
    this.enabled = !!this.baseUrl && this.liveEnabledFlag

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
    this.shouldReconnect = true
    this.failedReconnects = 0
    this.maxFailedReconnects = 5

    this.onMessage = () => {}
    this.onOpen = () => {}
    this.onClose = () => {}

    this.backoff = 400
    this.maxBackoff = 8000
    this.pingTimer = null
    this.availabilityChecked = false
    this.availabilityPromise = null

    const raw = localStorage.getItem('player_session_v1')
    this.session = raw ? JSON.parse(raw) : { playerId: uuidv4(), alias: null }
    localStorage.setItem('player_session_v1', JSON.stringify(this.session))

    if (!this.enabled) {
      if (this.baseUrl && !this.liveEnabledFlag) {
        console.warn('[LiveWS] Servicio live desactivado por configuración. Se usará HTTP.')
      } else {
        console.warn('[LiveWS] Falta VUE_APP_LIVE_URL. WS desactivado en este entorno.')
      }
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

  _httpBase() {
    if (!this.enabled) return ''
    let base = this.baseUrl.replace(/\/$/, '')
    try {
      const isHttpsPage = window.location.protocol === 'https:'
      const isHttpBase = base.startsWith('http://')
      const isLocalBase = /^(http:\/\/|https:\/\/)?(localhost|127\.0\.0\.1)/i.test(base)
      const isLocalPage = /^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname)
      if ((isHttpsPage && isHttpBase) || (isLocalBase && !isLocalPage)) {
        base = ''
      }
    } catch (e) {
      // ignore
    }
    return base
  }

  _httpUrl(path) {
    const base = this._httpBase()
    if (!base) return ''
    return `${base}${path}`
  }

  async ensureAvailable() {
    if (!this.enabled) return false
    if (this.availabilityChecked) return true
    if (this.availabilityPromise) return this.availabilityPromise

    const url = this._httpUrl('/estado-juego')
    if (!url) {
      this.enabled = false
      this.baseUrl = ''
      return false
    }

    this.availabilityPromise = (async () => {
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
      const timer = controller ? setTimeout(() => controller.abort(), 1200) : null

      try {
        const response = await fetch(url, {
          method: 'GET',
          cache: 'no-store',
          signal: controller?.signal
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        this.availabilityChecked = true
        return true
      } catch (e) {
        this.enabled = false
        this.baseUrl = ''
        this.shouldReconnect = false
        console.warn('[LiveWS] Servicio live no disponible. Se desactiva y la app sigue por HTTP.', e)
        return false
      } finally {
        if (timer) clearTimeout(timer)
        this.availabilityPromise = null
      }
    })()

    return this.availabilityPromise
  }

  async connect({ role = 'player', alias } = {}) {
    this.role = role
    if (alias) this.setAlias(alias)
    this.shouldReconnect = true

    if (!this.enabled) return // ✅ no rompe nada
    const available = await this.ensureAvailable()
    if (!available || !this.enabled || !this.shouldReconnect) return

    const url = this._wsUrl()
    if (!url) return

    if (this.ws) {
      try {
        this.ws.onopen = null
        this.ws.onmessage = null
        this.ws.onclose = null
        this.ws.onerror = null
        this.ws.close()
      } catch (e) {
        console.warn(e)
      }
    }

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.backoff = 400
      this.isOpen = true
      this.failedReconnects = 0
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
    if (!this.enabled || !this.shouldReconnect) return
    this.failedReconnects += 1
    if (this.failedReconnects >= this.maxFailedReconnects) {
      this.enabled = false
      this.baseUrl = ''
      console.warn('[LiveWS] No se pudo conectar al servicio live. Se desactiva y la app sigue por HTTP.')
      return
    }
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
    const sent = this.send({ type: 'reset' })
    if (!sent) {
      const url = this._httpUrl('/reset')
      if (!url) return
      fetch(url, { method: 'POST' }).catch(() => {})
    }
  }

  disconnect() {
    this.shouldReconnect = false
    this._stopPing()
    try {
      if (this.ws) {
        this.ws.onopen = null
        this.ws.onmessage = null
        this.ws.onclose = null
        this.ws.onerror = null
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.close()
        }
      }
    } catch(e) {console.warn(e)}
    this.isOpen = false
    this.ws = null
  }
}
