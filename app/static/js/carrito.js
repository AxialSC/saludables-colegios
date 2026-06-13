/* =====================================================================
   CARRITO · Saludables (cliente)
   - Vive en sessionStorage: se mantiene al navegar páginas, se borra al
     cerrar la pestaña (como pidió Iván).
   - Escalón de precio por cantidad del MISMO producto:
       1 a 4   -> precio x1
       5 a 9   -> precio x5  (-desc)
       10 o más-> precio x10 (-desc)
   - Mínimo de compra: el botón de pedido se bloquea hasta llegar.
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

  // Precio unitario segun la cantidad de ESE producto
  function precioUnit(item) {
    const q = item.qty;
    if (q >= 10) return item.p10;
    if (q >= 5) return item.p5;
    return item.p1;
  }

  // Pista para vender mas (idea de Ivan)
  function pista(item) {
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

  // --- Acciones (globales para los onclick) ---
  window.agregarAlCarrito = function (btn) {
    const d = btn.dataset;
    const cod = d.codigo;
    if (carrito[cod]) {
      carrito[cod].qty += 1;
    } else {
      carrito[cod] = {
        nombre: d.nombre,
        p1: Number(d.p1), p5: Number(d.p5), p10: Number(d.p10),
        qty: 1
      };
    }
    guardar(); render(); toast('Agregado al carrito');
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
          return '' +
            '<div class="cart-item">' +
              '<div class="ci-info">' +
                '<div class="ci-nombre">' + it.nombre + '</div>' +
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
