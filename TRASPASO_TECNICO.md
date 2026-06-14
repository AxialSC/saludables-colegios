# 🛠️ TRASPASO TÉCNICO — Sistema Saludables

Documento para que cualquier IA o desarrollador continúe el proyecto desde cero.
Leer junto a `METODOLOGIA_AXIAL.md` y `BITACORA_SALUDABLES.md`.

---

## 1. STACK
- **Backend:** Flask 3 (Application Factory) + SQLAlchemy + Flask-Login + Flask-Bcrypt + Flask-WTF (CSRF)
- **BD:** SQLite (`instance/saludables.db`)
- **PDF:** ReportLab · **Excel:** openpyxl · **Imágenes:** Pillow
- **Frontend:** Jinja2 + CSS vanilla + JS vanilla (sin frameworks, sin CDN)
- **Hosting:** PythonAnywhere free, cuenta `saludablesPilar` (URL: saludablesPilar.pythonanywhere.com)
- **Repo:** github.com/AxialSC/saludables-colegios (Iván sube por la web GUI, drag-drop)
- **Python:** 3.13 · WSGI manual (ver `wsgi_pythonanywhere.py`)

⚠️ **Límite importante:** la cuenta free de PythonAnywhere NO permite llamadas a APIs
externas (whitelist). Por eso la validación de CUIT es offline (dígito verificador) y la
consulta a ARCA queda pendiente para cuenta paga.

---

## 2. ESTRUCTURA DE ARCHIVOS
```
saludables-colegios/
├── config.py                  # Config + APP_VERSION (bump manual)
├── run.py                     # runner local
├── wsgi_pythonanywhere.py     # referencia WSGI (no se sube)
├── requirements.txt
├── instance/saludables.db     # BD (no en git)
└── app/
    ├── __init__.py            # Factory: extensiones, blueprints, filtro |pesos, errores
    ├── extensions.py          # db, bcrypt, login_manager, csrf
    ├── models.py              # TODOS los modelos (ver sección 3)
    ├── pricing.py             # Motor de precios (Opción 1 + escalón + piso)
    ├── services.py            # aplicar_importacion (upsert de productos)
    ├── pdf_pedido.py          # PDF del pedido (ReportLab)
    ├── auth.py                # login / logout / cambiar-password
    ├── admin.py               # TODO el panel: dashboard, pedidos(CRM), catalogo, ajustes, importar, fotos
    ├── cliente.py             # Tienda pública: catalogo, checkout, confirmacion, pdf
    ├── cli.py                 # init-db, seed-data, import-planilla, migrar-v06, migrar-v08
    ├── utils/
    │   ├── timezone.py        # hora Argentina + filtros Jinja (|ar_datetime, |ar_fecha)
    │   ├── decorators.py      # @admin_requerido, @super_admin_requerido
    │   ├── import_planilla.py # parser robusto del Excel/CSV del mayorista
    │   └── validaciones.py    # validar_cuit (dígito verificador)
    ├── templates/
    │   ├── base.html, auth/, errors/
    │   ├── admin/             # base_admin (sidebar) + dashboard/catalogo/ajustes/importar/fotos/pedidos/pedido_detalle/pedido_editar
    │   └── cliente/           # catalogo / checkout / confirmacion
    └── static/
        ├── css/app.css        # El Arquitecto (admin)
        ├── css/tienda.css     # Tienda pública
        ├── js/carrito.js      # Carrito (sessionStorage)
        └── img/productos/     # Fotos subidas (no en git, nombradas codigo.jpg)
```

---

## 3. MODELOS (app/models.py)
- **Usuario** (UserMixin): usuario, nombre, password_hash, rol, activo, debe_cambiar_password.
  - `Rol`: SUPER_ADMIN / ADMIN / REVENDEDORA. Props: `es_super_admin`, `es_admin`.
- **Producto:** codigo (str, unique), nombre, rubro, costo_neto (Numeric s/IVA),
  marca, **imagen** (nombre de archivo), margen_individual, destacado, activo, en_ultima_lista.
  Prop `costo_con_iva`. (IVA = 0.21 constante en el módulo.)
- **Ajustes** (singleton, `get_ajustes()`): markup_general, markup_minimo, desc_x5, desc_x10,
  minimo_compra, whatsapp, nombre_negocio.
- **Pedido:** numero (WEB-00001), **token** (público no adivinable), origen (WEB/CUMPLE/COLEGIO),
  estado, datos del cliente (nombre, apellido, cuit, whatsapp, email, direccion, zona, observaciones),
  total, facturado(+_en), ip_origen, dispositivo, anulado_por/_en/_motivo, modificado_en.
  Props: `total_cobrado`, `saldo`, `esta_cobrado`, `esta_anulado`, `cliente_completo`.
  - `EstadoPedido`: PENDIENTE / CONFIRMADO / ENTREGADO / ANULADO.
- **ItemPedido:** snapshot (codigo, nombre, cantidad, precio_unitario, subtotal).
- **Cobro:** forma_pago (`FormaPago`: EFECTIVO/TRANSFERENCIA/MERCADOPAGO/OTRO), monto, nota, registrado_por.
- **ModificacionPedido:** descripcion, total_anterior, total_nuevo, hecho_por (historial de ediciones).

---

## 4. MOTOR DE PRECIOS (app/pricing.py)
```python
margen_efectivo(producto, ajustes)  # individual si tiene, sino general; nunca < mínimo
precio_final(producto, ajustes, escala)  # escala = 'x1'/'x5'/'x10'; aplica desc + guard del piso
precio_por_cantidad(producto, ajustes, cantidad)  # mapea cantidad -> escala (1-4/5-9/10+)
precios(producto, ajustes)  # dict {x1, x5, x10, margen}
```
Fórmula: `venta_neta = costo_neto / (1 - margen/100)` ; `final = venta_neta * 1.21`.

---

## 5. FLUJOS CLAVE
- **Importar planilla:** `/admin/importar` (super admin). Parser detecta solo las columnas
  (Rubro/Código/Nombre/Pcio) aunque haya columna vacía o encabezado corrido. Upsert por código:
  actualiza precio de existentes, agrega nuevos, marca `en_ultima_lista`. No borra nada.
  Formato real: col A vacía, encabezado fila 3, precios "1.053,233" (punto=miles, coma=decimal).
- **Carrito (cliente):** `static/js/carrito.js`, en sessionStorage (se borra al cerrar pestaña).
  El botón "Hacer el pedido" lleva a `/checkout`.
- **Checkout:** valida CUIT + mínimo + datos, RECALCULA precios en backend, guarda Pedido + items,
  redirige a `/p/<token>` (confirmación con WhatsApp + PDF). Captura IP y dispositivo.
- **CRM pedidos:** `/admin/pedidos`. Detalle con estado, facturado, cobros, anular, editar, PDF.
- **Editar pedido:** `/admin/pedidos/<id>/editar`. Buscador AJAX `/admin/productos/buscar`.
  Recalcula en backend, valida (mínimo, cobros, no anulado), guarda ModificacionPedido.
- **Fotos:** `/admin/fotos`. Sube varias, asigna por nombre (codigo.jpg), achica a 600px con Pillow.

---

## 6. DEPLOY (PythonAnywhere)
```bash
cd saludables-colegios
cp instance/saludables.db instance/saludables_backup.db   # SIEMPRE backup si toca BD
git pull
pip3 install --user -r requirements.txt                   # si hay deps nuevas
# Si la versión tiene migración, correr el comando que corresponda:
flask --app run migrar-v06     # (ya aplicada)
flask --app run migrar-v08     # (ya aplicada)
# Reload desde la pestaña Web
```
**Comandos CLI:** `init-db`, `seed-data`, `import-planilla <ruta>`, `migrar-v06`, `migrar-v08`.

⚠️ `init-db` (create_all) crea tablas faltantes pero **NO agrega columnas** a tablas existentes.
Por eso cada cambio de columnas en producción necesita un comando `migrar-vXX` con ALTER TABLE
idempotente (patrón ya establecido en cli.py — copiar ese patrón para futuras migraciones).

---

## 7. IDENTIDAD VISUAL
- **Admin "El Arquitecto":** carbón #1A1A1A, bronce #8B6F47, crema #F4F1EC (en app.css).
- **Tienda pública:** fresca, verde #2F6F4E + bronce para precios, mobile-first (tienda.css).
- Moneda: filtro Jinja `|pesos` → formato argentino ($1.820,59).

---

## 8. DECISIONES IMPORTANTES YA TOMADAS (no volver a discutir)
- Markup = **Opción 1** (margen sobre venta), piso 20%, IVA al final.
- Carrito client-side en sessionStorage (se cae al cerrar = aceptado).
- Pedidos NO se borran: se anulan (auditado).
- Precios siempre recalculados en backend (defensa en profundidad).
- PDF SIN fotos (es un comprobante serio). Miniaturas solo en el carrito (futuro).
- CUIT offline ahora; ARCA online cuando haya cuenta paga.
