/* =====================================================================
   CARRITO · Saludables (cliente)
   - Vive en sessionStorage: se mantiene al navegar páginas, se borra al
     cerrar la pestaña (como pidió Iván).
   - Escalón de precio por cantidad del MISMO producto:
       1 a 4   -> precio x1
       5 a 9   -> precio x5  (-desc)
       10 o más-> precio x10 (-desc)
   - v0.12: si el producto está en OFERTA, usa el precio de oferta (plano,
     sin escalón). El precio igual se revalida en el backend al confirmar.
   - Mínimo de compra: el botón de pedido se bloquea hasta llegar.

   v0.22.1 -> MICRO-FEEDBACK TÁCTIL al agregar.
     En una computadora, el :hover del botón ya te confirma que estás tocando
     algo. En un CELULAR NO EXISTE EL HOVER: el usuario toca "Agregar" y, si no
     mira el numerito del carrito allá abajo, no tiene NINGUNA señal de que el
     toque funcionó -> vuelve a tocar -> agrega el producto dos veces.
     Este "latido" de 300ms (clase .t-add-ok, ya definida en tienda.css) es la
     ÚNICA confirmación visual inmediata que tiene alguien desde el teléfono.
     Es una línea de código y evita pedidos duplicados.
   ===================================================================== */
(function () {
  const KEY = 'carrito_saludables_v1';
  const MIN = (window.SALU && window.SALU.minimo) ? Number(window.SALU.minimo) : 0;

  let carrito = leer();

  function leer() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; }
    catch (e) { return {}; }
  }
  function guardar() { sessionStorage.setItem(KEY, JSON.stringify(carrito)); }

  function fmt(v) {
    return '$' + Number(v).toLocaleString('es-AR',
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Precio unitario segun la cantidad de ESE producto (o precio de oferta, plano)
  function precioUnit(item) {
    if (item.of) return item.of;     // precio de oferta: plano, sin escalon
    const q = item.qty;
    if (q >= 10) return item.p10;
    if (q >= 5) return item.p5;
    return item.p1;
  }

  // Pista para vender mas (idea de Ivan)
  function pista(item) {
    if (item.of) return '🏷️ Precio de oferta aplicado';
    const q = item.qty;
    if (q < 5)  return 'Sumá ' + (5 - q) + ' y baja a ' + fmt(item.p5) + ' c/u';
    if (q < 10) return 'Sumá ' + (10 - q) + ' y baja a ' + fmt(item.p10) + ' c/u';
    return '¡Mejor precio aplicado!';
  }

  function totales() {
    let total = 0, items = 0;
    for (const cod in carrito) {
      const it = carrito[cod];
      total += precioUnit(it) * it.qty;
      items += it.qty;
    }
    return { total, items };
  }

  // v0.22.1 · El "latido" del boton al agregar (ver nota de arriba).
  // OJO: solo agrega y saca una CLASE. NUNCA toca el contenido del boton, para
  // no borrarle el icono SVG que trae desde _grid.html.
  function latido(btn) {
    if (!btn || !btn.classList) return;
    btn.classList.add('t-add-ok');
    setTimeout(function () { btn.classList.remove('t-add-ok'); }, 300);
  }

  // --- Acciones (globales para los onclick) ---
  window.agregarAlCarrito = function (btn) {
    const d = btn.dataset;
    const cod = d.codigo;
    const esOferta = d.oferta === '1';
    if (carrito[cod]) {
      carrito[cod].qty += 1;
    } else {
      carrito[cod] = {
        nombre: d.nombre,
        p1: Number(d.p1), p5: Number(d.p5), p10: Number(d.p10),
        of: esOferta ? Number(d.poferta) : null,
        qty: 1
      };
    }
    guardar(); render(); latido(btn);
    toast(esOferta ? '🏷️ Oferta agregada al carrito' : 'Agregado al carrito');
  };

  window.cambiarCant = function (cod, delta) {
    if (!carrito[cod]) return;
    carrito[cod].qty += delta;
    if (carrito[cod].qty <= 0) delete carrito[cod];
    guardar(); render();
  };

  window.quitarItem = function (cod) {
    delete carrito[cod]; guardar(); render();
  };

  window.abrirCarrito = function () {
    document.getElementById('cart-modal').classList.add('abierto');
  };
  window.cerrarCarrito = function () {
    document.getElementById('cart-modal').classList.remove('abierto');
  };

  window.intentarPedido = function () {
    const { total } = totales();
    if (total < MIN) return;
    window.location.href = '/checkout';
  };

  // --- Toast ---
  let toastTimer = null;
  function toast(msg) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('visible'), 2200);
  }

  // --- Render ---
  function render() {
    const { total, items } = totales();

    // Boton flotante
    const badge = document.getElementById('cart-badge');
    const fabTotal = document.getElementById('cart-fab-total');
    if (badge) {
      badge.textContent = items;
      badge.style.display = items > 0 ? 'flex' : 'none';
    }
    if (fabTotal) fabTotal.textContent = fmt(total);

    // Lista del modal
    const cont = document.getElementById('cart-items');
    if (cont) {
      const cods = Object.keys(carrito);
      if (cods.length === 0) {
        cont.innerHTML = '<p class="cart-vacio">Tu carrito está vacío. ¡Agregá productos!</p>';
      } else {
        cont.innerHTML = cods.map(function (cod) {
          const it = carrito[cod];
          const pu = precioUnit(it);
          const ofTag = it.of ? '<span class="ci-oftag">OFERTA</span> ' : '';
          return '' +
            '<div class="cart-item">' +
              '<div class="ci-info">' +
                '<div class="ci-nombre">' + ofTag + it.nombre + '</div>' +
                '<div class="ci-precio">' + fmt(pu) + ' c/u · subtotal ' + fmt(pu * it.qty) + '</div>' +
                '<div class="ci-pista">' + pista(it) + '</div>' +
              '</div>' +
              '<div class="ci-controls">' +
                '<button onclick="cambiarCant(\'' + cod + '\',-1)">−</button>' +
                '<span>' + it.qty + '</span>' +
                '<button onclick="cambiarCant(\'' + cod + '\',1)">+</button>' +
                '<button class="ci-quitar" onclick="quitarItem(\'' + cod + '\')">✕</button>' +
              '</div>' +
            '</div>';
        }).join('');
      }
    }

    // Total + estado del minimo
    const totalEl = document.getElementById('cart-total');
    if (totalEl) totalEl.textContent = fmt(total);

    const estado = document.getElementById('cart-estado');
    const btnPedir = document.getElementById('cart-pedir');
    if (estado && btnPedir) {
      if (items === 0) {
        estado.textContent = '';
        btnPedir.disabled = true;
        btnPedir.textContent = 'Pedido mínimo ' + fmt(MIN);
      } else if (total < MIN) {
        const falta = MIN - total;
        estado.innerHTML = 'Te faltan <b>' + fmt(falta) + '</b> para el pedido mínimo';
        estado.className = 'cart-estado falta';
        btnPedir.disabled = true;
        btnPedir.textContent = 'Falta para el mínimo';
      } else {
        estado.innerHTML = '¡Llegaste al mínimo! Ya podés pedir.';
        estado.className = 'cart-estado ok';
        btnPedir.disabled = false;
        btnPedir.textContent = 'Hacer el pedido';
      }
    }
  }

  document.addEventListener('DOMContentLoaded', render);
})();
