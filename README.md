<p align="center">
  <img src="assets/logo.png" alt="Kunaq Logo" width="500">
</p>

# Kunaq · Red de Salud Rural

Mismo proyecto (HTML + clases + funciones de orden superior + SQLite/Python), ahora con
**inventario de 20 medicamentos**, **sincronización con la nube pensada para internet débil**
y **alertas de emergencia entre equipos vinculados**.

## Cómo probarlo

**Opción A: sin instalar nada (para practicar en una sola PC)**
1. Abra `views/index.html` con doble clic en **dos pestañas**.
2. En cada una: clave del personal `0000` → llene el formulario → marque *Modo demostración* → **Vincular esta PC**.
   Una pestaña como **Hospital** (marque sus implementos) y la otra como **Posta**.
3. En la posta: `Panel Médico` → *Emergencia* → elija un caso → **Enviar alerta**. En la pestaña del hospital salta la alerta.

**Opción B: nube real en una PC o red local**
```
python server/servidor_nube.py          # modo "todo": portal del personal + portal del paciente
```
Abra `http://<IP-de-la-PC>:8765/views/index.html` en cada equipo (misma WiFi). Sin cuentas configuradas, el panel se desbloquea con la clave de práctica `0000`. Para exigir **cuentas con usuario y contraseña** (como en producción):
`set KUNAQ_ADMIN_CLAVE=MiClave2026` (Windows) / `export KUNAQ_ADMIN_CLAVE=MiClave2026` antes de arrancar; entre como `admin` y cree las cuentas del personal desde la portada.
Para probar el portal del paciente con un paciente de ejemplo: `KUNAQ_SEMILLA_DEMO=1` (DNI `70123456`, PIN `1234`).

**Opción C: publicar en Render con dos portales separados** → ver la sección *Publicar en Render* más abajo.

## Dos portales separados (personal y pacientes)
El servidor tiene tres modos (`KUNAQ_MODO`):

| Modo | Quién lo usa | Qué sirve | Qué NO sirve |
|---|---|---|---|
| `hospital` | Postas y hospitales | `index.html`, `admin.html`, `/api/sync/*` (exige cuenta del personal) | `paciente.html` y la consulta de pacientes |
| `paciente` | Pacientes | `paciente.html` y `POST /api/paciente/consulta` (DNI + PIN) | Todo lo demás: ni `kunaq-core.js`, ni admin, ni sincronización |
| `todo` | Pruebas en una PC | Todo junto | — |

Los dos portales comparten **la misma base de datos**. Cómo entra un paciente:
1. La posta registra la primera atención del paciente → el sistema genera un **PIN aleatorio de 6 dígitos** y lo muestra en pantalla (se entrega en persona).
2. El PIN viaja una sola vez a la nube, que guarda **solo su hash** (PBKDF2). El DNI tampoco se guarda: solo un HMAC con un secreto (`KUNAQ_PEPPER`).
3. El paciente entra al portal con DNI + PIN; **el servidor** valida, limita intentos (5 fallos por DNI → bloqueo de 30 min; también por IP) y devuelve **solo su historial**.
4. Si el paciente pierde el PIN: búsqueda del personal → **Generar PIN nuevo**.

## Publicar en Render (PostgreSQL + dos servicios)
1. Suba esta carpeta a un repositorio de GitHub (el archivo `render.yaml` debe quedar en la raíz).
2. En Render: **New → Blueprint** → elija el repositorio → **Apply**. Se crean `kunaq-db` (PostgreSQL), `kunaq-hospital` y `kunaq-paciente`; `DATABASE_URL`, `KUNAQ_PEPPER` y `KUNAQ_LLAVE` se generan y conectan solos. Render le **pedirá escribir `KUNAQ_ADMIN_CLAVE`**: es la contraseña del administrador (mínimo 8 caracteres).
3. **Guarde `KUNAQ_LLAVE` y `KUNAQ_PEPPER` en un lugar seguro** (Render → *Environment Groups* → `kunaq-secretos`). Si se pierden, los datos cifrados de la base no se pueden recuperar.
4. Si el servicio del paciente no se llama `kunaq-paciente`, corrija `KUNAQ_URL_PACIENTE` en `kunaq-hospital`.
5. Cada equipo abre la dirección de `kunaq-hospital` (`https://….onrender.com`), entra como `admin`, crea una cuenta para cada persona del personal (portada → *Cuentas del personal*), y cada equipo inicia sesión y se vincula. Los pacientes usan la dirección de `kunaq-paciente`.

Sin Blueprint (manual): cree la base en *New → Postgres*; luego dos *Web Service* con *Build* `pip install -r requirements.txt`, *Start* `python server/servidor_nube.py`, y las variables `KUNAQ_MODO`, `DATABASE_URL` (*Internal Database URL*), `KUNAQ_PEPPER` y `KUNAQ_LLAVE` (iguales en ambos) y `KUNAQ_ADMIN_CLAVE` (solo hospital).

Límites del plan gratuito de Render (verifique en su documentación, cambian): la base PostgreSQL gratuita **expira a los 30 días**; un servicio gratuito **se duerme tras 15 min** sin tráfico y tarda ~1 min en despertar. Sirve para la demostración; para uso real, plan de pago o una base permanente (Neon/Supabase: basta pegar su cadena en `DATABASE_URL`).

Pruebas automáticas: `python tests/prueba_nube.py sqlite` (y `pg` si instala `pgserver`).

## Qué pasa cuando la señal es mala
| Problema | Cómo lo resuelve |
|---|---|
| No hay internet | Todo se guarda en el equipo (`localStorage`) y entra a una **cola de salida** |
| Internet intermitente | Envía en lotes de 15, con **tiempo límite de 8 s** y reintentos cada vez más espaciados (3 s → 60 s) |
| El reintento llega dos veces | Cada cambio tiene un **ID único**; la nube ignora los repetidos |
| Dos postas descuentan el mismo medicamento | Se envía el **cambio** (−1), no el valor final: no se pisan |
| Poco ancho de banda | Solo baja lo **nuevo** (`cursor`); las respuestas son JSON mínimo |
| Emergencia con señal débil | Va con **prioridad 0**: sale antes que cualquier otro cambio |
| Abrir la página sin internet | `sw.js` guarda las páginas en el equipo (cuando se abre con `http://`) |

Para presentar: marque **Simular sin internet**, registre una emergencia y mire el contador *“por enviar”*; desmárquelo y la alerta llega al hospital.

## Controlador con funciones de orden superior
`ControladorEmergencias` (en `models/entidades.py` y `assets/kunaq-core.js`) decide a qué hospital derivar:
```
hospitales → filter(es_receptor) → filter(no_excluido) → filter(está_vivo)
           → map(puntuar(requisitos, origen))        # función que devuelve otra función
           → sorted(key=lambda …) → reduce(mejor)
```
Puntaje: cobertura de lo que necesita el paciente (100) + categoría MINSA + camas UCI libres − distancia − señal débil.
Si el hospital rechaza, la nube lo reasigna automáticamente al siguiente.
La versión en JavaScript permite decidir **sin internet**; la de Python decide en el servidor si la posta no tenía datos frescos.

## Estructura
```
views/index.html     Portal + registro de la PC + equipos vinculados (clave del personal)
views/admin.html     Inventario, atenciones, emergencias, búsqueda segura
views/paciente.html  Carnet del paciente (consulta la nube con DNI + PIN; no carga kunaq-core.js)
assets/              kunaq-core.js (sincronización + controlador), kunaq-core.css, logos
server/servidor_nube.py   Nube (Python estándar; SQLite o PostgreSQL; modos todo/hospital/paciente)
render.yaml / requirements.txt   Publicación en Render
tests/prueba_nube.py      Pruebas automáticas
models/              entidades.py (+ControladorEmergencias), inventario_base.py (lista de medicamentos)
scripts/semilla_db.py     Ahora también siembra los 20 medicamentos
sw.js                Páginas disponibles sin internet
```


