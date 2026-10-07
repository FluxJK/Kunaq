# Guía: subir Kunaq a GitHub y publicarlo en Render

Repositorio: https://github.com/FluxJK/Kunaq (hoy contiene la versión anterior: `main.py`, `src/`, `tests/`).

## 1. Subir este proyecto a GitHub

Instale [Git](https://git-scm.com/downloads). Para iniciar sesión, lo más simple es **GitHub Desktop** o `gh auth login`
(GitHub ya no acepta la contraseña de la cuenta en la terminal; se usa el navegador o un *token*).

```bash
git clone https://github.com/FluxJK/Kunaq.git
cd Kunaq
```

Elija UNA de estas dos opciones para la versión anterior:

**A) Reemplazarla** (el historial de commits se conserva en GitHub):
```bash
git rm -r src tests main.py
```
**B) Guardarla** en una carpeta `legacy/`:
```bash
mkdir legacy && git mv src tests main.py legacy/
```

Copie **todo el contenido** de este ZIP dentro de la carpeta `Kunaq` (que `render.yaml` quede junto a `index`/`views`,
en la raíz, no dentro de otra carpeta). Después:

```bash
git add -A
git commit -m "Kunaq: portales separados, PostgreSQL, cuentas del personal y cifrado"
git push origin main
```
Compruebe en GitHub que en la raíz se ven `render.yaml`, `requirements.txt`, `server/`, `views/`, `assets/`.
La pestaña **Actions** ejecutará las pruebas automáticamente en cada `push`.

> El repositorio es **público**: nunca escriba contraseñas ni llaves en los archivos. Las claves viven solo en las
> variables de entorno de Render (el proyecto ya está preparado así).

## 2. Conectar GitHub con Render

1. Cree una cuenta en https://render.com con **Sign in with GitHub**.
2. **New → Blueprint** → *Connect a repository* → autorice a Render el acceso a `FluxJK/Kunaq` → elíjalo (rama `main`).
3. Render lee `render.yaml` y muestra lo que creará: la base `kunaq-db` y los servicios `kunaq-hospital` y `kunaq-paciente`.
4. Le pedirá el valor de **`KUNAQ_ADMIN_CLAVE`**: escriba la contraseña del administrador (mínimo 8 caracteres). Anótela.
5. Pulse **Apply**. Espere a que ambos servicios queden en *Live* (unos minutos).
6. **Guarde `KUNAQ_LLAVE` y `KUNAQ_PEPPER`** (Render → *Environment Groups* → `kunaq-secretos`) en un lugar seguro.
   Si se pierden o cambian, los nombres y datos clínicos ya guardados no se podrán leer.

Desde ahora, **cada `git push` a `main` vuelve a publicar solo** (despliegue automático).

Si Render no le deja usar el nombre `kunaq-paciente` (ya ocupado), cámbielo en `render.yaml` y ajuste
`KUNAQ_URL_PACIENTE` con la dirección real; o corrija esa variable en el panel de `kunaq-hospital`.

## 3. Comprobar que funciona

1. `https://kunaq-hospital.onrender.com/api/ping` debe responder `"ok":true` y `"modo":"hospital"`.
2. Abra `https://kunaq-hospital.onrender.com/views/index.html` → entre como `admin` con su contraseña.
3. En *Cuentas del personal* cree una cuenta para cada persona. Cada equipo inicia sesión y se vincula
   (posta u hospital).
4. En el panel médico registre una atención a un paciente nuevo: aparece su **PIN de 6 dígitos**.
5. Abra `https://kunaq-paciente.onrender.com` → DNI + PIN → ve su historial.
6. Con dos equipos distintos: la posta envía una emergencia y al hospital le suena la alerta.

## 4. Límites del plan gratuito (verifique en la documentación de Render, cambian)
- La base PostgreSQL gratuita **expira a los 30 días**. Para que dure, use un plan de pago, o cree una base gratuita
  permanente (p. ej. Neon o Supabase) y pegue su cadena de conexión en la variable `DATABASE_URL` de ambos servicios.
- Los servicios gratuitos **se duermen a los 15 minutos** sin tráfico; el primer acceso tarda cerca de 1 minuto.
  Abra la página unos minutos antes de una demostración.

## 5. Problemas comunes
| Síntoma | Causa / solución |
|---|---|
| El despliegue falla con `ERROR: el modo hospital exige KUNAQ_ADMIN_CLAVE` | Falta escribir la contraseña del admin (Environment de `kunaq-hospital`). |
| `ERROR: defina KUNAQ_PEPPER y KUNAQ_LLAVE` | Los dos servicios deben tener el grupo `kunaq-secretos` enlazado. |
| La portada del hospital no muestra el enlace al paciente | Revise `KUNAQ_URL_PACIENTE`. |
| «Sesión vencida o no iniciada» | La sesión dura 24 h: vuelva a iniciar sesión; lo pendiente se conserva en el equipo y se envía al reconectar. |
| Olvidó la contraseña del admin | Cambie `KUNAQ_ADMIN_CLAVE` en Render y guarde: se aplica al reiniciar. |
| Datos que dicen `[dato no legible]` | `KUNAQ_LLAVE` distinta a la usada al guardar. |
