"""Pruebas automáticas de la nube.  python tests/prueba_nube.py sqlite   |   python tests/prueba_nube.py pg  (pg requiere: pip install pgserver)"""
import os, sys, json, hashlib, time, threading, urllib.request, urllib.error
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["KUNAQ_PEPPER"]="pepper-de-prueba"; os.environ["KUNAQ_TOKEN"]="tok123"; os.environ["KUNAQ_SEMILLA_DEMO"]="1"
modo_bd = sys.argv[1]
url = ""
if modo_bd == "pg":
    import pgserver, tempfile
    srv = pgserver.get_server(tempfile.mkdtemp())
    url = srv.get_uri(); print("PG URI:", url)
import importlib; sn = importlib.import_module("server.servidor_nube")
sn.TOKEN="tok123"; sn.PEPPER="pepper-de-prueba"
sn.LLAVE="llave-de-prueba"; sn.ADMIN_USUARIO="admin"; sn.ADMIN_CLAVE="Admin#2026-ok"
if modo_bd=="sqlite":
    import tempfile; ruta=tempfile.mktemp(suffix=".db"); bd=sn.BD("", ruta)
else: bd=sn.BD(url)
sha=lambda t: hashlib.sha256(t.encode()).hexdigest()
def levantar(modo, puerto, nube):
    h = type("M",(sn.Manejador,),{"modo":modo,"cors":"","nube":nube})
    s = sn.ThreadingHTTPServer(("127.0.0.1",puerto),h); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
nube_h = sn.Nube(bd,"hospital"); nube_p = sn.Nube(bd,"paciente")   # dos "servicios", misma BD
levantar("hospital",9101,nube_h); levantar("paciente",9102,nube_p)
def req(puerto, ruta, datos=None, token=None):
    r = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}", data=json.dumps(datos).encode() if datos is not None else None,
        headers={"Content-Type":"application/json", **({"X-Kunaq-Token":token} if token else {})})
    try:
        with urllib.request.urlopen(r) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
J=lambda b: json.loads(b)
ok=lambda c,m: print(("OK   " if c else "FALLA"), m) or (c or sys.exit(1))

# --- separación de portales
ok(req(9102,"/views/paciente.html")[0]==200, "paciente: sirve paciente.html")
ok(req(9102,"/views/admin.html")[0]==404, "paciente: NO sirve admin.html")
ok(req(9102,"/assets/kunaq-core.js")[0]==404, "paciente: NO sirve kunaq-core.js")
ok(req(9102,"/assets/kunaq-logo.png")[0]==200, "paciente: sí sirve logos")
ok(req(9102,"/api/sync/pull?dispositivo=x&cursor=0",token="tok123")[0]==404, "paciente: NO expone /api/sync")
ok(req(9101,"/views/paciente.html")[0]==404, "hospital: NO sirve paciente.html")
ok(req(9101,"/views/admin.html")[0]==200, "hospital: sirve admin.html")
ok(req(9101,"/api/paciente/consulta",{"dni":"70123456","pin":"1234"})[0]==404, "hospital: NO expone consulta de paciente")
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0")[0]==401, "hospital: sin token → 401")
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0",token="tok123")[0]==200, "hospital: con token → 200")

# --- alta de paciente y atención desde el hospital, consulta desde el portal
dni="45678912"; h=sha(dni)
ops=[{"id":"op-1","tipo":"PACIENTE","prioridad":5,"datos":{"dni_hash":h,"nombre":"Rosa Mamani","pin":"4821"}},
     {"id":"op-2","tipo":"ATENCION","prioridad":5,"datos":{"id":"A-1","dni_hash":h,"nombre":"Rosa Mamani","fecha":"07/10/2026","hospital":"Posta Laredo","datos_cifrados":"QUJD"}},
     {"id":"op-3","tipo":"PACIENTE","datos":{"dni_hash":"malo","pin":"1"}}]
c,b=req(9101,"/api/sync/push",{"dispositivo":"d1","ops":ops},"tok123"); r=J(b)
ok(c==200 and r["aceptadas"]==["op-1","op-2"] and len(r["rechazadas"])==1, f"push: 2 aceptadas, 1 rechazada ({r['rechazadas'][0]['error']})")
c,b=req(9101,"/api/sync/push",{"dispositivo":"d1","ops":ops[:2]},"tok123")
ok(J(b)["aceptadas"]==["op-1","op-2"], "push repetido es idempotente")
ok(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"4821"})[0]==200, "paciente: DNI+PIN correctos → entra")
r=J(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"4821"})[1]); ok(r["nombre"]=="Rosa Mamani" and len(r["atenciones"])==1, "paciente: ve SOLO su historial")
ok(req(9102,"/api/paciente/consulta",{"dni":"70123456","pin":"1234"})[0]==200, "paciente demo (semilla) entra")
ok(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"0000"})[0]==401, "PIN incorrecto → 401")
ok(req(9102,"/api/paciente/consulta",{"dni":"11111111","pin":"4821"})[0]==401, "DNI inexistente → 401")
codes=[req(9102,"/api/paciente/consulta",{"dni":dni,"pin":f"{i:04d}"})[0] for i in range(1,8)]
ok(429 in codes, f"fuerza bruta bloqueada → {codes}")
ok(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"4821"})[0]==429, "ni con el PIN correcto mientras está bloqueado")
# restablecer PIN desde hospital desbloquea
req(9101,"/api/sync/push",{"dispositivo":"d1","ops":[{"id":"op-9","tipo":"PACIENTE","datos":{"dni_hash":h,"nombre":"Rosa Mamani","pin":"7777","reset":True}}]},"tok123")
nube_p.limitador.limpiar("dni:"+nube_p._clave_dni(h))
ok(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"7777"})[0]==200, "PIN restablecido por el personal funciona")
ok(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"4821"})[0]==401, "el PIN viejo ya no sirve")
# búsqueda del personal
c,b=req(9101,f"/api/atenciones?dni_hash={h}",token="tok123"); ok(len(J(b)["atenciones"])==1, "personal busca por dni_hash")
# el DNI no está en la BD
filas=" ".join(str(dict(r)) for r in bd.execute("SELECT * FROM atenciones").fetchall()+bd.execute("SELECT * FROM pacientes").fetchall())
ok(h not in filas and dni not in filas, "la BD no contiene ni el DNI ni su SHA-256 simple")

# --- emergencias, stock, rechazo con savepoint
disp=lambda i,n,t,caps,uci:{"id":i,"nombre":n,"tipo":t,"categoria":"II-1","capacidades":caps,"camas_uci":uci,"lat":-8.1,"lng":-79.0}
req(9101,"/api/sync/push",{"dispositivo":"H1","ops":[{"id":"o-a","tipo":"DISPOSITIVO","datos":disp("H1","Hospital A","HOSPITAL",["UCI","VENTILADOR"],3)},
    {"id":"o-b","tipo":"DISPOSITIVO","datos":disp("H2","Hospital B","HOSPITAL",["UCI"],1)},{"id":"o-c","tipo":"DISPOSITIVO","datos":disp("P1","Posta","POSTA",[],0)}]},"tok123")
req(9101,"/api/sync/pull?dispositivo=H1&cursor=0",token="tok123"); req(9101,"/api/sync/pull?dispositivo=H2&cursor=0",token="tok123")
req(9101,"/api/sync/push",{"dispositivo":"P1","ops":[{"id":"o-e","tipo":"EMERGENCIA","datos":{"id":"E-1","origen_id":"P1","origen_nombre":"Posta","prioridad":1,"requisitos":["UCI","VENTILADOR"],"datos_cifrados":"x"}}]},"tok123")
r=J(req(9101,"/api/sync/pull?dispositivo=H1&cursor=0",token="tok123")[1]); a=[x for x in r["alertas"] if x["id"]=="E-1"][0]
ok(a["destino_id"]=="H1" and a["estado"]=="ENTREGADA", "emergencia llega al hospital mejor (H1) y queda ENTREGADA")
req(9101,"/api/sync/push",{"dispositivo":"H1","ops":[{"id":"o-r","tipo":"ALERTA_ESTADO","datos":{"id":"E-1","estado":"RECHAZADA","motivo":"sin cama"}}]},"tok123")
r=J(req(9101,"/api/sync/pull?dispositivo=P1&cursor=0",token="tok123")[1]); a=[x for x in r["alertas"] if x["id"]=="E-1"][0]
ok(a["destino_id"]=="H2", "al rechazar, se reasigna a H2")
c,b=req(9101,"/api/sync/push",{"dispositivo":"P1","ops":[{"id":"o-bad","tipo":"ALERTA_ESTADO","datos":{"id":"NO-EXISTE","estado":"CONFIRMADA"}},
    {"id":"o-s","tipo":"STOCK_DELTA","datos":{"id":1,"delta":-5}}]},"tok123"); r=J(b)
ok(r["aceptadas"]==["o-s"] and r["rechazadas"][0]["id"]=="o-bad", "una operación mala no frena a las demás (savepoint)")
stock0=bd.execute("SELECT stock FROM inventario WHERE id=1").fetchone()[0]
req(9101,"/api/sync/push",{"dispositivo":"P1","ops":[{"id":"o-s2","tipo":"STOCK_DELTA","datos":{"id":1,"delta":-99999}}]},"tok123")
ok(bd.execute("SELECT stock FROM inventario WHERE id=1").fetchone()[0]==0, f"el stock nunca baja de 0 (era {stock0})")

# --- cifrado en reposo (Fernet) y PIN de 6 dígitos
raw=lambda sql: bd.execute(sql).fetchall()
at=raw("SELECT nombre,datos_cifrados FROM atenciones WHERE id='A-1'")[0]
ok(at["datos_cifrados"].startswith("f1:") and "QUJD" not in at["datos_cifrados"] and "Rosa" not in at["nombre"], "BD: atención y nombre guardados cifrados (Fernet)")
ok(all("Rosa" not in r["nombre"] for r in raw("SELECT nombre FROM pacientes")), "BD: nombre del paciente cifrado")
ok(raw("SELECT datos_cifrados FROM alertas WHERE id='E-1'")[0]["datos_cifrados"].startswith("f1:"), "BD: datos de la emergencia cifrados")
r=J(req(9102,"/api/paciente/consulta",{"dni":dni,"pin":"7777"})[1]); ok(r["atenciones"][0]["datos_cifrados"]=="QUJD" and r["nombre"]=="Rosa Mamani", "el portal devuelve los datos ya descifrados")
a=[x for x in J(req(9101,"/api/sync/pull?dispositivo=H2&cursor=0",token="tok123")[1])["alertas"] if x["id"]=="E-1"][0]; ok(a["datos_cifrados"]=="x", "la alerta llega descifrada al hospital")
req(9101,"/api/sync/push",{"dispositivo":"d1","ops":[{"id":"op-p6","tipo":"PACIENTE","datos":{"dni_hash":sha("33445566"),"nombre":"Luis","pin":"482913"}}]},"tok123")
ok(req(9102,"/api/paciente/consulta",{"dni":"33445566","pin":"482913"})[0]==200, "PIN de 6 dígitos funciona")

# --- cuentas del personal
ok(J(req(9101,"/api/ping")[1])["requiere_login"] is True, "hospital: ping indica que exige inicio de sesión")
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0")[0]==401, "sin sesión → 401")
ok(req(9101,"/api/personal/login",{"usuario":"admin","clave":"mala"})[0]==401, "login con clave mala → 401")
c,b=req(9101,"/api/personal/login",{"usuario":"admin","clave":"Admin#2026-ok"}); L=J(b); TA=L["token"]
ok(c==200 and L["rol"]=="admin" and len(TA)>30, "login del administrador")
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0",token=TA)[0]==200, "la sesión sirve para sincronizar")
ok(req(9101,"/api/personal/crear",{"usuario":"enf1","nombre":"Enf Uno","clave":"corta","rol":"personal"},TA)[0]==400, "contraseña corta rechazada")
ok(req(9101,"/api/personal/crear",{"usuario":"enf1","nombre":"Enf Uno","clave":"claveSegura1","rol":"personal"},TA)[0]==200, "admin crea cuenta de personal")
TP=J(req(9101,"/api/personal/login",{"usuario":"enf1","clave":"claveSegura1"})[1])["token"]
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0",token=TP)[0]==200, "el personal inicia sesión y sincroniza")
ok(req(9101,"/api/personal/crear",{"usuario":"x1x","nombre":"X","clave":"claveSegura1"},TP)[0]==403, "el personal NO puede crear cuentas")
ok(req(9101,"/api/personal/lista",token=TP)[0]==403 and len(J(req(9101,"/api/personal/lista",token=TA)[1])["usuarios"])==2, "solo el admin lista cuentas")
ok(req(9101,"/api/personal/desactivar",{"usuario":"admin"},TA)[0]==400, "no puede desactivar su propia cuenta")
req(9101,"/api/personal/desactivar",{"usuario":"enf1"},TA)
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0",token=TP)[0]==401, "cuenta desactivada → su sesión deja de valer")
ok(req(9101,"/api/personal/login",{"usuario":"enf1","clave":"claveSegura1"})[0]==401, "cuenta desactivada no puede entrar")
req(9101,"/api/personal/logout",{},TA)
ok(req(9101,"/api/sync/pull?dispositivo=x&cursor=0",token=TA)[0]==401, "cerrar sesión invalida el token")
ok(req(9102,"/api/personal/login",{"usuario":"admin","clave":"Admin#2026-ok"})[0]==404, "el portal del paciente no tiene login de personal")
cod=[req(9101,"/api/personal/login",{"usuario":"admin","clave":f"mala{i}"})[0] for i in range(7)]
ok(429 in cod, f"login: fuerza bruta bloqueada → {cod}")
ok("Admin#2026-ok" not in " ".join(str(dict(r)) for r in raw("SELECT * FROM usuarios")), "BD: la contraseña no se guarda en claro")
print("\nTODO OK con", modo_bd)
