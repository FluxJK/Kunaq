/* =====================================================================
   KUNAQ CORE  ·  modo "offline-first" + red de emergencias
   ---------------------------------------------------------------------
   Idea central para trabajar con INTERNET DÉBIL:
     1. Todo se guarda primero en el propio equipo (funciona sin señal).
     2. Cada cambio entra a una COLA DE SALIDA con un ID único.
     3. Un motor intenta enviar la cola a la nube en lotes pequeños,
        con tiempo límite y reintentos cada vez más espaciados.
        Si el reintento llega repetido, la nube lo ignora (ID repetido).
     4. Solo se descargan los cambios NUEVOS (cursor), no todo cada vez.
     5. Las emergencias tienen prioridad: pasan al frente de la cola.
   Este archivo lo usan index.html y admin.html.  paciente.html NO lo usa.
   ===================================================================== */
(function (root) {
'use strict';

/* ---------- 0. Utilidades puras y Funciones de Orden Superior ---------- */
const LS = { DB: 'kunaq_db', COLA: 'kunaq_cola', CURSOR: 'kunaq_cursor', DISP: 'kunaq_dispositivo',
             CFG: 'kunaq_config', SIM: 'kunaq_nube_sim', NS: 'kunaq_ns' };
const ns = () => { try { return sessionStorage.getItem(LS.NS) || ''; } catch (e) { return ''; } };
// Claves con espacio propio cuando una pestaña actúa como "otro equipo" (modo demostración)
const clave = (k) => (ns() && [LS.DB, LS.COLA, LS.CURSOR].includes(k)) ? k + '@' + ns() : k;
const leer = (k, def) => { try { const v = localStorage.getItem(clave(k)); return v ? JSON.parse(v) : def; } catch (e) { return def; } };
const guardar = (k, v) => { try { localStorage.setItem(clave(k), JSON.stringify(v)); return true; } catch (e) { return false; } };
const uid = (pref = '') => pref + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const pipe = (...fns) => (x) => fns.reduce((acc, fn) => fn(acc), x);          // HOF: compone de izquierda a derecha
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const normalizar = (s) => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

/* SHA-256 en JavaScript puro (crypto.subtle no existe en http:// fuera de localhost).
   Mismo resultado que hashear_dni() de utils/seguridad.py → el DNI nunca viaja en claro. */
function sha256(texto) {
  const ascii = unescape(encodeURIComponent(texto));
  const rr = (v, a) => (v >>> a) | (v << (32 - a));
  const K = [], H = []; const comp = {}; let pc = 0;
  for (let c = 2; pc < 64; c++) if (!comp[c]) {
    for (let i = 0; i < 313; i += c) comp[i] = c;
    H[pc] = (Math.pow(c, 0.5) * 4294967296) | 0; K[pc++] = (Math.pow(c, 1 / 3) * 4294967296) | 0;
  }
  const w = []; const bits = ascii.length * 8; let s = ascii + '\x80';
  while (s.length % 64 - 56) s += '\x00';
  for (let i = 0; i < s.length; i++) w[i >> 2] |= s.charCodeAt(i) << ((3 - i) % 4) * 8;
  w[w.length] = (bits / 4294967296) | 0; w[w.length] = bits;
  let h = H.slice(0, 8);
  for (let j = 0; j < w.length;) {
    const x = w.slice(j, j += 16), old = h; h = h.slice(0, 8);
    for (let i = 0; i < 64; i++) {
      const w15 = x[i - 15], w2 = x[i - 2], a = h[0], e = h[4];
      const t1 = h[7] + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & h[5]) ^ (~e & h[6])) + K[i] +
        (x[i] = i < 16 ? x[i] : (x[i - 16] + (rr(w15, 7) ^ rr(w15, 18) ^ (w15 >>> 3)) + x[i - 7] + (rr(w2, 17) ^ rr(w2, 19) ^ (w2 >>> 10))) | 0);
      const t2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & h[1]) ^ (a & h[2]) ^ (h[1] & h[2]));
      h = [(t1 + t2) | 0].concat(h); h[4] = (h[4] + t1) | 0;
    }
    for (let i = 0; i < 8; i++) h[i] = (h[i] + old[i]) | 0;
  }
  let out = '';
  for (let i = 0; i < 8; i++) for (let j = 3; j + 1; j--) { const b = (h[i] >> (j * 8)) & 255; out += (b < 16 ? '0' : '') + b.toString(16); }
  return out;
}

/* ---------- 1. Datos base (los mismos de models/inventario_base.py) ---------- */
const INVENTARIO_BASE = [
    {id:1, nombre:"Paracetamol 500mg", categoria:"Analgésico", stock:50, minimo:20, unidad:"tabletas", ubicacion:"Estante A"},
    {id:2, nombre:"Amoxicilina 500mg", categoria:"Antibiótico", stock:0, minimo:20, unidad:"cápsulas", ubicacion:"Estante B"},
    {id:3, nombre:"Ibuprofeno 400mg", categoria:"Antiinflamatorio", stock:15, minimo:15, unidad:"tabletas", ubicacion:"Estante A"},
    {id:4, nombre:"Azitromicina 500mg", categoria:"Antibiótico", stock:24, minimo:12, unidad:"tabletas", ubicacion:"Estante B"},
    {id:5, nombre:"Ciprofloxacino 500mg", categoria:"Antibiótico", stock:18, minimo:12, unidad:"tabletas", ubicacion:"Estante B"},
    {id:6, nombre:"Metformina 850mg", categoria:"Antidiabético", stock:60, minimo:25, unidad:"tabletas", ubicacion:"Estante C"},
    {id:7, nombre:"Enalapril 10mg", categoria:"Antihipertensivo", stock:35, minimo:20, unidad:"tabletas", ubicacion:"Estante C"},
    {id:8, nombre:"Losartán 50mg", categoria:"Antihipertensivo", stock:8, minimo:20, unidad:"tabletas", ubicacion:"Estante C"},
    {id:9, nombre:"Omeprazol 20mg", categoria:"Gastrointestinal", stock:40, minimo:20, unidad:"cápsulas", ubicacion:"Estante D"},
    {id:10, nombre:"Salbutamol 100mcg", categoria:"Respiratorio", stock:12, minimo:10, unidad:"inhaladores", ubicacion:"Estante D"},
    {id:11, nombre:"Loratadina 10mg", categoria:"Antihistamínico", stock:30, minimo:15, unidad:"tabletas", ubicacion:"Estante A"},
    {id:12, nombre:"Sulfato ferroso 300mg", categoria:"Suplemento", stock:70, minimo:30, unidad:"tabletas", ubicacion:"Estante D"},
    {id:13, nombre:"Ácido fólico 5mg", categoria:"Suplemento", stock:45, minimo:20, unidad:"tabletas", ubicacion:"Estante D"},
    {id:14, nombre:"Sales de rehidratación oral", categoria:"Hidratación", stock:80, minimo:30, unidad:"sobres", ubicacion:"Estante E"},
    {id:15, nombre:"Cloruro de sodio 0.9% 1000ml", categoria:"Hidratación", stock:25, minimo:15, unidad:"frascos", ubicacion:"Estante E"},
    {id:16, nombre:"Adrenalina 1mg/ml", categoria:"Emergencia", stock:6, minimo:5, unidad:"ampollas", ubicacion:"Vitrina de emergencia"},
    {id:17, nombre:"Oxitocina 10UI", categoria:"Emergencia", stock:4, minimo:5, unidad:"ampollas", ubicacion:"Refrigerador"},
    {id:18, nombre:"Dexametasona 4mg/ml", categoria:"Emergencia", stock:14, minimo:8, unidad:"ampollas", ubicacion:"Vitrina de emergencia"},
    {id:19, nombre:"Diclofenaco 75mg/3ml", categoria:"Analgésico", stock:20, minimo:10, unidad:"ampollas", ubicacion:"Estante A"},
    {id:20, nombre:"Albendazol 400mg", categoria:"Antiparasitario", stock:40, minimo:15, unidad:"tabletas", ubicacion:"Estante D"}
];

const CAPACIDADES = {
  UCI: 'UCI', VENTILADOR: 'Ventilador mecánico', QUIROFANO: 'Quirófano',
  OBSTETRICIA: 'Sala de partos / Gineco-obstetricia', NEONATOLOGIA: 'Neonatología',
  BANCO_SANGRE: 'Banco de sangre', TOMOGRAFO: 'Tomógrafo', TRAUMA: 'Trauma shock'
};
const TIPOS = { POSTA: 'Posta de salud', CENTRO_SALUD: 'Centro de salud', HOSPITAL: 'Hospital' };
const CATEGORIAS_MINSA = ['I-1', 'I-2', 'I-3', 'I-4', 'II-1', 'II-2', 'III-1', 'III-2'];
const PLANTILLAS = [   // casos típicos para llenar el formulario con un clic
  { nombre: 'Shock anafiláctico', cuadro: 'Shock anafiláctico, hipotensión severa, requiere soporte vital', prioridad: 1, requisitos: ['UCI', 'VENTILADOR'] },
  { nombre: 'Gestante con hemorragia', cuadro: 'Gestante con hemorragia severa, sospecha de atonía/placenta previa', prioridad: 1, requisitos: ['OBSTETRICIA', 'BANCO_SANGRE', 'QUIROFANO'] },
  { nombre: 'Politraumatismo', cuadro: 'Politraumatismo por accidente de tránsito, inestable', prioridad: 1, requisitos: ['TRAUMA', 'QUIROFANO', 'TOMOGRAFO', 'BANCO_SANGRE'] }
];

/* ---------- 2. Seguridad (simulada, igual que en el proyecto original) ---------- */
class SeguridadKunaq {
  cifrar(texto) { return btoa(encodeURIComponent(texto)); }                    // simula AES-256
  descifrar(c) { try { return decodeURIComponent(atob(c)); } catch (e) { return '[dato no legible]'; } }
}

/* ---------- 3. Controlador de emergencias · FUNCIONES DE ORDEN SUPERIOR ----------
   Mismo algoritmo que ControladorEmergencias en models/entidades.py.
   Funciona SIN internet: usa la última lista de dispositivos guardada.        */
class ControladorEmergencias {
  // Fábricas de predicados: funciones que DEVUELVEN funciones
  static esReceptor(d) { return d.tipo === 'HOSPITAL'; }
  static senal(d) {                       // en_linea | debil | sin_senal, según su último latido
    const edad = (d.visto_hace || 0) + (d._t ? (Date.now() - d._t) / 1000 : 0);
    return edad <= 45 ? 'en_linea' : edad <= 180 ? 'debil' : 'sin_senal';
  }
  static estaVivo(d) { return ControladorEmergencias.senal(d) !== 'sin_senal'; }
  static noExcluido(ids) { return (d) => !ids.includes(d.id); }
  static cumpleTodo(reqs) { return (d) => reqs.every((r) => (d.capacidades || []).includes(r)); }

  static distanciaKm(a, b) {
    if ([a.lat, a.lng, b.lat, b.lng].some((v) => v == null)) return null;
    const rad = (g) => g * Math.PI / 180, dphi = rad(b.lat - a.lat), dlam = rad(b.lng - a.lng);
    const h = Math.sin(dphi / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dlam / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }
  static nivel(d) { return { I: 1, II: 2, III: 3 }[String(d.categoria || 'I-1').split('-')[0]] || 1; }

  // Devuelve una función de puntuación ya configurada con los requisitos
  static puntuar(reqs, origen) {
    return (d) => {
      const caps = d.capacidades || [];
      const faltantes = reqs.filter((r) => !caps.includes(r));
      const cobertura = reqs.length ? (reqs.length - faltantes.length) / reqs.length : 1;
      const dist = origen ? ControladorEmergencias.distanciaKm(origen, d) : null;
      const puntaje = 100 * cobertura + 12 * ControladorEmergencias.nivel(d)
        + (reqs.includes('UCI') ? 3 * Math.min(d.camas_uci || 0, 5) : 0)
        - (dist != null ? 0.5 * Math.min(dist, 100) : 0)
        - (ControladorEmergencias.senal(d) === 'debil' ? 40 : 0);
      return { dispositivo: d, puntaje: Math.round(puntaje * 10) / 10, cobertura, cumpleTodo: !faltantes.length,
               faltantes, distanciaKm: dist == null ? null : Math.round(dist * 10) / 10 };
    };
  }
  // Pipeline: filter → filter → filter → map → sort
  static ranking(dispositivos, reqs, origen, excluir = []) {
    const C = ControladorEmergencias;
    const receptores = dispositivos.filter(C.esReceptor).filter(C.noExcluido(excluir));
    const vivos = receptores.filter(C.estaVivo);
    return (vivos.length ? vivos : receptores).map(C.puntuar(reqs, origen)).sort((a, b) => b.puntaje - a.puntaje);
  }
  // reduce: se queda con el mejor puntaje
  static mejor(ranking) { return ranking.reduce((a, b) => (b.puntaje > a.puntaje ? b : a), ranking[0] || null); }
  // reduce: cuántas emergencias hay por prioridad
  static contarPorPrioridad(lista) { return lista.reduce((acc, e) => ({ ...acc, [e.prioridad]: (acc[e.prioridad] || 0) + 1 }), {}); }
}

/* ---------- 4. Filtros de inventario (HOF) ---------- */
const Filtros = {
  disponible: (m) => m.stock > 0,
  agotado: (m) => m.stock === 0,
  bajo: (m) => m.stock > 0 && m.stock <= m.minimo,
  texto: (q) => (m) => !q || normalizar(m.nombre + ' ' + m.categoria).includes(normalizar(q)),
  categoria: (c) => (m) => !c || m.categoria === c,
  todos: (...ps) => (x) => ps.every((p) => p(x))                       // combina predicados
};
const estadoStock = (m) => (m.stock === 0 ? 'agotado' : m.stock <= m.minimo ? 'bajo' : 'ok');
const resumenStock = (lista) => lista.reduce((r, m) => { r.total++; r[estadoStock(m)]++; return r; }, { total: 0, ok: 0, bajo: 0, agotado: 0 });

/* ---------- 5. "Nube" simulada: mismo contrato que servidor_nube.py ----------
   Sirve para demostrar todo en UNA PC (dos pestañas) sin instalar el servidor.   */
class NucleoNube {
  static vacio() {
    return { seq: 0, ops: {}, dispositivos: {}, inventario: INVENTARIO_BASE.reduce((o, m) => (o[m.id] = { ...m, seq: 0 }, o), {}),
             alertas: {}, atenciones: [] };
  }
  static push(e, disp, ops) {
    const aceptadas = [], rechazadas = [];
    ops.slice(0, 50).forEach((op) => {
      try {
        if (e.ops[op.id]) { aceptadas.push(op.id); return; }
        const d = op.datos || {};
        switch (op.tipo) {
          case 'DISPOSITIVO': e.dispositivos[d.id] = { ...(e.dispositivos[d.id] || {}), ...d, visto: Date.now(), activo: true }; break;
          case 'DISPOSITIVO_BAJA': if (e.dispositivos[d.id]) e.dispositivos[d.id].activo = false; break;
          case 'MED_UPSERT': e.inventario[d.id] = { ...d, stock: Math.max(0, d.stock | 0), seq: ++e.seq }; break;
          case 'STOCK_DELTA': { const m = e.inventario[d.id]; if (m) { m.stock = Math.max(0, m.stock + (d.delta | 0)); m.seq = ++e.seq; } break; }
          case 'ATENCION': if (!e.atenciones.some((a) => a.id === d.id)) e.atenciones.push({ ...d, origen: disp, creada: Date.now() }); break;
          case 'PACIENTE': break;      // el acceso del paciente solo existe en la nube real (servidor_nube.py)
          case 'EMERGENCIA': NucleoNube._emergencia(e, disp, d); break;
          case 'ALERTA_ESTADO': NucleoNube._estado(e, d); break;
          default: throw new Error('tipo de operación desconocido');
        }
        e.ops[op.id] = 1; aceptadas.push(op.id);
      } catch (err) { rechazadas.push({ id: op.id, error: err.message }); }
    });
    return { aceptadas, rechazadas, cursor: e.seq };
  }
  static listaDispositivos(e) {
    const t = Date.now();
    return Object.values(e.dispositivos).filter((d) => d.activo)
      .map((d) => ({ id: d.id, nombre: d.nombre, tipo: d.tipo, categoria: d.categoria, capacidades: d.capacidades || [],
                     camas_uci: d.camas_uci || 0, lat: d.lat == null ? null : d.lat, lng: d.lng == null ? null : d.lng,
                     visto_hace: Math.max(0, Math.round((t - d.visto) / 1000)) }));
  }
  static _elegir(e, reqs, origenId, excluir) {
    const lista = NucleoNube.listaDispositivos(e);
    const origen = lista.find((d) => d.id === origenId) || null;
    return ControladorEmergencias.mejor(ControladorEmergencias.ranking(lista, reqs, origen, [...excluir, origenId]));
  }
  static _emergencia(e, disp, a) {
    if (e.alertas[a.id]) return;
    const lista = NucleoNube.listaDispositivos(e);
    let dest = a.destino_id && lista.find((d) => d.id === a.destino_id);
    if (!dest) { const m = NucleoNube._elegir(e, a.requisitos || [], a.origen_id || disp, []); dest = m && m.dispositivo; }
    const t = Date.now();
    e.alertas[a.id] = { id: a.id, origen_id: a.origen_id || disp, origen_nombre: a.origen_nombre || '', destino_id: dest ? dest.id : null,
      destino_nombre: dest ? dest.nombre : null, prioridad: a.prioridad || 2, requisitos: a.requisitos || [],
      datos_cifrados: a.datos_cifrados || '', estado: dest ? 'ENVIADA' : 'SIN_DESTINO', rechazados: [],
      bitacora: [{ t: a.creada || t, texto: 'Registrada en ' + (a.origen_nombre || disp) },
                 { t, texto: dest ? 'Enviada a ' + dest.nombre : 'No hay hospitales vinculados para recibirla' }],
      creada: a.creada || t, actualizada: t, seq: ++e.seq };
  }
  static _estado(e, d) {
    const a = e.alertas[d.id]; if (!a) throw new Error('alerta inexistente');
    const t = Date.now();
    if (d.estado === 'CONFIRMADA') { a.estado = 'CONFIRMADA'; a.bitacora.push({ t, texto: a.destino_nombre + ' confirmó: preparando equipo' }); }
    else if (d.estado === 'RECHAZADA') {
      a.bitacora.push({ t, texto: a.destino_nombre + ' no puede recibir (' + ((d.motivo || 'sin motivo').slice(0, 120)) + ')' });
      a.rechazados = [...a.rechazados, a.destino_id];
      const n = NucleoNube._elegir(e, a.requisitos, a.origen_id, a.rechazados);
      if (n) { a.destino_id = n.dispositivo.id; a.destino_nombre = n.dispositivo.nombre; a.estado = 'ENVIADA'; a.bitacora.push({ t, texto: 'Reasignada a ' + a.destino_nombre }); }
      else { a.estado = 'SIN_DESTINO'; a.bitacora.push({ t, texto: 'Ningún otro hospital disponible' }); }
    } else throw new Error('estado inválido');
    a.actualizada = t; a.seq = ++e.seq;
  }
  static pull(e, disp, cursor) {
    if (disp && e.dispositivos[disp]) e.dispositivos[disp].visto = Date.now();
    const inventario = Object.values(e.inventario).filter((m) => m.seq > cursor);
    const alertas = Object.values(e.alertas).filter((a) => a.seq > cursor && (a.destino_id === disp || a.origen_id === disp));
    alertas.forEach((a) => {
      if (a.destino_id === disp && a.estado === 'ENVIADA') {
        a.estado = 'ENTREGADA'; a.bitacora.push({ t: Date.now(), texto: 'Entregada al equipo de ' + a.destino_nombre });
        a.actualizada = Date.now(); a.seq = ++e.seq;
      }
    });
    return { cursor: e.seq, ahora: Date.now(), dispositivos: NucleoNube.listaDispositivos(e), inventario, alertas };
  }
}

/* Adaptadores: ambos ofrecen ping / push / pull / atenciones */
class NubeSimulada {
  constructor() { this.nombre = 'simulada'; }
  _leer() { try { return JSON.parse(localStorage.getItem(LS.SIM)) || NucleoNube.vacio(); } catch (e) { return NucleoNube.vacio(); } }
  _usar(fn) { const e = this._leer(); const r = fn(e); localStorage.setItem(LS.SIM, JSON.stringify(e)); return r; }
  async ping() { await dormir(30); return { ms: 30 }; }
  async push(disp, ops) { await dormir(40); return this._usar((e) => NucleoNube.push(e, disp, ops)); }
  async pull(disp, cursor) { await dormir(40); return this._usar((e) => NucleoNube.pull(e, disp, cursor)); }
  async atenciones(hash) { await dormir(40); return { atenciones: this._leer().atenciones.filter((a) => a.dni_hash === hash) }; }
}

class NubeHTTP {
  constructor(cfg) { this.nombre = 'http'; this.url = String(cfg.url || '').replace(/\/$/, ''); this.token = cfg.token || ''; }
  async _fetch(ruta, opts = {}, ms = 8000) {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), ms);   // tiempo límite: no se queda colgado
    const headers = this.token ? { 'X-Kunaq-Token': this.token } : {};
    try {
      const r = await fetch(this.url + ruta, { ...opts, headers, signal: ctl.signal, cache: 'no-store' });
      if (!r.ok) throw new Error(r.status === 401 ? 'Sesión vencida o no iniciada: inicie sesión de nuevo en la portada' : 'HTTP ' + r.status);
      return await r.json();
    } finally { clearTimeout(t); }
  }
  async ping() { const t0 = performance.now(); const r = await this._fetch('/api/ping', {}, 4000); return { ms: performance.now() - t0, ...r }; }
  // POST como text/plain: evita la consulta previa (preflight) y ahorra un viaje con señal débil
  push(disp, ops) { return this._fetch('/api/sync/push', { method: 'POST', body: JSON.stringify({ dispositivo: disp, ops }) }); }
  pull(disp, cursor) { return this._fetch('/api/sync/pull?dispositivo=' + encodeURIComponent(disp || '') + '&cursor=' + cursor); }
  atenciones(hash) { return this._fetch('/api/atenciones?dni_hash=' + encodeURIComponent(hash)); }
}


/* ---------- 6. Base local (lo que ya existía, ampliado) ---------- */
class BaseLocal {
  static semilla() {
    return {
      version: 2,
      pacientes: [{ dni: '70123456', pin: '1234', nombre: 'Juan Perez', historial: [
        { fecha: '07/10/2026', hospital: 'Posta Laredo', datos_cifrados: btoa(encodeURIComponent('Diagnóstico: Gripe | Receta: Paracetamol')) } ] }],
      inventario: INVENTARIO_BASE.map((m) => ({ ...m })),
      dispositivos: [], alertas: []
    };
  }
  // Crea la BD si no existe y completa lo que falte (migra instalaciones anteriores sin perder datos)
  static asegurar() {
    let db = leer(LS.DB, null);
    if (!db) db = BaseLocal.semilla();
    db.pacientes = db.pacientes || []; db.dispositivos = db.dispositivos || []; db.alertas = db.alertas || [];
    db.inventario = db.inventario || [];
    INVENTARIO_BASE.forEach((base) => {
      const i = db.inventario.findIndex((m) => m.id === base.id);
      if (i < 0) db.inventario.push({ ...base });
      else db.inventario[i] = { ...base, ...db.inventario[i], nombre: db.inventario[i].categoria ? db.inventario[i].nombre : base.nombre };
    });
    db.version = 2; guardar(LS.DB, db); return db;
  }
}

/* ---------- 7. Piezas del motor de sincronización ---------- */
class Emisor {
  constructor() { this._m = {}; }
  on(e, f) { (this._m[e] = this._m[e] || []).push(f); }
  emit(e, d) { (this._m[e] || []).forEach((f) => { try { f(d); } catch (x) { console.error(x); } }); }
}

class MonitorConexion {
  constructor() { this.nivel = 'conectando'; this.ms = null; this.ultimaOk = null; this.fallos = 0; this.error = ''; }
  exito(ms, simulada) { this.ms = ms; this.ultimaOk = Date.now(); this.fallos = 0; this.error = ''; this.nivel = simulada ? 'simulada' : ms > 1500 ? 'debil' : 'buena'; }
  fallo(msg, forzado) { this.fallos++; this.error = msg || ''; this.nivel = (forzado || this.fallos >= 2) ? 'sin_conexion' : 'debil'; }
}

const Config = {
  leer() {
    const c = leer(LS.CFG, {}); const http = /^https?:/.test(location.protocol);
    let off = false; try { off = sessionStorage.getItem('kunaq_offline') === '1'; } catch (e) { /* nada */ }
    return { modo: c.modo || (http ? 'http' : 'simulada'), url: c.url || (http ? location.origin : 'http://localhost:8765'),
             token: c.token || '', sonido: c.sonido !== false, forzarOffline: off };
  },
  guardar(c) { try { localStorage.setItem(LS.CFG, JSON.stringify({ modo: c.modo, url: c.url, token: c.token, sonido: c.sonido })); } catch (e) { /* nada */ } }
};

/* Sesión del personal (cuenta + contraseña verificadas por el servidor). El token se guarda en el equipo para poder
   seguir trabajando sin internet hasta que venza; las operaciones pendientes se envían al reconectar. */
const Sesion = {
  K: 'kunaq_sesion',
  leer() { try { const s = JSON.parse(localStorage.getItem(Sesion.K) || 'null'); return s && s.expira > Date.now() ? s : null; } catch (e) { return null; } },
  async _post(url, ruta, cuerpo, token) {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 10000);
    try {
      const r = await fetch(String(url).replace(/\/$/, '') + ruta, { method: 'POST', headers: token ? { 'X-Kunaq-Token': token } : {},
                                                                   body: JSON.stringify(cuerpo || {}), signal: ctl.signal, cache: 'no-store' });
      return await r.json();
    } finally { clearTimeout(t); }
  },
  // true = el servidor exige cuentas · false = abierto (pruebas) · null = no se pudo consultar (sin señal)
  async requiere(url) {
    try { const r = await fetch(String(url).replace(/\/$/, '') + '/api/ping', { cache: 'no-store' }); return !!(await r.json()).requiere_login; }
    catch (e) { return null; }
  },
  async entrar(url, usuario, clave) {
    const r = await Sesion._post(url, '/api/personal/login', { usuario, clave });
    if (r.ok) { try { localStorage.setItem(Sesion.K, JSON.stringify({ usuario: r.usuario, nombre: r.nombre, rol: r.rol, token: r.token, expira: r.expira })); } catch (e) { /* nada */ } }
    return r;
  },
  async salir(url) {
    const s = Sesion.leer();
    try { if (s) await Sesion._post(url, '/api/personal/logout', {}, s.token); } catch (e) { /* sin señal: igual se cierra aquí */ }
    try { localStorage.removeItem(Sesion.K); sessionStorage.removeItem('kunaq_staff'); } catch (e) { /* nada */ }
  },
  // Llamada autenticada a la API (para administrar cuentas)
  async api(url, ruta, cuerpo) {
    const s = Sesion.leer(); if (!s) throw new Error('sin sesión');
    const r = await fetch(String(url).replace(/\/$/, '') + ruta, { method: cuerpo ? 'POST' : 'GET', headers: { 'X-Kunaq-Token': s.token },
                                                                body: cuerpo ? JSON.stringify(cuerpo) : undefined, cache: 'no-store' });
    return r.json();
  }
};

const Identidad = {
  leer() { try { return JSON.parse(sessionStorage.getItem(LS.DISP) || localStorage.getItem(LS.DISP) || 'null'); } catch (e) { return null; } },
  guardar(d, soloPestana) {
    try {
      if (soloPestana) { sessionStorage.setItem(LS.DISP, JSON.stringify(d)); sessionStorage.setItem(LS.NS, d.id); }
      else localStorage.setItem(LS.DISP, JSON.stringify(d));
    } catch (e) { /* nada */ }
  },
  borrar() { try { sessionStorage.removeItem(LS.DISP); sessionStorage.removeItem(LS.NS); localStorage.removeItem(LS.DISP); } catch (e) { /* nada */ } }
};

/* ---------- 8. Aplicación: base local + cola + motor + controlador ---------- */
class KunaqApp {
  constructor() {
    this.seg = new SeguridadKunaq(); this.ev = new Emisor(); this.monitor = new MonitorConexion();
    this._raw = null; this._cache = null; this.alertadas = new Set(); this.config = Config.leer();
    this.fallos = 0; this.timer = null; this.enCurso = false; this.nube = this._crearNube();
    this.inventario = new Inventario(this); this.emergencias = new Emergencias(this);
  }
  _crearNube() { return this.config.modo === 'http' ? new NubeHTTP(this.config) : new NubeSimulada(); }
  cambiarConfig(nueva) {
    this.config = { ...this.config, ...nueva }; Config.guardar(this.config); this.nube = this._crearNube();
    guardar(LS.CURSOR, 0); this.mutar((db) => { db.dispositivos = []; }); this.despertar(); this.ev.emit('estado', this.estado());
  }
  setForzarOffline(v) {
    try { sessionStorage.setItem('kunaq_offline', v ? '1' : '0'); } catch (e) { /* nada */ }
    this.config.forzarOffline = !!v; if (v) this.monitor.fallo('Sin internet (simulado)', true); this.despertar(); this.ev.emit('estado', this.estado());
  }

  // ----- base local (se relee si otra pestaña la modificó) -----
  get db() {
    const raw = localStorage.getItem(clave(LS.DB));
    if (raw !== this._raw || !this._cache) { this._raw = raw; this._cache = raw ? JSON.parse(raw) : BaseLocal.asegurar(); }
    return this._cache;
  }
  mutar(fn) {
    const antes = JSON.stringify(this.db), db = JSON.parse(antes); fn(db);
    if (JSON.stringify(db) !== antes) { guardar(LS.DB, db); this._raw = null; }   // no escribe si nada cambió
    return db;
  }

  // ----- cola de salida -----
  colaItems() { return leer(LS.COLA, []); }
  _guardarCola(c) { guardar(LS.COLA, c); }
  encolar(tipo, datos, prioridad = 5) {
    const c = this.colaItems(); const op = { id: uid('op-'), tipo, datos, prioridad, ts: Date.now() };
    c.push(op); this._guardarCola(c); this.ev.emit('estado', this.estado()); return op;
  }
  get identidad() { return Identidad.leer(); }

  // ----- vincular equipo (registro de la PC) -----
  vincular(datos, soloPestana) {
    const d = { id: uid('D-'), nombre: datos.nombre, tipo: datos.tipo, categoria: datos.categoria,
                capacidades: datos.capacidades || [], camas_uci: datos.camas_uci | 0,
                lat: datos.lat == null ? null : datos.lat, lng: datos.lng == null ? null : datos.lng };
    Identidad.guardar(d, soloPestana); this._raw = null; BaseLocal.asegurar();
    this.encolar('DISPOSITIVO', d, 1); this.despertar(); this.ev.emit('identidad', d); return d;
  }
  actualizarEquipo(cambios) {
    const d = { ...this.identidad, ...cambios }; Identidad.guardar(d, !!ns());
    this.encolar('DISPOSITIVO', d, 1); this.despertar(); this.ev.emit('identidad', d); return d;
  }
  desvincular() {
    const d = this.identidad; if (!d) return;
    this.encolar('DISPOSITIVO_BAJA', { id: d.id }, 1); Identidad.borrar(); this._raw = null; this.despertar(); this.ev.emit('identidad', null);
  }

  // ----- estado para la interfaz -----
  estado() {
    const m = this.monitor;
    return { nivel: this.config.forzarOffline ? 'sin_conexion' : m.nivel, ms: m.ms, ultimaOk: m.ultimaOk, error: m.error,
             pendientes: this.colaItems().length, modo: this.config.modo, forzado: this.config.forzarOffline };
  }

  // ----- motor de sincronización -----
  iniciar() {
    window.addEventListener('online', () => this.despertar());
    window.addEventListener('offline', () => { this.monitor.fallo('Sin red', true); this.ev.emit('estado', this.estado()); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) this.despertar(); });
    window.addEventListener('storage', (e) => { if (e.key && e.key.indexOf('kunaq_') === 0) this.ev.emit('datos', e.key); });
    this._programar(250);
    // alertas que quedaron sin responder (por ejemplo, tras recargar la página) vuelven a sonar
    const yo = this.identidad;
    if (yo) this.db.alertas.filter((a) => a.destino_id === yo.id && ['ENVIADA', 'ENTREGADA'].includes(a.estado))
      .forEach((a) => { this.alertadas.add(a.id); this.ev.emit('alerta-entrante', a); });
  }
  despertar() { clearTimeout(this.timer); this._programar(0); }
  _programar(ms) { this.timer = setTimeout(() => this._ciclo(), ms); }
  _intervalo() {
    const base = { buena: 4000, simulada: 3000, debil: 8000 }[this.monitor.nivel];
    const t = base || Math.min(60000, 3000 * Math.pow(2, Math.min(this.fallos, 5))) * (0.8 + Math.random() * 0.4);  // reintento cada vez más espaciado
    return document.hidden ? t * 4 : t;
  }
  async _ciclo() {
    if (this.enCurso) return; this.enCurso = true;
    try {
      if (this.config.forzarOffline) throw Object.assign(new Error('Sin internet (simulado)'), { forzado: true });
      if (navigator.onLine === false) throw Object.assign(new Error('Sin red'), { forzado: true });
      const t0 = performance.now();
      await this._empujar();      // 1) primero lo que yo tengo pendiente
      await this._traer();        // 2) luego solo lo nuevo de la nube
      this.monitor.exito(performance.now() - t0, this.nube.nombre === 'simulada'); this.fallos = 0;
    } catch (e) {
      this.fallos++; this.monitor.fallo(e.name === 'AbortError' ? 'Tiempo agotado (señal muy débil)' : e.message, e.forzado);
    } finally {
      this.enCurso = false; this.ev.emit('estado', this.estado()); this._programar(this._intervalo());
    }
  }
  async _empujar() {
    const yo = this.identidad; const idDisp = yo ? yo.id : '';
    for (let vuelta = 0; vuelta < 10; vuelta++) {
      const lote = this.colaItems().sort((a, b) => a.prioridad - b.prioridad || a.ts - b.ts).slice(0, 15);   // emergencias primero
      if (!lote.length) return;
      const r = await this.nube.push(idDisp, lote.map(({ id, tipo, datos }) => ({ id, tipo, datos })));
      const hechas = new Set([...r.aceptadas, ...(r.rechazadas || []).map((x) => x.id)]);
      this._guardarCola(this.colaItems().filter((o) => !hechas.has(o.id)));
      const enviadas = new Set(lote.filter((o) => o.tipo === 'EMERGENCIA' && r.aceptadas.includes(o.id)).map((o) => o.datos.id));
      if (enviadas.size) this.mutar((db) => db.alertas.forEach((a) => { if (enviadas.has(a.id) && a.estado === 'PENDIENTE_ENVIO') a.estado = 'ENVIADA'; }));
      if (r.rechazadas && r.rechazadas.length) this.ev.emit('error-sync', r.rechazadas);
      this.ev.emit('estado', this.estado());
    }
  }
  async _traer(reintento) {
    const yo = this.identidad; const cursor = leer(LS.CURSOR, 0);
    const r = await this.nube.pull(yo ? yo.id : '', cursor);
    if (r.cursor < cursor && !reintento) { guardar(LS.CURSOR, 0); return this._traer(true); }   // la nube se reinició
    this._aplicarPull(r, yo); guardar(LS.CURSOR, r.cursor);
  }
  _aplicarPull(r, yo) {
    const cola = this.colaItems();
    const pendStock = cola.filter((o) => o.tipo === 'STOCK_DELTA').reduce((m, o) => (m[o.datos.id] = (m[o.datos.id] || 0) + o.datos.delta, m), {});
    const pendEstado = new Set(cola.filter((o) => o.tipo === 'ALERTA_ESTADO').map((o) => o.datos.id));
    const pendEnvio = new Set(cola.filter((o) => o.tipo === 'EMERGENCIA').map((o) => o.datos.id));
    const entrantes = []; let hayInv = false;
    this.mutar((db) => {
      const t = Date.now(); db.dispositivos = r.dispositivos.map((d) => ({ ...d, _t: t }));
      r.inventario.forEach((row) => {            // stock de la nube + lo que yo aún no he enviado
        hayInv = true;
        const m = { id: row.id, nombre: row.nombre, categoria: row.categoria, minimo: row.minimo, unidad: row.unidad,
                    ubicacion: row.ubicacion, stock: Math.max(0, row.stock + (pendStock[row.id] || 0)) };
        const i = db.inventario.findIndex((x) => x.id === row.id); if (i >= 0) db.inventario[i] = m; else db.inventario.push(m);
      });
      r.alertas.forEach((a) => {
        if (pendEnvio.has(a.id)) return;
        const i = db.alertas.findIndex((x) => x.id === a.id);
        if (i >= 0 && pendEstado.has(a.id)) a = { ...a, estado: db.alertas[i].estado };   // mi respuesta aún no salió: manda lo local
        if (i >= 0) db.alertas[i] = a; else db.alertas.unshift(a);
        if (yo && a.destino_id === yo.id && ['ENVIADA', 'ENTREGADA'].includes(a.estado) && !this.alertadas.has(a.id)) entrantes.push(a);
      });
      db.alertas.sort((x, y) => y.creada - x.creada); db.alertas = db.alertas.slice(0, 50);
    });
    this.ev.emit('dispositivos', this.db.dispositivos); this.ev.emit('alertas', this.db.alertas);
    if (hayInv) this.ev.emit('inventario', this.db.inventario);
    entrantes.forEach((a) => { this.alertadas.add(a.id); this.ev.emit('alerta-entrante', a); });
  }

  // ----- historial clínico hacia la nube (el DNI viaja como hash) -----
  atencionANube(dni, nombre, hospital, fecha, datosCifrados) {
    this.encolar('ATENCION', { id: uid('A-'), dni_hash: sha256(dni), nombre, fecha, hospital, datos_cifrados: datosCifrados }, 5);
    this.despertar();
  }
  // Acceso del paciente al portal (DNI + PIN). El PIN viaja una sola vez; la nube lo guarda solo como hash.
  pacienteANube(dni, nombre, pin, reset) {
    this.encolar('PACIENTE', { dni_hash: sha256(dni), nombre, pin, reset: !!reset }, 5);
    this.despertar();
  }
  async buscarEnNube(dni) {
    const r = await this.nube.atenciones(sha256(dni)); return r.atenciones || [];
  }
}

/* ---------- 9. Inventario (stock con cambios sincronizables) ---------- */
class Inventario {
  constructor(app) { this.app = app; }
  lista() { return this.app.db.inventario; }
  categorias() { return [...new Set(this.lista().map((m) => m.categoria))].sort(); }
  ajustar(id, delta) {
    this.app.mutar((db) => { const m = db.inventario.find((x) => x.id === id); if (m) m.stock = Math.max(0, m.stock + delta); });
    this.app.encolar('STOCK_DELTA', { id, delta }, 4); this.app.despertar();
  }
  agregar(m) {
    const id = Math.max(100, ...this.lista().map((x) => x.id)) + 1;
    const nuevo = { id, nombre: m.nombre, categoria: m.categoria || 'General', stock: Math.max(0, m.stock | 0), minimo: Math.max(0, m.minimo | 0),
                    unidad: m.unidad || 'unid.', ubicacion: m.ubicacion || '-' };
    this.app.mutar((db) => db.inventario.push(nuevo)); this.app.encolar('MED_UPSERT', nuevo, 4); this.app.despertar(); return nuevo;
  }
}

/* ---------- 10. Emergencias: crear, responder, consultar ---------- */
class Emergencias {
  constructor(app) { this.app = app; }
  ranking(reqs) {
    const yo = this.app.identidad;
    return ControladorEmergencias.ranking(this.app.db.dispositivos, reqs, yo, yo ? [yo.id] : []);
  }
  enviar({ paciente, dni, edad, cuadro, prioridad, requisitos, destino }) {
    const yo = this.app.identidad; if (!yo) throw new Error('Vincule este equipo en la página de inicio antes de enviar una emergencia.');
    const rk = this.ranking(requisitos);
    const elegido = destino ? rk.find((x) => x.dispositivo.id === destino) : ControladorEmergencias.mejor(rk);
    const t = Date.now();
    const alerta = { id: uid('E-'), origen_id: yo.id, origen_nombre: yo.nombre, destino_id: elegido ? elegido.dispositivo.id : null,
      destino_nombre: elegido ? elegido.dispositivo.nombre : null, prioridad, requisitos,
      datos_cifrados: this.app.seg.cifrar(JSON.stringify({ paciente: paciente || '', dni: dni || '', edad: edad || '', cuadro })),
      estado: 'PENDIENTE_ENVIO', rechazados: [], bitacora: [{ t, texto: 'Registrada en este equipo' }], creada: t, actualizada: t };
    this.app.mutar((db) => db.alertas.unshift(alerta));
    this.app.encolar('EMERGENCIA', alerta, 0);          // prioridad 0 = sale antes que todo
    this.app.despertar(); this.app.ev.emit('alertas', this.app.db.alertas); return alerta;
  }
  responder(id, estado, motivo) {
    const nombre = (this.app.identidad || {}).nombre || 'Hospital';
    this.app.mutar((db) => { const a = db.alertas.find((x) => x.id === id); if (!a) return;
      a.estado = estado; a.bitacora = (a.bitacora || []).concat({ t: Date.now(), texto: estado === 'CONFIRMADA' ? nombre + ' confirmó: preparando equipo' : nombre + ' no puede recibir (' + (motivo || 'sin motivo') + ')' }); });
    this.app.encolar('ALERTA_ESTADO', { id, estado, motivo: motivo || '' }, 0); this.app.despertar();
    this.app.ev.emit('alertas', this.app.db.alertas);
  }
  detalle(a) { try { return JSON.parse(this.app.seg.descifrar(a.datos_cifrados)); } catch (e) { return {}; } }
  enviadas() { const yo = this.app.identidad; return yo ? this.app.db.alertas.filter((a) => a.origen_id === yo.id) : []; }
  recibidas() { const yo = this.app.identidad; return yo ? this.app.db.alertas.filter((a) => a.destino_id === yo.id || (a.rechazados || []).includes(yo.id)) : []; }
}

/* ---------- 11. Interfaz compartida: avisos, estado de conexión, alerta a pantalla completa ---------- */
const tiempoRelativo = (ms) => { const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return s < 5 ? 'ahora' : s < 60 ? 'hace ' + s + ' s' : s < 3600 ? 'hace ' + Math.round(s / 60) + ' min' : 'hace ' + Math.round(s / 3600) + ' h'; };
const PRIORIDAD = { 1: { txt: 'Prioridad I · Crítica', cls: 'p1' }, 2: { txt: 'Prioridad II · Urgente', cls: 'p2' }, 3: { txt: 'Prioridad III · Menor', cls: 'p3' } };
const ESTADO_ALERTA = { PENDIENTE_ENVIO: 'En cola (sin señal)', ENVIADA: 'Enviada', ENTREGADA: 'Entregada al hospital',
                        CONFIRMADA: 'Hospital confirmó', RECHAZADA: 'Rechazada', SIN_DESTINO: 'Sin hospital disponible' };
const camasTxt = (n) => (n | 0) + ((n | 0) === 1 ? ' cama UCI libre' : ' camas UCI libres');
const SENAL_TXT = { en_linea: 'En línea', debil: 'Señal débil', sin_senal: 'Sin señal' };

const UI = {
  toast(texto, tipo = 'ok') {
    let caja = document.getElementById('kq-toasts');
    if (!caja) { caja = document.createElement('div'); caja.id = 'kq-toasts'; caja.className = 'kq-toasts'; caja.setAttribute('role', 'status'); caja.setAttribute('aria-live', 'polite'); document.body.appendChild(caja); }
    const t = document.createElement('div'); t.className = 'kq-toast kq-toast--' + tipo; t.textContent = texto; caja.appendChild(t);
    setTimeout(() => { t.classList.add('kq-toast--sale'); setTimeout(() => t.remove(), 300); }, 3800);
  },
  // Muestra el estado de conexión y la cantidad de pendientes dentro de un elemento
  montarEstado(el, app) {
    const pintar = () => {
      const s = app.estado();
      const txt = { buena: 'Conectado' + (s.ms ? ' · ' + Math.round(s.ms) + ' ms' : ''), simulada: 'Nube simulada (este navegador)',
                    conectando: 'Conectando…', debil: 'Señal débil', sin_conexion: s.forzado ? 'Sin internet (simulado)' : 'Sin conexión' }[s.nivel];
      el.className = 'kq-estado kq-estado--' + s.nivel;
      el.innerHTML = '<span class="kq-estado__punto"></span><span class="kq-estado__txt">' + esc(txt) + '</span>' +
        (s.pendientes ? '<span class="kq-estado__cola" title="Cambios guardados en este equipo que aún no llegan a la nube">' + s.pendientes + ' por enviar</span>' : '') +
        (s.nivel === 'sin_conexion' && !s.pendientes ? '' : '');
      el.title = s.ultimaOk ? 'Última sincronización ' + tiempoRelativo(s.ultimaOk) : 'Aún sin sincronizar';
    };
    app.ev.on('estado', pintar); pintar(); setInterval(pintar, 15000);
  },
  tarjetasDispositivos(lista, yoId) {
    if (!lista.length) return '<p class="kq-vacio">Todavía no hay equipos vinculados. Registre esta PC para comenzar.</p>';
    return lista.map((d) => {
      const s = ControladorEmergencias.senal(d); const caps = (d.capacidades || []).map((c) => '<li>' + esc(CAPACIDADES[c] || c) + '</li>').join('');
      return '<article class="kq-disp kq-disp--' + s + '"><header><span class="kq-disp__punto" title="' + SENAL_TXT[s] + '"></span><strong>' + esc(d.nombre) + '</strong>' +
        (d.id === yoId ? '<em class="kq-disp__yo">este equipo</em>' : '') + '</header>' +
        '<p class="kq-disp__meta">' + esc(TIPOS[d.tipo] || d.tipo) + ' · Categoría ' + esc(d.categoria) + (d.tipo === 'HOSPITAL' ? ' · ' + camasTxt(d.camas_uci) : '') + '</p>' +
        (caps ? '<ul class="kq-disp__caps">' + caps + '</ul>' : '') +
        '<p class="kq-disp__senal">' + SENAL_TXT[s] + (d.id === yoId ? '' : ' · visto ' + tiempoRelativo(Date.now() - (d.visto_hace || 0) * 1000 - (Date.now() - (d._t || Date.now())))) + '</p></article>';
    }).join('');
  },
  chipsPrioridad(p) { const x = PRIORIDAD[p] || PRIORIDAD[2]; return '<span class="kq-prio kq-prio--' + x.cls + '">' + x.txt + '</span>'; },
  estadoAlerta(e) { return ESTADO_ALERTA[e] || e; },
  camasTxt, tiempoRelativo
};

class Sirena {
  constructor() { this.ctx = null; this.timer = null; }
  habilitar() { try { this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)(); if (this.ctx.state === 'suspended') this.ctx.resume(); } catch (e) { /* sin audio */ } }
  _beep(f) {
    if (!this.ctx) return;
    const o = this.ctx.createOscillator(), g = this.ctx.createGain(); o.type = 'square'; o.frequency.value = f; g.gain.value = 0.07;
    o.connect(g); g.connect(this.ctx.destination); o.start(); o.stop(this.ctx.currentTime + 0.35);
  }
  prueba() { this.habilitar(); this._beep(660); setTimeout(() => this._beep(880), 400); }
  iniciar() { if (this.timer) return; let alto = false; const t = () => { this._beep(alto ? 880 : 660); alto = !alto; }; t(); this.timer = setInterval(t, 500); }
  detener() { clearInterval(this.timer); this.timer = null; }
}

/* Ventana de alerta: aparece sola en el equipo del hospital destino */
class AlertaVisual {
  constructor(app) {
    this.app = app; this.cola = []; this.actual = null; this.sirena = new Sirena(); this.tituloOriginal = document.title; this.parpadeo = null;
    document.addEventListener('pointerdown', () => this.sirena.habilitar(), { once: true });   // el navegador exige un clic para permitir sonido
    this._montar();
    app.ev.on('alerta-entrante', (a) => this.encolar(a));
    app.ev.on('alertas', () => this._revisar());
  }
  _montar() {
    const d = document.createElement('div'); d.id = 'kq-alerta'; d.className = 'kq-alerta'; d.hidden = true;
    d.setAttribute('role', 'alertdialog'); d.setAttribute('aria-modal', 'true'); d.setAttribute('aria-labelledby', 'kq-al-titulo');
    d.innerHTML = '<div class="kq-alerta__panel">' +
      '<header class="kq-alerta__cab"><div><p id="kq-al-prio"></p><h2 id="kq-al-titulo">Emergencia entrante</h2></div><span id="kq-al-mas" class="kq-alerta__mas"></span></header>' +
      '<p id="kq-al-origen" class="kq-alerta__origen"></p><dl id="kq-al-datos" class="kq-alerta__datos"></dl>' +
      '<div><p class="kq-alerta__sub">Lo que necesita el paciente</p><ul id="kq-al-reqs" class="kq-alerta__reqs"></ul></div>' +
      '<div id="kq-al-rechazo" class="kq-alerta__rechazo" hidden><label for="kq-al-motivo">Motivo (llega a la posta)</label>' +
      '<input id="kq-al-motivo" maxlength="100" placeholder="Ej.: sin camas UCI disponibles"><button type="button" id="kq-al-enviar-rechazo" class="kq-btn kq-btn--peligro">Enviar rechazo</button></div>' +
      '<footer class="kq-alerta__acciones"><button type="button" id="kq-al-ok" class="kq-btn kq-btn--ok">Recibido: preparar equipo</button>' +
      '<button type="button" id="kq-al-no" class="kq-btn kq-btn--sec">No podemos recibirlo</button></footer></div>';
    document.body.appendChild(d);
    d.querySelector('#kq-al-ok').onclick = () => this._responder('CONFIRMADA');
    d.querySelector('#kq-al-no').onclick = () => { d.querySelector('#kq-al-rechazo').hidden = false; d.querySelector('#kq-al-motivo').focus(); };
    d.querySelector('#kq-al-enviar-rechazo').onclick = () => this._responder('RECHAZADA', d.querySelector('#kq-al-motivo').value.trim());
  }
  encolar(a) { if (!this.cola.some((x) => x.id === a.id) && !(this.actual && this.actual.id === a.id)) this.cola.push(a); if (!this.actual) this._siguiente(); else this._pintarMas(); }
  _revisar() { /* si la alerta fue reasignada o respondida desde otra pestaña, se cierra sola */
    if (this.actual) { const a = this.app.db.alertas.find((x) => x.id === this.actual.id);
      if (a && !['ENVIADA', 'ENTREGADA'].includes(a.estado)) this._cerrar(); } }
  _siguiente() {
    this.cola.sort((a, b) => a.prioridad - b.prioridad || a.creada - b.creada);
    this.actual = this.cola.shift() || null; if (!this.actual) return;
    const a = this.actual, det = this.app.emergencias.detalle(a), yo = this.app.identidad || {}, caps = yo.capacidades || [];
    const el = document.getElementById('kq-alerta');
    el.querySelector('#kq-al-prio').innerHTML = UI.chipsPrioridad(a.prioridad);
    el.querySelector('#kq-al-origen').innerHTML = 'Enviada por <strong>' + esc(a.origen_nombre) + '</strong> ' + UI.tiempoRelativo(a.creada);
    const fila = (k, v) => v ? '<div><dt>' + k + '</dt><dd>' + esc(v) + '</dd></div>' : '';
    el.querySelector('#kq-al-datos').innerHTML = fila('Paciente', det.paciente || 'Sin identificar') + fila('Edad', det.edad ? det.edad + ' años' : '') + fila('DNI', det.dni) + fila('Cuadro clínico', det.cuadro);
    el.querySelector('#kq-al-reqs').innerHTML = (a.requisitos || []).length ? a.requisitos.map((r) => caps.includes(r)
      ? '<li class="si">✓ ' + esc(CAPACIDADES[r] || r) + ' <small>disponible aquí</small></li>' : '<li class="no">✕ ' + esc(CAPACIDADES[r] || r) + ' <small>no registrado en este equipo</small></li>').join('') : '<li>Sin requisitos especiales</li>';
    el.querySelector('#kq-al-rechazo').hidden = true; el.querySelector('#kq-al-motivo').value = '';
    el.hidden = false; this._pintarMas(); el.querySelector('#kq-al-ok').focus();
    this.sirena.iniciar(); if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]);
    clearInterval(this.parpadeo); let on = false; this.parpadeo = setInterval(() => { document.title = (on = !on) ? '🚨 EMERGENCIA ENTRANTE' : this.tituloOriginal; }, 800);
    try { if (window.Notification && Notification.permission === 'granted' && document.hidden) new Notification('🚨 Emergencia entrante', { body: a.origen_nombre + ' · ' + (det.cuadro || '') }); } catch (e) { /* nada */ }
  }
  _pintarMas() { const m = document.getElementById('kq-al-mas'); if (m) m.textContent = this.cola.length ? '+' + this.cola.length + ' más en espera' : ''; }
  _responder(estado, motivo) {
    if (!this.actual) return;
    this.app.emergencias.responder(this.actual.id, estado, motivo);
    UI.toast(estado === 'CONFIRMADA' ? 'Confirmado. La posta ya sabe que están preparando el equipo.' : 'Rechazo enviado. El sistema buscará otro hospital.', estado === 'CONFIRMADA' ? 'ok' : 'aviso');
    this._cerrar();
  }
  _cerrar() {
    this.actual = null; document.getElementById('kq-alerta').hidden = true; this.sirena.detener();
    clearInterval(this.parpadeo); document.title = this.tituloOriginal; this._siguiente();
  }
}

/* ---------- 12. Arranque ---------- */
const KunaqCore = {
  app: null, UI, Filtros, resumenStock, estadoStock, ControladorEmergencias, CAPACIDADES, TIPOS, CATEGORIAS_MINSA, PLANTILLAS, PRIORIDAD,
  BaseLocal, sha256, esc, normalizar, SeguridadKunaq, Sesion,
  // PIN de 6 dígitos aleatorio (criptográfico) para el portal del paciente; evita los más obvios
  generarPin() {
    const malos = ['000000', '111111', '222222', '333333', '444444', '555555', '666666', '777777', '888888', '999999', '123456', '654321'];
    let pin;
    do { pin = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, '0'); } while (malos.includes(pin));
    return pin;
  },
  iniciar(opciones = {}) {
    if (KunaqCore.app) return KunaqCore.app;
    BaseLocal.asegurar();
    const app = KunaqCore.app = new KunaqApp();
    if (opciones.alertas !== false) KunaqCore.alerta = new AlertaVisual(app);
    app.iniciar();
    // Service worker: guarda las páginas en el equipo para abrirlas aunque no haya internet (solo con http/https)
    if ('serviceWorker' in navigator && /^https?:/.test(location.protocol)) navigator.serviceWorker.register(opciones.sw || '../sw.js').catch(() => {});
    return app;
  }
};
root.KunaqCore = KunaqCore;
if (typeof module !== 'undefined' && module.exports) {   // para pruebas en Node
  module.exports = { KunaqApp, BaseLocal, sha256, ControladorEmergencias, NucleoNube, Filtros, resumenStock, estadoStock, INVENTARIO_BASE, SeguridadKunaq };
}
})(typeof window !== 'undefined' ? window : globalThis);
