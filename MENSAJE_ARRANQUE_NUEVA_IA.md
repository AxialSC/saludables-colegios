# 🚀 MENSAJE DE ARRANQUE — Sistema Saludables (copiar/pegar en chat nuevo)

> Pegá TODO este bloque como primer mensaje en el chat nuevo (con la IA que sea).
> Adjuntá además estos 3 archivos: `METODOLOGIA_AXIAL.md`, `BITACORA_SALUDABLES.md` y `TRASPASO_TECNICO.md`.

---

Hola. Soy Iván Abrigo, de AXIAL SECURITY (Argentina). Vamos a continuar un proyecto que ya
está andando en producción, no arrancamos de cero. Te voy a pasar 3 documentos y necesito que
los leas antes de proponer nada:

1. **METODOLOGIA_AXIAL.md** — cómo trabajo. Respetala al pie: archivos COMPLETOS (nunca
   fragmentos), paso a paso con confirmación, POV honesto + preguntas antes de programar algo
   grande, versión a mano en config.py, migraciones de BD manuales con backup previo. Hablame
   en español argentino informal (vos), nivel principiante-intermedio.

2. **BITACORA_SALUDABLES.md** — qué es el sistema, todas las versiones hechas (v0.1 a v0.8),
   las reglas de negocio ya cerradas y el roadmap.

3. **TRASPASO_TECNICO.md** — stack, estructura de archivos, modelos, motor de precios, flujos,
   deploy y decisiones tomadas.

**Qué es el sistema (resumen):** "Saludables", un catálogo mayorista web en Flask para Juliana
Maciel, que distribuye productos saludables a colegios y kioscos de Pilar. Tiene tienda pública
(catálogo + carrito + checkout con PDF y WhatsApp) y panel admin (CRM de pedidos, catálogo,
ajustes de precios, importador de planilla, fotos). Está en producción en PythonAnywhere
(cuenta free, saludablesPilar) y el código está en GitHub (AxialSC/saludables-colegios), que es
la **fuente de verdad**.

**Cómo trabajamos el código:** yo subo a GitHub por la web (drag-drop), no uso git por consola.
Cuando vayas a tocar un archivo, **pedímelo y te paso la versión actual** desde el repo, así
trabajás sobre lo real y no inventás nada. Entregame siempre archivos completos.

**Estamos parados en la v0.8.0** (editar pedidos, ya probada y en producción). Lo próximo es la
**v0.9.0**, con estas mejoras ya acordadas (están detalladas en la bitácora):
- Botellas en el recuadro: cambiar `object-fit: cover` → `contain` + fondo blanco.
- Buscador en vivo (incremental) en la tienda pública.
- Solapa "Con alcohol / Sin alcohol" (campo nuevo `es_alcoholica`, autodetectar por palabras + corrección manual).
- Versión en el footer del login admin (te voy a pasar captura del formato que quiero).

**Antes de programar la v0.9:** dame tu POV honesto, hacé las preguntas que necesites, y
proponé el orden. No empieces a tirar código sin confirmarme. Cuando estés listo, arrancamos
de a una, paso a paso.

Si en algún momento te falta contexto que debería estar en estos documentos, avisame y lo
resolvemos (puedo volver a consultar al asistente anterior que armó el traspaso).

Empecemos. Leé los 3 documentos y decime: (a) que entendiste el estado del proyecto, y
(b) tu POV + preguntas para arrancar la v0.9.
