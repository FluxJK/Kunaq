"""Inventario base de medicamentos de Kunaq (fuente única de verdad).

Lo usan: scripts/semilla_db.py y server/servidor_nube.py.
El mismo listado vive también en assets/kunaq-core.js para que el panel
funcione SIN internet (los datos viajan con la página).

Campos: (id, nombre, categoria, stock, minimo, unidad, ubicacion)
"""

INVENTARIO_BASE = [
    (1,  "Paracetamol 500mg",           "Analgésico",        50, 20, "tabletas",    "Estante A"),
    (2,  "Amoxicilina 500mg",           "Antibiótico",        0, 20, "cápsulas",    "Estante B"),
    (3,  "Ibuprofeno 400mg",            "Antiinflamatorio",  15, 15, "tabletas",    "Estante A"),
    (4,  "Azitromicina 500mg",          "Antibiótico",       24, 12, "tabletas",    "Estante B"),
    (5,  "Ciprofloxacino 500mg",        "Antibiótico",       18, 12, "tabletas",    "Estante B"),
    (6,  "Metformina 850mg",            "Antidiabético",     60, 25, "tabletas",    "Estante C"),
    (7,  "Enalapril 10mg",              "Antihipertensivo",  35, 20, "tabletas",    "Estante C"),
    (8,  "Losartán 50mg",               "Antihipertensivo",   8, 20, "tabletas",    "Estante C"),
    (9,  "Omeprazol 20mg",              "Gastrointestinal",  40, 20, "cápsulas",    "Estante D"),
    (10, "Salbutamol 100mcg",           "Respiratorio",      12, 10, "inhaladores", "Estante D"),
    (11, "Loratadina 10mg",             "Antihistamínico",   30, 15, "tabletas",    "Estante A"),
    (12, "Sulfato ferroso 300mg",       "Suplemento",        70, 30, "tabletas",    "Estante D"),
    (13, "Ácido fólico 5mg",            "Suplemento",        45, 20, "tabletas",    "Estante D"),
    (14, "Sales de rehidratación oral", "Hidratación",       80, 30, "sobres",      "Estante E"),
    (15, "Cloruro de sodio 0.9% 1000ml","Hidratación",       25, 15, "frascos",     "Estante E"),
    (16, "Adrenalina 1mg/ml",           "Emergencia",         6,  5, "ampollas",    "Vitrina de emergencia"),
    (17, "Oxitocina 10UI",              "Emergencia",         4,  5, "ampollas",    "Refrigerador"),
    (18, "Dexametasona 4mg/ml",         "Emergencia",        14,  8, "ampollas",    "Vitrina de emergencia"),
    (19, "Diclofenaco 75mg/3ml",        "Analgésico",        20, 10, "ampollas",    "Estante A"),
    (20, "Albendazol 400mg",            "Antiparasitario",   40, 15, "tabletas",    "Estante D"),
]
