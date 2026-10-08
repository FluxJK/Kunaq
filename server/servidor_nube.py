"""Servidor NUBE de Kunaq.

Qué hace:
  * Guarda en una base de datos lo que envían las postas/hospitales:
      - PostgreSQL si existe la variable DATABASE_URL (Render, Neon, Supabase...)
      - SQLite (kunaq_nube.db) si no existe (pruebas en una PC)
  * Recibe operaciones en lotes pequeños (/api/sync/push) y entrega SOLO los
    cambios nuevos (/api/sync/pull?cursor=N): ideal para internet débil.
  * Enruta emergencias con ControladorEmergencias (filter/map/sorted/reduce)
    y las reasigna al siguiente hospital si el primero rechaza.
  * Tiene TRES MODOS (variable KUNAQ_MODO o --modo):
      todo      (por defecto) todo junto, para probar en una PC
      hospital  solo personal de salud: index/admin + /api/sync/*  (exige KUNAQ_TOKEN)
      paciente  solo pacientes: paciente.html + /api/paciente/consulta (DNI + PIN)
    En producción se publican DOS servicios (uno por modo) con la MISMA base de datos.

Uso local:
    python server/servidor_nube.py                 (modo todo, puerto 8765)
    python server/servidor_nube.py --modo hospital --puerto 9000

Variables:
  DATABASE_URL       conexión PostgreSQL (si falta, usa SQLite)
  KUNAQ_MODO         todo | hospital | paciente
  KUNAQ_ADMIN_USUARIO / KUNAQ_ADMIN_CLAVE   cuenta del administrador (se crea/actualiza al arrancar; mínimo 8 caracteres).
                     El administrador crea las cuentas del personal desde la portada. Obligatoria en modo hospital.
  KUNAQ_SESION_HORAS duración de cada inicio de sesión del personal (por defecto 24)
  KUNAQ_TOKEN        (opcional, heredado) código de red compartido; en producción use cuentas de personal
  KUNAQ_PEPPER       secreto para proteger los DNI (obligatorio en hospital/paciente; IGUAL en ambos)
  KUNAQ_LLAVE        secreto para cifrar en la base los nombres y datos clínicos (obligatorio en hospital/paciente;
                     IGUAL en ambos). Si se pierde, esos datos no se pueden recuperar.
  KUNAQ_URL_PACIENTE dirección pública del portal del paciente (el modo hospital la muestra en su portada)
  KUNAQ_CORS         origen permitido para CORS (por defecto "*" solo en modo todo)
  KUNAQ_SEMILLA_DEMO 1 = crea un paciente de prueba (DNI 70123456, PIN 1234). No usar con datos reales.
  PORT               puerto (Render lo define solo)
"""
import argparse, base64, hashlib, hmac, json, mimetypes, os, re, secrets, socket, sqlite3, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
from models.entidades import Dispositivo, ControladorEmergencias          # noqa: E402
from models.inventario_base import INVENTARIO_BASE                         # noqa: E402

RUTA_DB = os.environ.get("KUNAQ_DB", os.path.join(RAIZ, "kunaq_nube.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
TOKEN = os.environ.get("KUNAQ_TOKEN", "")
PEPPER = os.environ.get("KUNAQ_PEPPER", "")
LLAVE = os.environ.get("KUNAQ_LLAVE", "")
ADMIN_USUARIO = os.environ.get("KUNAQ_ADMIN_USUARIO", "admin").strip().lower()
ADMIN_CLAVE = os.environ.get("KUNAQ_ADMIN_CLAVE", "")
SESION_HORAS = float(os.environ.get("KUNAQ_SESION_HORAS", "24"))
URL_PACIENTE = os.environ.get("KUNAQ_URL_PACIENTE", "")
MODOS = ("todo", "hospital", "paciente")
EXT_PERMITIDAS = {".html", ".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".json", ".webmanifest"}
EXT_PACIENTE = {".css", ".png", ".jpg", ".jpeg", ".svg", ".ico"}            # el portal del paciente NO recibe .js
TIPOS_OP = {"DISPOSITIVO", "DISPOSITIVO_BAJA", "MED_UPSERT", "STOCK_DELTA",
            "ATENCION", "EMERGENCIA", "ALERTA_ESTADO", "PACIENTE"}
RE_HASH = re.compile(r"[0-9a-f]{64}")
RE_USUARIO = re.compile(r"[a-z0-9._-]{3,30}")
ROLES = ("admin", "personal")

ahora_ms = lambda: int(time.time() * 1000)


# ============================================================ base de datos
class Fila(dict):
    """Fila que se lee por nombre (f["id"]) o por posición (f[0]), igual que sqlite3.Row."""
    def __getitem__(self, k):
        return list(self.values())[k] if isinstance(k, int) else super().__getitem__(k)


def _fila_pg(cursor):
    nombres = [c.name for c in (cursor.description or [])]
    return lambda valores: Fila(zip(nombres, valores))


def es_error_conexion(e):
    """True si el error es de red/conexión con PostgreSQL (se debe reintentar, no descartar la operación)."""
    return type(e).__module__.startswith("psycopg") and type(e).__name__ in ("OperationalError", "InterfaceError", "AdminShutdown")


class BD:
    """Envoltura mínima: el mismo código SQL sirve para SQLite y para PostgreSQL."""

    def __init__(self, url="", ruta=RUTA_DB):
        self.pg, self.url, self.ruta = bool(url), url, ruta
        self._conectar()

    def _conectar(self):
        if self.pg:
            import psycopg                      # pip install "psycopg[binary]"
            self.con = psycopg.connect(self.url, row_factory=_fila_pg)
        else:
            self.con = sqlite3.connect(self.ruta, check_same_thread=False)
            self.con.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        if self.pg:
            return self.con.execute(sql.replace("?", "%s"), params or None)
        return self.con.execute(sql, params)

    def commit(self):
        self.con.commit()

    def verificar(self):
        """Se llama al inicio de cada operación: limpia transacciones rotas y reconecta si la conexión se cayó."""
        if not self.pg:
            return
        try:
            self.con.rollback()
            self.con.execute("SELECT 1")
            self.con.rollback()
        except Exception:
            try:
                self.con.close()
            except Exception:
                pass
            self._conectar()


class Limitador:
    """Límite de intentos en memoria (protege el PIN de 4 dígitos contra fuerza bruta)."""

    def __init__(self):
        self.f, self.lock = {}, threading.Lock()

    def _vivos(self, clave, ventana):
        t = time.time()
        self.f[clave] = [x for x in self.f.get(clave, []) if t - x < ventana]
        return self.f[clave]

    def bloqueado(self, clave, maximo, ventana):
        with self.lock:
            return len(self._vivos(clave, ventana)) >= maximo

    def registrar(self, clave, ventana):
        with self.lock:
            self._vivos(clave, ventana).append(time.time())

    def limpiar(self, clave):
        with self.lock:
            self.f.pop(clave, None)


class Nube:
    """Lógica de negocio de la nube (independiente de HTTP, para poder probarla)."""

    def __init__(self, bd=None, modo="todo"):
        self.db = bd or BD(DATABASE_URL)
        self.modo = modo
        self.lock = threading.RLock()
        self.limitador = Limitador()
        self._fernet = None
        if LLAVE:                                   # cifrado en reposo: cualquier texto secreto sirve de llave
            from cryptography.fernet import Fernet  # pip install cryptography
            self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(LLAVE.encode()).digest()))
        self._crear_tablas()
        self._hay_usuarios = self._contar_usuarios() > 0
        if ADMIN_CLAVE and self.modo != "paciente":
            self.crear_usuario(ADMIN_USUARIO, "Administrador", ADMIN_CLAVE, "admin")
        if os.environ.get("KUNAQ_SEMILLA_DEMO") == "1":
            self._semilla_demo()

    # ------------------------------------------------------------ esquema
    ESQUEMA = [
        "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v BIGINT)",
        "CREATE TABLE IF NOT EXISTS ops(id TEXT PRIMARY KEY, tipo TEXT, dispositivo TEXT, ts BIGINT)",
        """CREATE TABLE IF NOT EXISTS dispositivos(
            id TEXT PRIMARY KEY, nombre TEXT, tipo TEXT, categoria TEXT, capacidades TEXT,
            camas_uci INTEGER, lat DOUBLE PRECISION, lng DOUBLE PRECISION, visto BIGINT, activo INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS inventario(
            id INTEGER PRIMARY KEY, nombre TEXT, categoria TEXT, stock INTEGER, minimo INTEGER,
            unidad TEXT, ubicacion TEXT, seq BIGINT)""",
        """CREATE TABLE IF NOT EXISTS alertas(
            id TEXT PRIMARY KEY, origen_id TEXT, origen_nombre TEXT, destino_id TEXT, destino_nombre TEXT,
            prioridad INTEGER, requisitos TEXT, datos_cifrados TEXT, estado TEXT, rechazados TEXT,
            bitacora TEXT, creada BIGINT, actualizada BIGINT, seq BIGINT)""",
        """CREATE TABLE IF NOT EXISTS atenciones(
            id TEXT PRIMARY KEY, dni_hash TEXT, nombre TEXT, fecha TEXT, hospital TEXT,
            datos_cifrados TEXT, origen_id TEXT, creada BIGINT)""",
        "CREATE INDEX IF NOT EXISTS ix_aten ON atenciones(dni_hash)",
        # Pacientes con acceso al portal: el DNI NO se guarda, solo su HMAC; el PIN solo como hash PBKDF2.
        """CREATE TABLE IF NOT EXISTS pacientes(
            clave TEXT PRIMARY KEY, nombre TEXT, pin_hash TEXT, sal TEXT, creado BIGINT)""",
        # Cuentas del personal de salud (contraseña solo como hash PBKDF2) y sus sesiones (el token solo como SHA-256)
        """CREATE TABLE IF NOT EXISTS usuarios(
            usuario TEXT PRIMARY KEY, nombre TEXT, rol TEXT, clave_hash TEXT, sal TEXT, activo INTEGER DEFAULT 1, creado BIGINT)""",
        "CREATE TABLE IF NOT EXISTS sesiones(token_hash TEXT PRIMARY KEY, usuario TEXT, expira BIGINT)",
        "INSERT INTO meta(k, v) VALUES('seq', 0) ON CONFLICT DO NOTHING",
    ]

    def _crear_tablas(self):
        for intento in range(3):            # dos servicios pueden arrancar a la vez en la misma base
            try:
                with self.lock:
                    for sql in self.ESQUEMA:
                        self.db.execute(sql)
                    self.db.commit()
                break
            except Exception:
                self.db.verificar()
                if intento == 2:
                    raise
                time.sleep(1.5)
        if self.modo == "paciente":
            return                          # el portal del paciente no siembra inventario
        with self.lock:
            if self.db.execute("SELECT COUNT(*) FROM inventario").fetchone()[0] == 0:
                for (i, n, c, s, m, u, ub) in INVENTARIO_BASE:
                    self.db.execute("INSERT INTO inventario VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                                    (i, n, c, s, m, u, ub, self._seq()))
            self.db.commit()

    def _seq(self):
        self.db.execute("UPDATE meta SET v = v + 1 WHERE k='seq'")
        return self.db.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]

    def _cursor(self):
        return self.db.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]

    # ------------------------------------------------- DNI y PIN (seguridad)
    @staticmethod
    def _clave_dni(dni_hash):
        """HMAC con secreto (pepper) del SHA-256 que calcula el equipo. Sin el pepper, la base no permite adivinar DNIs."""
        return hmac.new((PEPPER or "kunaq-solo-desarrollo").encode(), dni_hash.encode(), "sha256").hexdigest()

    @staticmethod
    def _hash_pin(pin, sal):
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), sal, 200_000).hex()

    def _semilla_demo(self):
        h = hashlib.sha256(b"70123456").hexdigest()
        self._op_paciente("demo", {"dni_hash": h, "nombre": "Juan Perez Quispe", "pin": "1234"})
        clave = self._clave_dni(h)
        cif = lambda t: base64.b64encode(quote(t, safe="-_.!~*'()").encode()).decode()
        with self.lock:
            for i, (f, hosp, txt) in enumerate([
                    ("05/10/2026", "Posta de Salud Laredo", "Diagnóstico: Infección respiratoria leve | Receta: Paracetamol 500mg"),
                    ("15/08/2026", "Hospital Regional Trujillo", "Diagnóstico: Control general | Receta: Vitaminas, reposo")]):
                self.db.execute("INSERT INTO atenciones VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                                (f"A-demo-{i}", clave, self._sellar("Juan Perez Quispe"), f, hosp, self._sellar(cif(txt)), "demo", ahora_ms() - i * 1000))
            self.db.commit()

    # ------------------------------------------- cifrado en reposo (Fernet)
    def _sellar(self, texto):
        """Cifra con KUNAQ_LLAVE antes de guardar. Sin llave (solo pruebas en una PC) guarda tal cual."""
        texto = texto or ""
        return "f1:" + self._fernet.encrypt(texto.encode()).decode() if self._fernet else texto

    def _abrir(self, guardado):
        if not guardado or not guardado.startswith("f1:"):
            return guardado or ""                     # dato anterior al cifrado: se devuelve igual
        if not self._fernet:
            return "[dato cifrado: falta KUNAQ_LLAVE]"
        try:
            return self._fernet.decrypt(guardado[3:].encode()).decode()
        except Exception:
            return "[dato no legible]"

    # ------------------------------------------------- cuentas del personal
    def _contar_usuarios(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM usuarios WHERE activo=1").fetchone()[0]

    def auth_requerida(self):
        """En producción (hospital) siempre. En modo todo solo si hay cuentas o código de red (así sigue siendo fácil probar)."""
        return self.modo != "todo" or bool(TOKEN) or self._hay_usuarios

    def crear_usuario(self, usuario, nombre, clave, rol="personal"):
        usuario = str(usuario).strip().lower()
        if not RE_USUARIO.fullmatch(usuario):
            raise ValueError("usuario: 3 a 30 caracteres (letras minúsculas, números, . _ -)")
        if len(str(clave)) < 8:
            raise ValueError("la contraseña debe tener al menos 8 caracteres")
        if rol not in ROLES:
            raise ValueError("rol inválido")
        sal = secrets.token_bytes(16)
        with self.lock:
            self.db.verificar()
            self.db.execute("""INSERT INTO usuarios VALUES(?,?,?,?,?,1,?)
                ON CONFLICT(usuario) DO UPDATE SET nombre=excluded.nombre, rol=excluded.rol,
                  clave_hash=excluded.clave_hash, sal=excluded.sal, activo=1""",
                (usuario, (str(nombre).strip() or usuario)[:60], rol, self._hash_pin(str(clave), sal), sal.hex(), ahora_ms()))
            self.db.execute("DELETE FROM sesiones WHERE usuario=?", (usuario,))     # cambiar la contraseña cierra sus sesiones
            self.db.commit()
        self._hay_usuarios = True

    def desactivar_usuario(self, actor, usuario):
        usuario = str(usuario).strip().lower()
        if usuario == actor:
            raise ValueError("no puede desactivar su propia cuenta")
        with self.lock:
            self.db.verificar()
            self.db.execute("UPDATE usuarios SET activo=0 WHERE usuario=?", (usuario,))
            self.db.execute("DELETE FROM sesiones WHERE usuario=?", (usuario,))
            self.db.commit()

    def listar_usuarios(self):
        with self.lock:
            self.db.verificar()
            return [dict(r) for r in self.db.execute(
                "SELECT usuario,nombre,rol,activo FROM usuarios ORDER BY usuario").fetchall()]

    def login(self, usuario, clave, ip):
        usuario, clave = str(usuario).strip().lower()[:40], str(clave)[:200]
        if self.limitador.bloqueado("ipl:" + ip, 30, 600):
            return {"ok": False, "error": "Demasiados intentos. Espere unos minutos.", "codigo": 429}
        self.limitador.registrar("ipl:" + ip, 600)
        if self.limitador.bloqueado("usr:" + usuario, 5, 900):
            return {"ok": False, "error": "Demasiados intentos para esta cuenta. Espere 15 minutos.", "codigo": 429}
        with self.lock:
            self.db.verificar()
            f = self.db.execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,)).fetchone()
        calculado = self._hash_pin(clave, bytes.fromhex(f["sal"]) if f else b"\x00" * 16)   # mismo tiempo exista o no
        if not f or not hmac.compare_digest(calculado, f["clave_hash"]):
            self.limitador.registrar("usr:" + usuario, 900)
            return {"ok": False, "error": "Usuario o contraseña incorrectos", "codigo": 401}
        self.limitador.limpiar("usr:" + usuario)
        token, expira = secrets.token_urlsafe(32), ahora_ms() + int(SESION_HORAS * 3600 * 1000)
        with self.lock:
            self.db.execute("DELETE FROM sesiones WHERE expira<?", (ahora_ms(),))
            self.db.execute("INSERT INTO sesiones VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), usuario, expira))
            self.db.commit()
        return {"ok": True, "token": token, "usuario": usuario, "nombre": f["nombre"], "rol": f["rol"], "expira": expira}

    def logout(self, token):
        with self.lock:
            self.db.verificar()
            self.db.execute("DELETE FROM sesiones WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
            self.db.commit()

    def autenticar(self, token):
        """Devuelve la cuenta dueña del token, o None. Acepta también el código de red heredado (KUNAQ_TOKEN)."""
        if not token:
            return None
        if TOKEN and hmac.compare_digest(token, TOKEN):
            return {"usuario": "red", "nombre": "Código de red", "rol": "personal"}
        with self.lock:
            self.db.verificar()
            f = self.db.execute("""SELECT u.usuario, u.nombre, u.rol FROM sesiones s JOIN usuarios u ON u.usuario=s.usuario
                                   WHERE s.token_hash=? AND s.expira>? AND u.activo=1""",
                                (hashlib.sha256(token.encode()).hexdigest(), ahora_ms())).fetchone()
            return dict(f) if f else None

    # --------------------------------------------------------- dispositivos
    def _fila_a_dispositivo(self, f, t=None):
        t = t or ahora_ms()
        return {"id": f["id"], "nombre": f["nombre"], "tipo": f["tipo"], "categoria": f["categoria"],
                "capacidades": json.loads(f["capacidades"] or "[]"), "camas_uci": f["camas_uci"],
                "lat": f["lat"], "lng": f["lng"],
                "visto_hace": max(0, round((t - (f["visto"] or 0)) / 1000)) if f["visto"] else 99999}

    def listar_dispositivos(self):
        t = ahora_ms()
        return [self._fila_a_dispositivo(f, t) for f in
                self.db.execute("SELECT * FROM dispositivos WHERE activo=1 ORDER BY nombre").fetchall()]

    def _objetos_dispositivo(self):
        return [Dispositivo.desde_dict(d) for d in self.listar_dispositivos()]

    # ----------------------------------------------------------------- push
    def push(self, dispositivo, ops):
        aceptadas, rechazadas = [], []
        with self.lock:
            self.db.verificar()
            for op in ops[:50]:
                try:
                    oid, tipo = str(op["id"]), op["tipo"]
                    if tipo not in TIPOS_OP:
                        raise ValueError("tipo de operación desconocido")
                    if self.db.execute("SELECT 1 FROM ops WHERE id=?", (oid,)).fetchone():
                        aceptadas.append(oid)          # ya aplicada: reintento seguro (idempotente)
                        continue
                    self.db.execute("SAVEPOINT op")    # si la operación falla, se deshace SOLO ella
                    try:
                        getattr(self, "_op_" + tipo.lower())(dispositivo, op.get("datos") or {})
                        self.db.execute("INSERT INTO ops VALUES(?,?,?,?)", (oid, tipo, dispositivo, ahora_ms()))
                        self.db.execute("RELEASE SAVEPOINT op")
                    except Exception:
                        try:                            # deshace solo esta operación y deja la transacción sana
                            self.db.execute("ROLLBACK TO SAVEPOINT op")
                            self.db.execute("RELEASE SAVEPOINT op")
                        except Exception:
                            pass                        # (si la conexión murió, se reintentará el lote)
                        raise
                    aceptadas.append(oid)
                except Exception as e:
                    if es_error_conexion(e):
                        raise                           # fallo de red con la base: el equipo reintenta el lote completo
                    rechazadas.append({"id": op.get("id") if isinstance(op, dict) else None, "error": str(e)})
            self.db.commit()
            return {"aceptadas": aceptadas, "rechazadas": rechazadas, "cursor": self._cursor()}

    def _op_dispositivo(self, _, d):
        if not d.get("id") or not d.get("nombre"):
            raise ValueError("dispositivo sin id o nombre")
        self.db.execute("""INSERT INTO dispositivos(id,nombre,tipo,categoria,capacidades,camas_uci,lat,lng,visto,activo)
            VALUES(?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, tipo=excluded.tipo, categoria=excluded.categoria,
              capacidades=excluded.capacidades, camas_uci=excluded.camas_uci, lat=excluded.lat, lng=excluded.lng, activo=1""",
            (d["id"], d["nombre"][:80], d.get("tipo", "POSTA"), d.get("categoria", "I-1"),
             json.dumps(d.get("capacidades", [])), int(d.get("camas_uci") or 0), d.get("lat"), d.get("lng"), ahora_ms()))

    def _op_dispositivo_baja(self, _, d):
        self.db.execute("UPDATE dispositivos SET activo=0 WHERE id=?", (d.get("id"),))

    def _op_med_upsert(self, _, m):
        self.db.execute("""INSERT INTO inventario VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, categoria=excluded.categoria, stock=excluded.stock,
              minimo=excluded.minimo, unidad=excluded.unidad, ubicacion=excluded.ubicacion, seq=excluded.seq""",
            (int(m["id"]), m["nombre"][:80], m.get("categoria", "General"), max(0, int(m.get("stock", 0))),
             int(m.get("minimo", 0)), m.get("unidad", "unid."), m.get("ubicacion", "-"), self._seq()))

    def _op_stock_delta(self, _, d):
        # Se envía el CAMBIO (+/-), no el valor final: dos postas que descuentan a la vez no se pisan.
        delta = int(d["delta"])
        self.db.execute("UPDATE inventario SET stock = CASE WHEN stock + ? < 0 THEN 0 ELSE stock + ? END, seq=? WHERE id=?",
                        (delta, delta, self._seq(), int(d["id"])))

    def _op_atencion(self, disp, a):
        if not RE_HASH.fullmatch(str(a.get("dni_hash", ""))):
            raise ValueError("dni_hash inválido")
        self.db.execute("INSERT INTO atenciones VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                        (a["id"], self._clave_dni(a["dni_hash"]), self._sellar(a.get("nombre", "")[:80]), a.get("fecha", "")[:20],
                         a.get("hospital", "")[:80], self._sellar(a["datos_cifrados"]), disp, ahora_ms()))

    def _op_paciente(self, _, d):
        """Alta del acceso del paciente al portal (DNI + PIN de 4 dígitos). El PIN se guarda solo como hash."""
        h, pin = str(d.get("dni_hash", "")), str(d.get("pin", ""))
        if not RE_HASH.fullmatch(h):
            raise ValueError("dni_hash inválido")
        if not re.fullmatch(r"\d{4,6}", pin):
            raise ValueError("el PIN debe tener de 4 a 6 dígitos")
        clave, nombre = self._clave_dni(h), (str(d.get("nombre") or "Paciente").strip() or "Paciente")[:80]
        sal = secrets.token_bytes(16)
        existe = self.db.execute("SELECT nombre FROM pacientes WHERE clave=?", (clave,)).fetchone()
        if not existe:
            self.db.execute("INSERT INTO pacientes VALUES(?,?,?,?,?)",
                            (clave, self._sellar(nombre), self._hash_pin(pin, sal), sal.hex(), ahora_ms()))
        elif d.get("reset"):                          # el personal restablece el PIN
            self.db.execute("UPDATE pacientes SET pin_hash=?, sal=?, nombre=? WHERE clave=?",
                            (self._hash_pin(pin, sal), sal.hex(), self._sellar(nombre), clave))
            self.limitador.limpiar("dni:" + clave)
        elif self._abrir(existe["nombre"]) in ("", "Paciente", "Paciente Nuevo") and nombre not in ("Paciente", "Paciente Nuevo"):
            self.db.execute("UPDATE pacientes SET nombre=? WHERE clave=?", (self._sellar(nombre), clave))

    # ----------------------------------------------------------- emergencias
    def _alerta_dict(self, f):
        return {"id": f["id"], "origen_id": f["origen_id"], "origen_nombre": f["origen_nombre"],
                "destino_id": f["destino_id"], "destino_nombre": f["destino_nombre"],
                "prioridad": f["prioridad"], "requisitos": json.loads(f["requisitos"] or "[]"),
                "datos_cifrados": self._abrir(f["datos_cifrados"]), "estado": f["estado"],
                "rechazados": json.loads(f["rechazados"] or "[]"), "bitacora": json.loads(f["bitacora"] or "[]"),
                "creada": f["creada"], "actualizada": f["actualizada"], "seq": f["seq"]}

    def _elegir_destino(self, requisitos, origen_id, excluir):
        objs = self._objetos_dispositivo()
        origen = next((d for d in objs if d.id == origen_id), None)
        ranking = ControladorEmergencias.ranking(objs, requisitos, origen, list(excluir) + [origen_id])
        return ControladorEmergencias.elegir_mejor(ranking)                   # <- HOF del controlador

    def _op_emergencia(self, disp, a):
        reqs = a.get("requisitos", [])
        destino_id, destino_nombre = a.get("destino_id"), a.get("destino_nombre")
        bitacora = [{"t": a.get("creada", ahora_ms()), "texto": f"Registrada en {a.get('origen_nombre', disp)}"}]
        valido = destino_id and self.db.execute("SELECT 1 FROM dispositivos WHERE id=? AND activo=1", (destino_id,)).fetchone()
        if not valido:                                  # la posta no tenía datos frescos: decide la nube
            mejor = self._elegir_destino(reqs, a.get("origen_id", disp), [])
            destino_id = mejor["dispositivo"].id if mejor else None
            destino_nombre = mejor["dispositivo"].nombre if mejor else None
        estado = "ENVIADA" if destino_id else "SIN_DESTINO"
        bitacora.append({"t": ahora_ms(), "texto": f"Enviada a {destino_nombre}" if destino_id
                         else "No hay hospitales vinculados para recibirla"})
        self.db.execute("INSERT INTO alertas VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (a["id"], a.get("origen_id", disp), a.get("origen_nombre", ""), destino_id, destino_nombre,
             int(a.get("prioridad", 2)), json.dumps(reqs), self._sellar(a.get("datos_cifrados", "")), estado, "[]",
             json.dumps(bitacora), a.get("creada", ahora_ms()), ahora_ms(), self._seq()))

    def _op_alerta_estado(self, disp, d):
        f = self.db.execute("SELECT * FROM alertas WHERE id=?", (d["id"],)).fetchone()
        if not f:
            raise ValueError("alerta inexistente")
        al = self._alerta_dict(f)
        bit = al["bitacora"]
        if d["estado"] == "CONFIRMADA":
            al["estado"] = "CONFIRMADA"
            bit.append({"t": ahora_ms(), "texto": f"{al['destino_nombre']} confirmó: preparando equipo"})
        elif d["estado"] == "RECHAZADA":
            motivo = (d.get("motivo") or "sin motivo")[:120]
            rech = al["rechazados"] + [al["destino_id"]]
            bit.append({"t": ahora_ms(), "texto": f"{al['destino_nombre']} no puede recibir ({motivo})"})
            nuevo = self._elegir_destino(al["requisitos"], al["origen_id"], rech)
            if nuevo:                                    # reasignación automática al siguiente mejor
                al.update(destino_id=nuevo["dispositivo"].id, destino_nombre=nuevo["dispositivo"].nombre, estado="ENVIADA")
                bit.append({"t": ahora_ms(), "texto": f"Reasignada a {al['destino_nombre']}"})
            else:
                al["estado"] = "SIN_DESTINO"
                bit.append({"t": ahora_ms(), "texto": "Ningún otro hospital disponible"})
            al["rechazados"] = rech
        else:
            raise ValueError("estado inválido")
        self.db.execute("""UPDATE alertas SET destino_id=?, destino_nombre=?, estado=?, rechazados=?, bitacora=?,
                           actualizada=?, seq=? WHERE id=?""",
                        (al["destino_id"], al["destino_nombre"], al["estado"], json.dumps(al["rechazados"]),
                         json.dumps(bit), ahora_ms(), self._seq(), al["id"]))

    # ----------------------------------------------------------------- pull
    def pull(self, dispositivo, cursor):
        with self.lock:
            self.db.verificar()
            if dispositivo:
                self.db.execute("UPDATE dispositivos SET visto=? WHERE id=?", (ahora_ms(), dispositivo))
            inv = [dict(r) for r in self.db.execute("SELECT * FROM inventario WHERE seq>?", (cursor,)).fetchall()]
            filas = self.db.execute("SELECT * FROM alertas WHERE seq>? AND (destino_id=? OR origen_id=?)",
                                    (cursor, dispositivo, dispositivo)).fetchall()
            alertas = [self._alerta_dict(f) for f in filas]
            # Las alertas que llegan a su destino pasan a ENTREGADA (el remitente lo verá).
            for a in alertas:
                if a["destino_id"] == dispositivo and a["estado"] == "ENVIADA":
                    bit = a["bitacora"] + [{"t": ahora_ms(), "texto": f"Entregada al equipo de {a['destino_nombre']}"}]
                    s = self._seq()
                    self.db.execute("UPDATE alertas SET estado='ENTREGADA', bitacora=?, actualizada=?, seq=? WHERE id=?",
                                    (json.dumps(bit), ahora_ms(), s, a["id"]))
                    a.update(estado="ENTREGADA", bitacora=bit, seq=s)
            self.db.commit()
            return {"cursor": self._cursor(), "ahora": ahora_ms(), "dispositivos": self.listar_dispositivos(),
                    "inventario": inv, "alertas": alertas}

    # ------------------------------------------------ consultas de historial
    def atenciones(self, dni_hash):
        """Búsqueda del PERSONAL (modo hospital/todo, con código de red)."""
        if not RE_HASH.fullmatch(dni_hash or ""):
            return []
        with self.lock:
            self.db.verificar()
            filas = self.db.execute(
                "SELECT id,nombre,fecha,hospital,datos_cifrados FROM atenciones WHERE dni_hash=? ORDER BY creada DESC LIMIT 30",
                (self._clave_dni(dni_hash),)).fetchall()
            return [{**dict(r), "nombre": self._abrir(r["nombre"]), "datos_cifrados": self._abrir(r["datos_cifrados"])} for r in filas]

    def consulta_paciente(self, dni, pin, ip):
        """Portal del PACIENTE: valida DNI + PIN en el servidor y devuelve SOLO su historial."""
        dni, pin = str(dni).strip(), str(pin).strip()
        if not re.fullmatch(r"\d{6,12}", dni) or not re.fullmatch(r"\d{4,6}", pin):
            return {"ok": False, "error": "DNI o PIN incorrectos", "codigo": 401}
        if self.limitador.bloqueado("ip:" + ip, 30, 600):
            return {"ok": False, "error": "Demasiados intentos. Espere unos minutos.", "codigo": 429}
        self.limitador.registrar("ip:" + ip, 600)
        clave = self._clave_dni(hashlib.sha256(dni.encode()).hexdigest())
        if self.limitador.bloqueado("dni:" + clave, 5, 1800):
            return {"ok": False, "error": "Demasiados intentos para este DNI. Espere 30 minutos o pida al hospital un PIN nuevo.", "codigo": 429}
        with self.lock:
            self.db.verificar()
            f = self.db.execute("SELECT * FROM pacientes WHERE clave=?", (clave,)).fetchone()
        sal = bytes.fromhex(f["sal"]) if f else b"\x00" * 16
        calculado = self._hash_pin(pin, sal)                  # se calcula SIEMPRE: mismo tiempo exista o no el DNI
        if not f or not hmac.compare_digest(calculado, f["pin_hash"]):
            self.limitador.registrar("dni:" + clave, 1800)
            return {"ok": False, "error": "DNI o PIN incorrectos", "codigo": 401}
        self.limitador.limpiar("dni:" + clave)
        with self.lock:
            filas = self.db.execute("SELECT fecha,hospital,datos_cifrados FROM atenciones WHERE dni_hash=? "
                                    "ORDER BY creada DESC LIMIT 30", (clave,)).fetchall()
        return {"ok": True, "nombre": self._abrir(f["nombre"]),
                "atenciones": [{**dict(r), "datos_cifrados": self._abrir(r["datos_cifrados"])} for r in filas]}


# ====================================================================== HTTP
class Manejador(BaseHTTPRequestHandler):
    nube: Nube = None
    modo = "todo"
    cors = "*"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silencioso
        pass

    def _cabeceras_comunes(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", self.cors)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Kunaq-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self._cabeceras_comunes()
        self.end_headers()
        self.wfile.write(cuerpo)

    def _usuario(self):
        """Cuenta autenticada por el encabezado X-Kunaq-Token (sesión o código de red), o None."""
        return self.nube.autenticar(self.headers.get("X-Kunaq-Token", ""))

    def _autorizado(self):
        return (not self.nube.auth_requerida()) or self._usuario() is not None

    def _ip(self):
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[-1].strip() if xff else self.client_address[0]

    def _leer_json(self, maximo):
        largo = int(self.headers.get("Content-Length", "0") or 0)
        if largo > maximo:
            return None
        return json.loads(self.rfile.read(largo) or b"{}")

    def do_OPTIONS(self):
        self.send_response(204); self._cabeceras_comunes()
        self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        try:
            self._get()
        except Exception:
            traceback.print_exc()
            self._json({"error": "error interno"}, 500)

    def do_POST(self):
        try:
            self._post()
        except (ValueError, TypeError) as e:
            self._json({"error": "JSON inválido: %s" % e}, 400)
        except Exception:
            traceback.print_exc()
            self._json({"error": "error interno"}, 500)

    def _get(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/api/ping":
            return self._json({"ok": True, "ahora": ahora_ms(), "modo": self.modo,
                               "requiere_login": self.nube.auth_requerida() if self.modo != "paciente" else False,
                               "requiere_token": bool(TOKEN), "url_paciente": URL_PACIENTE})
        if u.path.startswith("/api/"):
            if self.modo == "paciente":
                return self._json({"error": "no existe"}, 404)
            if not self._autorizado():
                return self._json({"error": "código de red incorrecto"}, 401)
            if u.path == "/api/sync/pull":
                return self._json(self.nube.pull(q.get("dispositivo", [""])[0], int(q.get("cursor", ["0"])[0] or 0)))
            if u.path == "/api/atenciones":
                return self._json({"atenciones": self.nube.atenciones(q.get("dni_hash", [""])[0])})
            if u.path == "/api/personal/lista":
                return self._json({"usuarios": self.nube.listar_usuarios()}) if self._es_admin() else self._json({"error": "solo el administrador"}, 403)
            return self._json({"error": "no existe"}, 404)
        return self._estatico(u.path)

    def _es_admin(self):
        u = self._usuario()
        return bool(u and u["rol"] == "admin")

    def _post_personal(self, ruta):
        d = self._leer_json(4096)
        if d is None:
            return self._json({"error": "solicitud demasiado grande"}, 413)
        if ruta == "/api/personal/login":
            r = self.nube.login(d.get("usuario", ""), d.get("clave", ""), self._ip())
            return self._json({k: v for k, v in r.items() if k != "codigo"}, r.get("codigo", 200))
        if ruta == "/api/personal/logout":
            self.nube.logout(self.headers.get("X-Kunaq-Token", ""))
            return self._json({"ok": True})
        if not self._es_admin():
            return self._json({"error": "solo el administrador puede gestionar cuentas"}, 403)
        try:
            if ruta == "/api/personal/crear":
                self.nube.crear_usuario(d.get("usuario", ""), d.get("nombre", ""), d.get("clave", ""), d.get("rol", "personal"))
            else:
                self.nube.desactivar_usuario(self._usuario()["usuario"], d.get("usuario", ""))
        except ValueError as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        return self._json({"ok": True, "usuarios": self.nube.listar_usuarios()})

    def _post(self):
        ruta = urlparse(self.path).path
        if ruta in ("/api/personal/login", "/api/personal/logout", "/api/personal/crear", "/api/personal/desactivar") \
                and self.modo != "paciente":
            return self._post_personal(ruta)
        if ruta == "/api/paciente/consulta" and self.modo in ("paciente", "todo"):
            d = self._leer_json(2048)
            if d is None:
                return self._json({"error": "solicitud demasiado grande"}, 413)
            r = self.nube.consulta_paciente(d.get("dni", ""), d.get("pin", ""), self._ip())
            return self._json({k: v for k, v in r.items() if k != "codigo"}, r.get("codigo", 200))
        if ruta != "/api/sync/push" or self.modo == "paciente":
            return self._json({"error": "no existe"}, 404)
        if not self._autorizado():
            return self._json({"error": "código de red incorrecto"}, 401)
        d = self._leer_json(262144)
        if d is None:
            return self._json({"error": "lote demasiado grande"}, 413)
        return self._json(self.nube.push(str(d.get("dispositivo", "")), d.get("ops", [])))

    def _estatico(self, ruta):
        inicio = "/views/paciente.html" if self.modo == "paciente" else "/views/index.html"
        if ruta in ("", "/"):
            self.send_response(302); self.send_header("Location", inicio)
            self.send_header("Content-Length", "0"); self.end_headers(); return
        destino = os.path.abspath(os.path.join(RAIZ, ruta.lstrip("/")))
        ext = os.path.splitext(destino)[1].lower()
        rel = os.path.relpath(destino, RAIZ).replace(os.sep, "/")
        ok = destino.startswith(RAIZ + os.sep) and os.path.isfile(destino) and ext in EXT_PERMITIDAS
        if self.modo == "paciente":      # solo su página y recursos visuales (nunca kunaq-core.js ni sw.js)
            ok = ok and (rel == "views/paciente.html" or (rel.startswith("assets/") and ext in EXT_PACIENTE))
        elif self.modo == "hospital":    # el portal del personal no sirve la página del paciente
            ok = ok and rel != "views/paciente.html"
        if not ok:
            return self._json({"error": "no encontrado"}, 404)
        with open(destino, "rb") as f:
            cuerpo = f.read()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(destino)[0] or "application/octet-stream"))
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-cache")
        self._cabeceras_comunes()
        self.end_headers(); self.wfile.write(cuerpo)


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except OSError:
        return "127.0.0.1"


def main():
    global PEPPER
    ap = argparse.ArgumentParser(description="Servidor nube Kunaq")
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--modo", choices=MODOS, default=os.environ.get("KUNAQ_MODO", "todo").lower())
    args = ap.parse_args()
    if args.modo not in MODOS:
        sys.exit("KUNAQ_MODO debe ser: " + ", ".join(MODOS))
    if args.modo != "todo":                                    # producción: exigir secretos
        if args.modo == "hospital" and not (ADMIN_CLAVE or TOKEN):
            sys.exit("ERROR: el modo hospital exige KUNAQ_ADMIN_CLAVE (cuenta del administrador, mínimo 8 caracteres).")
        if not PEPPER or not LLAVE:
            sys.exit("ERROR: defina KUNAQ_PEPPER y KUNAQ_LLAVE (los mismos valores en el servicio hospital y en el de paciente).")
    elif not (PEPPER and LLAVE):
        print("AVISO: sin KUNAQ_PEPPER / KUNAQ_LLAVE los datos no se cifran en la base. Defínalos antes de guardar datos reales.")
    if os.environ.get("RENDER") and not DATABASE_URL:
        print("AVISO: en Render el disco es temporal; sin DATABASE_URL (PostgreSQL) los datos SE BORRAN al reiniciar.")
    Manejador.modo = args.modo
    Manejador.cors = os.environ.get("KUNAQ_CORS", "*" if args.modo == "todo" else "")
    Manejador.nube = Nube(BD(DATABASE_URL), args.modo)
    srv = ThreadingHTTPServer(("0.0.0.0", args.puerto), Manejador)
    inicio = "paciente.html" if args.modo == "paciente" else "index.html"
    print("=" * 62)
    print(f" Kunaq · Servidor nube en marcha · modo: {args.modo}")
    print(f"  Base de datos: {'PostgreSQL' if DATABASE_URL else 'SQLite (' + RUTA_DB + ')'}")
    print(f"  Esta PC      : http://localhost:{args.puerto}/views/{inicio}")
    print(f"  Otros equipos: http://{ip_local()}:{args.puerto}/views/{inicio}")
    if args.modo != "paciente":
        print("  Acceso del personal:", "con cuentas (inicio de sesión)" if Manejador.nube.auth_requerida()
              else "ABIERTO (solo pruebas; defina KUNAQ_ADMIN_CLAVE para exigir inicio de sesión)")
    print("  Cifrado en la base:", "activado (Fernet)" if LLAVE else "NO (defina KUNAQ_LLAVE)")
    print("  Ctrl+C para detener")
    print("=" * 62)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
