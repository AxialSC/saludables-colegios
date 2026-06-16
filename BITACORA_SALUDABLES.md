# 📋 BITÁCORA — Sistema Saludables (Catálogo Mayorista Pilar)

**Cliente:** Juliana Maciel · Distribuidora de saludables para colegios/kioscos de Pilar
**Desarrollador:** AXIAL SECURITY (Iván Abrigo)
**Repositorio:** github.com/AxialSC/saludables-colegios
**Producción:** saludablesPilar.pythonanywhere.com (cuenta free)
**Versión actual:** **v0.9.0** — ✅ Editar prolijo + footer con versión única + botellas en grilla
**Estado:** 9 versiones en producción · Próximo: buscador en vivo (tienda) y Con/Sin alcohol

---

## 🎯 ESTADO ACTUAL (qué funciona HOY)

**Tienda pública (sin login, en la raíz `/`):**
- Catálogo de 1654 productos importados de la planilla del mayorista
- Buscador (por Enter), filtro por rubro, vista grilla/lista
- Precios finales con IVA, con escalón por cantidad (x1 / x5 / x10)
- Fotos de productos: en **grilla** se muestran enteras (object-fit contain + fondo blanco),
  en lista igual que siempre. Productos sin foto con placeholder por rubro.
- Carrito (en sessionStorage), mínimo de compra $30.000
- Checkout: datos del cliente + CUIT validado → guarda pedido → WhatsApp + PDF

**Panel admin (El Arquitecto, en `/admin`):**
- Dashboard con métricas reales (productos, clientes, pedidos pendientes, ventas del mes)
- Catálogo: tabla con costo, costo c/IVA y precio de venta calculado
- **Pedidos (CRM):** lista, detalle, cambiar estado, tildar facturado, registrar cobros
  (efectivo/transferencia/MercadoPago/otro, admite parciales), anular (super admin),
  **editar pedido** (quitar/cambiar/agregar items con historial), re-bajar PDF
  - **Editar más prolijo (v0.9):** cada item muestra el código (chip mono). Lo que se
    agrega durante la edición queda **resaltado en verde** con etiqueta "✚ agregado",
    para ubicarlo fácil en pedidos grandes.
  - **Historial de modificaciones prolijo (v0.9):** un cambio por línea, con color
    (verde = agregado, rojo = quitado, bronce = cambio de cantidad) y código del producto.
- Ajustes: markup general, descuentos x5/x10, mínimo de compra, WhatsApp, nombre negocio
- Importar planilla (.xlsx/.csv) — solo super admin
- Fotos: carga masiva, asigna sola por nombre de archivo (codigo.jpg)

**Login (El Arquitecto):**
- Pastilla de versión "v0.9.0 — SALUDABLES" tomada de `config.py` (**fuente única**:
  login, footer del panel y footer de la tienda muestran el mismo número).
- "AXIAL SECURITY ✦ · 2026" es un link directo al WhatsApp del programador (Iván),
  con texto pre-armado "Vengo desde el Portal de Saludables…".

**Roles:**
- `ivan` → SUPER_ADMIN (Iván): importa planillas, anula pedidos, ve/hace todo
- `juliana` → ADMIN (Juliana): todo menos importar planillas y anular

---

## 📦 HISTORIAL DE VERSIONES

| Versión | Hito | ¿Tocó BD? |
|---|---|---|
| v0.1.0 | Esqueleto Flask + login "El Arquitecto" + roles | init-db |
| v0.2.0 | Importador de planilla (.xlsx/.csv) + catálogo en BD (1654 prod.) | init-db (tabla productos) |
| v0.3.0 | Tienda pública con precios + panel Ajustes + motor de precios | init-db (tabla ajustes) |
| v0.4.0 | Carrito + escalón por cantidad + mínimo $30k + fix buscador | No |
| v0.5.0 | Checkout: CUIT validado, pedido con número, WhatsApp + PDF | init-db (pedidos, items_pedido) |
| v0.6.0 | Panel de pedidos (CRM): estados, facturado, cobros, anular + IP/dispositivo | **migrar-v06** |
| v0.7.0 | Carga de fotos por código (achica solas con Pillow) | No |
| v0.8.0 | Editar pedidos (quitar/cambiar/agregar) + historial de modificaciones | **migrar-v08** |
| v0.9.0 | Editar prolijo (códigos + resaltado de agregados), historial prolijo, footer login con versión única + link WhatsApp, botellas enteras en grilla | No |

### Detalle v0.9.0 (4 pasos, ninguno tocó BD)
1. **Historial de modificaciones prolijo** (`admin.py`, `pedido_detalle.html`): un cambio por
   línea, con color y código. El split funciona también para registros viejos. De acá en
   adelante cada cambio guarda el código entre corchetes; ordenado por código (antes el orden
   era aleatorio).
2. **Footer del login + versión única** (`auth/login.html`, `config.py`): pastilla bronce con
   la versión, tomada de `APP_VERSION`. Bumpear esa sola línea actualiza login + panel + tienda.
   "AXIAL SECURITY ✦ · 2026" linkea al WhatsApp del programador.
3. **Botellas en grilla** (`cliente/catalogo.html`, `tienda.css`): `object-fit: contain` +
   fondo blanco, acotado con `:not(.lista)` para no tocar la vista lista.
4. **Resaltado de producto agregado al editar** (`pedido_editar.html`): fondo verde + etiqueta
   "✚ agregado" sobre lo que se suma durante la edición.

---

## 💰 REGLAS DE NEGOCIO VERIFICADAS

### Motor de precios — Opción 1 (MARGEN SOBRE VENTA). Confirmado por Iván.
```
venta_neta   = costo_neto / (1 - margen)
precio_final = venta_neta * (1 + IVA)        # IVA = 0.21
```
- El margen es **sobre venta**: 30% = de cada $100 que paga el cliente, $30 son ganancia.
- **Piso de seguridad:** nunca se vende por debajo del `markup_minimo` (default 20%).
- **Validación:** costo $100, markup 30% → venta neta $142,86 → **$172,86 final** (ganás $42,86).

### Escalón por cantidad (del mismo producto)
- 1 a 4 unidades → precio x1
- 5 a 9 → precio x5 (descuento `desc_x5`, default 3%)
- 10 o más → precio x10 (descuento `desc_x10`, default 5%)
- **Guard:** el descuento por volumen NUNCA hace caer el margen por debajo del mínimo (20%).

### Otras reglas
- Compra mínima del carrito: **$30.000** (con IVA). El checkout se bloquea hasta llegar.
- CUIT validado por **dígito verificador** (offline). La consulta online a ARCA queda
  pendiente para cuando se pase a cuenta paga de PythonAnywhere.
- **Defensa en profundidad:** los precios SIEMPRE se recalculan en el backend.
- Los precios quedan **congelados** (snapshot) en los items del pedido.
- Al **editar** un pedido: no puede quedar bajo $30k, ni bajar de lo ya cobrado, ni editar anulados.

---

## 👤 USUARIOS EN PRODUCCIÓN
- `ivan` — SUPER_ADMIN (contraseña ya cambiada por Iván)
- `juliana` — ADMIN (contraseña ya cambiada)
- (Las contraseñas iniciales eran Axial2026 / Saludables2026 con cambio obligatorio al primer ingreso.)

---

## 📋 PENDIENTES / ROADMAP

🟡 **Próximo — Buscador en vivo (tienda pública):**
- Buscador **incremental** (muestra resultados mientras se escribe) en la tienda pública.
- Solo frontend (o ruta JSON liviana). **No toca BD.** Bajo riesgo.

🟠 **Después — Con alcohol / Sin alcohol (TOCA BD):**
- Campo nuevo `Producto.es_alcoholica`, autodetectar por palabras clave (vino, cerveza,
  gancia, cinzano, fernet, vodka, gin, aperitivo…) + corrección manual.
- Solapa/filtro en la tienda. **Requiere migración** (`migrar-v10` con ALTER TABLE
  idempotente) + **backup previo** de la BD.

🟢 **Más adelante:**
- Seguimiento del pedido para el cliente (barra de estados en `/p/<token>`).
- Cuentas bancarias (hasta 5 CBU/CVU) asociadas a los cobros.
- "Armá tu bolsa" (combos para colegios/cumpleaños, con números CUMPLE-/COLEGIO-).
- Miniaturas de productos en el carrito.
- Validación de CUIT online contra ARCA (requiere cuenta paga de PythonAnywhere).
- Gestión de rubros (renombrar/ocultar los internos del mayorista).
- Buscador tolerante a errores de tipeo (fuzzy: que "bagio" encuentre "Baggio").
- Reportes/métricas por mes/semestre (zona, productos más vendidos).

---

## ⚙️ METODOLOGÍA ACTIVA (reglas clave aplicadas)
1. Archivos COMPLETOS para copy-paste (nunca fragmentos).
2. Paso a paso, una versión por vez, esperando confirmación.
3. POV honesto + preguntas clarificadoras antes de programar grande.
4. Bump de versión a mano en `config.py` (el footer la toma solo — ahora fuente única).
5. Migraciones de BD: comando Flask con ALTER TABLE idempotente (NO automático). Backup antes.
6. Timezone Argentina con `zoneinfo` (helpers en `app/utils/timezone.py`).
7. Deploy: Iván sube por GitHub web (drag-drop) → `git pull` en Bash → migración si toca BD → Reload.
8. Mensajes de WhatsApp sin emojis problemáticos.
9. En cada entrega, la IA indica si hay que correr Bash (`git pull`) y/o solo Reload.

_Última actualización: v0.9.0 · AXIAL SECURITY · Iván Abrigo_
