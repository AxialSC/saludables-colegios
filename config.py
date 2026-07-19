"""
config.py — Configuracion del Sistema Saludables (Catalogo Mayorista)
AXIAL SECURITY · Ivan Abrigo

La version se cambia A MANO aca (regla AXIAL). El footer la toma automaticamente
desde el context_processor en app/__init__.py.

v0.18.3 -> C2: alta de suscriptores (form publico + panel admin + export CSV).
v0.19.0 -> Login rediseñado, estilo "El Arquitecto" (referencia: portal Lofty).
v0.19.1 -> Food Cost real: lector de facturas PDF de Torres.
v0.19.3 -> Fixes visuales: login sin scroll, sidebar auto-ajustable.
v0.20.0 -> HISTORIAL DE PRECIOS + Dashboard con alertas.
v0.20.1 -> Auto-logout por inactividad (con barra de sesion en el sidebar).
v0.21.0 -> E0: Fix CSRF + auto-logout REAL + timer en el portal + MARGEN_CASA_MINIMO.
v0.22.0 -> E1: Rediseño de la tienda (header 3 zonas + navbar), banners en grilla
               (3 bugs corregidos), assets de marca, placeholder de producto y
               sidebar del panel agrupado por secciones.
v0.22.1 -> E1 (cierre): favicon en todo el sistema, boton Agregar con icono SVG
               (el emoji se pintaba distinto en cada telefono) y micro-feedback
               tactil al agregar al carrito.
v0.23.0 -> E2: CIMIENTO DEL FRENTE E. Migracion de la base: la venta de la
               revendedora, el circuito de aprobacion de Juliana y el snapshot
               de comision congelado. NO agrega pantallas todavia: solo la
               estructura, hecha UNA SOLA VEZ y bien.
v0.24.0 -> E3: EL PORTAL DE VENTAS DE LA REVENDEDORA. Catalogo con buscador,
               carrito con minimo de $50.000 NETOS, piso de ganancia por escalon
               y envio a la bandeja de aprobacion de Juliana.
v0.25.0 -> E4: LA BANDEJA DE APROBACION DE JULIANA. Aprobar / editar / rechazar
               las ventas de revendedora, con la comision congelandose al aprobar
               y el piso del 6% blindado tambien al editar. + 3 fixes (cobro
               deshabilitado explicado, precio elastico, telefono clickeable).
v0.26.0 -> E5: MOTOR DE NIVELES automatico (permanencia mixta, sin cron).
v0.26.1 -> E5-fix: import faltante en comisiones.py (500 en el portal).
v0.27.0 -> E6: PRESUPUESTOS (Cumpleaños / Comercios) EN EL PORTAL DE LA
               REVENDEDORA. Arma un presupuesto para su cliente con SU piso,
               genera un PDF con SU contacto, y con "Convertir en pedido" lo manda
               a la misma bandeja de aprobacion de Juliana (circuito E4). Cumple
               sin minimo; comercio con minimo de $50k netos. Al convertir un
               cumple, las bolsas se multiplican y el candado del 6% se revalida
               sobre el total final. SIN migracion (los campos ya existian de E2).
v0.28.0 -> P1: ALERTAS OPERATIVAS EN EL DASHBOARD. Al entrar, Juliana ve lo que
               espera accion: ventas de revendedora por aprobar (con recordatorio
               de editarlas SOLO desde Aprobaciones), pedidos web sin procesar,
               cobros pendientes (aprobados con saldo) y suscriptores nuevos de la
               semana. Todo se calcula al consultar (sin cron). SIN migracion.
v0.29.0 -> P2: BOX ESTILO CARREFOUR EN LA TIENDA. El boton "Agregar" al tocarlo
               se transforma en un stepper (- cant +) con la cantidad de ese
               producto; cambia de color (verde marca -> verde interfaz, rojo en
               ofertas). Sincroniza con el carrito y se re-sincroniza tras cada
               busqueda en vivo (observer, sin tocar catalogo.html). SIN migracion.
v0.30.0 -> P3: COBRO BLINDADO. El cobro de un pedido se habilita SOLO cuando esta
               CONFIRMADO o ENTREGADO. En PENDIENTE el form se reemplaza por un
               cartel ("primero confirma el pedido") y el backend rechaza el POST
               igual (defensa en profundidad). Evita cobrar algo no confirmado.
               SIN migracion.
v0.31.0 -> P4: WHATSAPP UNIFICADO EN LA TIENDA. Se saca el boton WhatsApp
               DUPLICADO del header (hacia lo mismo que el flotante) y el flotante
               pasa a ser un WIDGET: boton redondo verde + globo de bienvenida
               ("Somos <negocio> · ¿Necesitas ayuda?") que se abre al pasar el
               mouse (PC) o al tocarlo (celular), con auto-apertura una vez al
               entrar y una X para cerrarlo. BONUS: la pastilla "Ofertas" del
               navbar se pone ROJA cuando esta activa (antes de tocarla, amarilla).
               Solo tienda: catalogo.html + tienda.css. SIN migracion.
v0.32.0 -> P5: MENU DE CATEGORIAS ESTILO GONDOLA. El navbar horizontal verde se
               reemplaza por un MOSAICO de 8 azulejos (linea de 4) con icono +
               etiqueta: Todo, Golosinas, Galletitas, Comestibles, Bebidas, Sin
               alcohol, Con alcohol, Saludables. Debajo, la barra de OFERTAS a lo
               ancho en 2 tonos (amarilla -> roja cuando esta activa). Cada azulejo
               usa el filtro que YA existia en el backend (?rubro= para los rubros
               de Torres, ?cat= para las solapas): NO hubo que tocar cliente.py ni
               migrar. Los rubros del long-tail (Varios, Limpieza, Perfumeria, etc.)
               siguen accesibles en el desplegable "Todos los rubros". Iconos SVG
               inline (stroke=currentColor) para que se vean bien en el azulejo
               activo. Solo tienda: catalogo.html + tienda.css. SIN migracion.
v0.33.0 -> P5-fix: CADA MENU EN SU LUGAR (PC vs CELULAR). En v0.32 el mosaico se
               habia comido tambien el menu de la COMPU, y no era la idea: el
               mosaico es una solucion de ESPACIO, y en una PC el espacio sobra.
               Ahora:
                 · COMPU  -> NAVBAR horizontal REDISEÑADO: las 8 categorias a la
                   vista repartidas a lo ancho, cada una con su icono chico
                   (Todo, Golosinas, Galletitas, Comestibles, Bebidas, Sin
                   alcohol, Con alcohol, Saludables) + pastilla Ofertas a la
                   derecha con el contador, en 2 tonos (amarilla -> roja).
                 · CELULAR -> el MOSAICO de azulejos de v0.32 (linea de 4).
               El corte es en 640px: se muestra uno u otro, nunca los dos
               (clases .solo-pc / .solo-cel). Ademas se limpio una regla vieja
               duplicada que hacia que la pastilla Ofertas ROJA volviera a
               amarillo al pasarle el mouse. Solo tienda: catalogo.html +
               tienda.css. SIN migracion.
v0.34.0 -> P6: ICONOS PROPIOS DE LA MARCA. Entran los 8 iconos que mando Ivan
               (todo, golosinas, galletitas, comestibles, bebidas, sin-alcohol,
               con-alcohol, saludables), reemplazando a los provisorios. Van
               INLINE en el HTML (no como <img>) por un motivo concreto: asi el
               icono HEREDA el color del texto. Los archivos venian con el verde
               #235339 QUEMADO en el stroke, y en un azulejo activo (fondo verde)
               habrian quedado verde-sobre-verde = invisibles; se cambio ese
               color por currentColor, entonces se pintan verdes sobre fondo
               blanco y BLANCOS sobre el azulejo/solapa activa, solos.
               Se respeta el grosor de linea original de los archivos (1.8): el
               CSS ya no lo pisa, solo fija el tamaño. Los 8 iconos se usan en
               los DOS menus (navbar de PC y mosaico de celular) = 16 lugares,
               verificados uno por uno contra el archivo original. La pastilla
               Ofertas conserva su icono de etiqueta. Solo tienda: catalogo.html
               + tienda.css. SIN migracion.
v0.35.0 -> P7: MEDIOS DE PAGO. Pantalla nueva en el panel (Sistema -> Medios de
               pago) donde se configura COMO PUEDE PAGARTE el cliente: Efectivo,
               Transferencia (titular, banco, CBU/CVU, alias, CUIT), QR (se sube
               la imagen del QR del banco) y Mercado Pago (casillero listo pero
               APAGADO: el cobro real se programa en la etapa siguiente).
               OJO con la diferencia, son dos cosas distintas:
                 · Cobro.forma_pago -> COMO ENTRO la plata. Lo registra Juliana
                   despues del pago. Eso ya existia y no se toco.
                 · Estos campos     -> COMO PUEDE PAGAR el cliente. Es lo que se
                   le muestra en el checkout ANTES de pagar.
               En el checkout el cliente ELIGE uno y queda guardado en el pedido
               (Pedido.medio_pago). Al elegir, se despliegan los datos de ESE
               medio (el CBU solo si eligio transferencia, el QR solo si eligio
               QR); el CBU y el alias se copian con un toque. Lo que este apagado
               en el panel NO se le muestra, y el backend revalida la eleccion
               contra lo realmente habilitado (defensa en profundidad). Si no hay
               ningun medio prendido, el bloque no aparece y el pedido se manda
               igual: nunca se traba una venta por la configuracion de pagos.
               Se agrego QR a FormaPago (ahora tambien se puede registrar un
               cobro por QR). CON MIGRACION: migrar_v350.py (10 columnas en
               ajustes + medio_pago en pedidos, idempotente y con backup).
v0.35.1 -> P7-cierre: EL MEDIO DE PAGO SE VE EN EL DETALLE DEL PEDIDO. Juliana
               abre el pedido y ve "Quiere pagar con: Transferencia". Ademas, en
               el bloque de Cobros aparece el recordatorio y el desplegable viene
               PRESELECCIONADO con lo que eligio el cliente (un clic menos).
               Es una ayuda, no una imposicion: si dijo transferencia y termino
               pagando en efectivo, se registra efectivo. Manda lo que realmente
               entro. Nuevo: propiedad Pedido.medio_pago_etiqueta. Los pedidos
               viejos (sin medio) no muestran nada. SIN migracion (las columnas
               ya entraron con migrar_v350).
v0.36.0 -> P8: FIX DE ALINEACION DEL CHECKOUT Y LA CONFIRMACION. Las clases
               .t-header-top, .t-marca y .t-tagline las usaban checkout.html y
               confirmacion.html desde siempre, pero NUNCA tuvieron una linea de
               CSS: quedaron huerfanas cuando en v0.22 se rediseño el header de
               la tienda (que paso a .t-head-main). Por eso el encabezado se veia
               como texto crudo apilado contra el borde izquierdo. Ahora comparten
               el mismo ancho (620px) y el mismo centrado que .co-wrap, en PC y en
               celular. Ademas "Seguir comprando" dejo de ser un link suelto y es
               un BOTON con forma de pastilla: al pasar el mouse se pinta de verde
               y la flecha se corre hacia la izquierda; en celular ocupa todo el
               ancho (imposible errarle con el dedo). La flecha ahora la pone el
               CSS (se saco del HTML) para poder animarla. Como las dos pantallas
               comparten las clases, el arreglo del CSS cura las DOS de una.
               SIN migracion.
v0.37.0 -> P9: MERCADO PAGO EN LA TIENDA (Checkout Pro). El cliente elige MP en
               el checkout, se lo manda al sitio de Mercado Pago, paga y vuelve
               solo. Cuando el pago se acredita, MP le avisa al sistema por un
               WEBHOOK y el cobro se registra SOLO: Juliana no toca nada.
               Piezas nuevas: app/pagos_mp.py (unica puerta a MP, como
               comisiones.py), rutas /mp/retorno/<token> y /mp/webhook.

               COSTO DE PLATAFORMA — regla de Ivan: el precio de lista es igual
               para todos; el que elige pagar con MP (y financiarse con su
               tarjeta) paga ADEMAS lo que cobra la pasarela, asi a Ivan le
               entran sus $100 + IVA limpios. La cuenta DIVIDE, no suma:
                     total_a_cobrar = total / (1 - comision)
               Sumar el porcentaje se queda corto porque MP cobra tambien sobre
               el recargo (en un pedido de $50.000 la diferencia es $17,82).
               Es PARAMETRIZABLE desde el panel (activo si/no, porcentaje, y si
               lleva IVA): cuando MP cambie tarifas o la contadora defina lo del
               IVA, se ajusta sin tocar codigo.

               BLINDAJE DE OFERTAS: en un pedido con productos en oferta (piso de
               margen 10%) NO se ofrece Mercado Pago, porque la comision se come
               casi toda la ganancia. Se esconde en el checkout Y se rechaza en
               el backend (misma logica que el candado del 6%).

               SEGURIDAD: las credenciales se leen de variables de entorno
               (MP_ACCESS_TOKEN / MP_PUBLIC_KEY) definidas en el archivo WSGI de
               PythonAnywhere, NUNCA en el repo. Arranca en MODO PRUEBA
               (MP_SANDBOX=1 por defecto). El webhook va sin CSRF (lo llama MP,
               no un form nuestro) pero NO se le cree nada: se re-pregunta a MP
               con nuestro token cual es el estado real del pago. El registro de
               cobro es idempotente (MP avisa varias veces el mismo pago).
               Si MP no esta configurado o falla, el pedido se guarda igual y se
               sigue por WhatsApp: nunca se pierde una venta.
               CON MIGRACION: migrar_v370.py (3 columnas en ajustes + 4 en
               pedidos). Requiere haber corrido antes migrar_v350.py.
v0.37.1 -> P9-fix: los mensajes de aviso de la pantalla de Medios de pago se
               alinean con el contenido. Vivian en base_admin.html, FUERA del
               contenedor de ancho fijo, asi que la barra verde de "guardado"
               cruzaba de punta a punta mientras todo lo demas respetaba su
               margen. Ojo del cliente. SIN migracion.
v0.37.2 -> P9-fix2: TEXTO INVISIBLE en Medios de pago. Las etiquetas de los
               interruptores ("Aceptar pago con Mercado Pago", "Sumarle el IVA",
               etc.) se veian apagadas, casi ilegibles. Causa: se uso la variable
               --text, que en la paleta El Arquitecto es CREMA (#F4F1EC) porque
               esta pensada para el fondo oscuro del sidebar; sobre la tarjeta
               BLANCA de esta pantalla se perdia. Corregido a --text-dark
               (carbon #1A1A1A). Lo detecto Ivan mirando la pantalla.
               SIN migracion.
v0.37.3 -> P9-fix3: los avisos del checkout y la confirmacion salian SIEMPRE en
               ROJO. El estilo nacio cuando esas pantallas solo mostraban errores
               de validacion, asi que estaba fijo en rojo; con Mercado Pago ahora
               tambien dan buenas noticias, y "¡Recibimos tu pago!" aparecia con
               el color de "algo salio mal". Los templates ya leian la categoria
               pero no la usaban: ahora la pintan (verde exito / amarillo aviso /
               rojo error). Lo detecto Ivan en la primera prueba real de pago.
               SIN migracion.
v0.38.0 -> P10: LOS PDF DEL CLIENTE, CON LA CARA DE LA TIENDA. El comprobante de
               pedido y el presupuesto usaban la paleta "El Arquitecto" (carbon,
               bronce, Times): la del PANEL de Juliana. Pero esos papeles los
               recibe el CLIENTE y tienen que verse como la tienda. Ahora:
                 · Franja VERDE de marca arriba, con el logo real.
                 · Marca de agua con el isotipo, muy tenue (7%): se insinua sin
                   competir con los precios ni comer tinta al imprimir.
                 · Tabla de productos con encabezado verde y filas alternadas
                   (con 15 renglones el ojo se pierde si son todas iguales).
                 · Total en caja verde, bien visible.
               Nuevo app/pdf_marca.py: los colores, el logo y la marca de agua
               viven en UN solo lugar y los comparten los dos documentos (misma
               idea que comisiones.py). Si cambia un color de la marca, se toca
               una linea y cambian los dos.
               Ademas: se SACO la IP y el dispositivo del PDF (dato interno de
               seguridad; Ivan lo sigue viendo en el panel, pero en el papel del
               cliente no suma), y el comprobante ahora MUESTRA EL COSTO DE
               PLATAFORMA desglosado cuando se pago con Mercado Pago (antes el
               PDF decia un total y al cliente le figuraba otro en su tarjeta).
               Si faltara un archivo de logo, el PDF sale igual con el nombre en
               texto: un comprobante tiene que salir SIEMPRE. SIN migracion.
v0.38.1 -> P11: FIX DE LA HORA (todo se veia 3 HORAS ATRASADO). Era una DOBLE
               CONVERSION: models._ahora() guarda HORA ARGENTINA sin etiqueta de
               zona, pero timezone.a_argentina() asumia que un dato sin zona
               venia en UTC y le restaba 3 horas otra vez. Un pedido de las 02:34
               del 19/07 se mostraba como 23:34 del 18/07.
               NO era solo cosmetico: todo pedido hecho entre medianoche y las
               3 AM figuraba con la FECHA DEL DIA ANTERIOR (y si caia un 1° de
               mes, del MES anterior), ensuciando cualquier corte por dia o por
               mes. Afectaba al panel, a los PDF y a los listados.
               Arreglado en a_argentina(): un datetime sin zona ahora se
               interpreta como lo que realmente es en esta base, hora Argentina.
               Se verificaron los 14 campos de fecha del modelo: NINGUNO guarda
               en UTC (todos usan _ahora()), asi que el cambio es seguro.
               NO HAY QUE MIGRAR NADA: lo guardado siempre estuvo bien, lo que
               fallaba era la lectura. Las fechas historicas se corrigen solas.
               Lo detecto Ivan comparando la hora real con la del pedido.
               SIN migracion.
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # IMPORTANTE: en produccion poner una SECRET_KEY real via variable de entorno
    SECRET_KEY = os.environ.get('SECRET_KEY', 'axial-dev-cambiar-en-produccion')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Identidad / version ---
    APP_VERSION = '0.38.1'
    APP_NOMBRE = 'Saludables'
    APP_SUBTITULO = 'Catalogo Mayorista · Pilar'

    # URL publica del sistema (se usa en el mensaje de bienvenida por WhatsApp).
    # Si tu dominio es otro, cambialo aca.
    APP_URL = 'https://saludablespilar.pythonanywhere.com/'

    # ------------------------------------------------------------------
    # v0.21.0 · CSRF — fix del "Bad Request: The CSRF token has expired"
    # ------------------------------------------------------------------
    # Por defecto Flask-WTF le pone al token CSRF un vencimiento de 1 HORA,
    # INDEPENDIENTE de la sesion. Resultado: dejas el login (o cualquier
    # formulario) abierto una hora, apretas Guardar, y te salta un "Bad Request"
    # crudo y feo. Le paso None: el token deja de tener reloj propio y pasa a
    # durar LO MISMO QUE LA SESION.
    #
    # ¿Se pierde seguridad? NO. El token sigue siendo unico y firmado con la
    # SECRET_KEY: la proteccion contra CSRF sigue intacta. Lo unico que se quita
    # es el vencimiento por tiempo, que es justo lo que molestaba. Y como abajo
    # la sesion muere sola por inactividad, el token muere con ella.
    WTF_CSRF_TIME_LIMIT = None

    # ------------------------------------------------------------------
    # v0.20.1 / v0.21.0 · SESION (auto-logout por inactividad)
    # ------------------------------------------------------------------
    # Minutos de inactividad antes de cerrar la sesion sola. CUALQUIER movimiento
    # del mouse o tecla reinicia el contador al maximo.
    # >>> Si 2 minutos te resulta molesto (ej: leer una lista larga sin tocar
    #     nada), cambia este numero y listo. No hay que tocar codigo ni migrar.
    SESION_TIMEOUT_MIN = 2

    # Segundos finales en los que la barra se pone roja y late (aviso visual).
    SESION_AVISO_SEG = 30

    # --- v0.21.0: el candado DE VERDAD (server-side) ---
    # Hasta v0.20.1 el auto-logout era SOLO JavaScript: si alguien cerraba el
    # navegador (o desactivaba el JS), la cookie de sesion seguia viva y podia
    # volver a entrar sin loguearse. Esto lo arregla: la cookie se VENCE SOLA en
    # el servidor, pase lo que pase en el navegador.
    #
    # Le doy 1 minuto de colchon sobre el contador visual, para que el JS llegue
    # a redirigir con su mensaje lindo ANTES de que el servidor corte en seco.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESION_TIMEOUT_MIN + 1)

    # Renovar la cookie en cada request. Junto con el "heartbeat" del navegador
    # (ver base_admin.html / base_revendedora.html), mantiene sincronizado lo que
    # muestra la barrita con lo que realmente piensa el servidor.
    SESSION_REFRESH_EACH_REQUEST = True

    # Endurecer la cookie de sesion (no cuesta nada y suma).
    SESSION_COOKIE_HTTPONLY = True     # el JS no puede leer la cookie (anti-XSS)
    SESSION_COOKIE_SAMESITE = 'Lax'    # no viaja desde sitios de terceros

    # ------------------------------------------------------------------
    # v0.21.0 · PISO DE GANANCIA DE LA CASA (base del modulo de comisiones, E2)
    # ------------------------------------------------------------------
    # La comision de la revendedora sale DE ADENTRO del margen, no se suma
    # encima. Entonces, con el piso blindado del 10% y una revendedora en el
    # escalon del 4%:
    #
    #       margen de la venta (10%)  -  comision (4%)  =  6% para la casa
    #
    # Este numero es LO MINIMO que le tiene que quedar a la casa (Ivan + Juliana)
    # DESPUES de pagar la comision. El backend NUNCA va a dejar confirmar una
    # venta que deje a la casa por debajo de este piso.
    #
    # Regla que se hace cumplir en el servidor:
    #       margen_de_la_venta  -  comision_del_escalon  >=  MARGEN_CASA_MINIMO
    #
    MARGEN_CASA_MINIMO = 6.0

    # ------------------------------------------------------------------
    # v0.23.0 · FRENTE E — VENTA DE LA REVENDEDORA
    # ------------------------------------------------------------------
    # Carrito minimo de un pedido de revendedora, en NETO (sin IVA).
    #
    # ¿Por que NETO y no con IVA? Porque el IVA no es plata de Ivan: es plata
    # que se le junta a AFIP. Si el minimo fuera "con IVA", el 21% del pedido
    # seria impuesto y el pedido real seria mas chico de lo pactado. Y la
    # comision se calcula sobre el MISMO neto, por la misma razon: nadie
    # comisiona sobre los impuestos.
    MINIMO_REVENDEDORA_NETO = 50000.0

    # Escalones de comision. Se leen de aca (no estan hardcodeados en el codigo)
    # para poder cambiarlos sin tocar una linea de Python.
    #   'desde' = ventas NETAS acumuladas y APROBADAS que hay que superar.
    #
    # OJO — la cuenta que hay que entender:
    #   La comision sale DE ADENTRO del margen, no se suma encima. Entonces el
    #   margen minimo que el sistema le exige a cada revendedora es:
    #
    #        margen_minimo = MARGEN_CASA_MINIMO + su comision
    #
    #   Inicial (2%) -> margen minimo  8%  ->  8 - 2 = 6% para la casa  ✓
    #   Plata   (3%) -> margen minimo  9%  ->  9 - 3 = 6% para la casa  ✓
    #   Oro     (4%) -> margen minimo 10%  -> 10 - 4 = 6% para la casa  ✓
    #
    #   Es decir: CUANTO MAS GANA ELLA, MENOS PUEDE REGALAR. Por ningun camino
    #   -ni bajando el precio a mano, ni con un producto raro- la casa termina
    #   ganando menos del 6%. El backend lo hace cumplir.
    COMISION_NIVELES = [
        {'clave': 'INICIAL', 'nombre': 'Inicial', 'comision': 2.0, 'desde': 0},
        {'clave': 'PLATA',   'nombre': 'Plata',   'comision': 3.0, 'desde': 5_000_000},
        {'clave': 'ORO',     'nombre': 'Oro',     'comision': 4.0, 'desde': 10_000_000},
    ]

    # Reglas de permanencia. La LOGICA que las aplica se programa en E5; se
    # dejan los numeros aca para no volver a tocar el config despues.
    # (PythonAnywhere free NO tiene tareas programadas: esto se calcula al
    #  consultar, nunca con un cron.)
    # v0.26.0 · Reglas de PERMANENCIA (las aplica app/comisiones.py, sin cron).
    # Regla mixta confirmada por Ivan:
    #   · Al ganar/alcanzar un nivel, se asegura COMISION_MESES_GRACIA meses:
    #     en ese lapso NO se puede bajar, venda lo que venda.
    #   · Pasada la gracia, cada mes se exige COMISION_PISO_MENSUAL de venta neta.
    #     El primer mes cerrado que no llega -> baja UN SOLO escalon
    #     (Oro->Plata, Plata->Inicial), y arranca una gracia nueva en el nivel
    #     de abajo (para que se recupere sin caer en cascada).
    COMISION_MESES_GRACIA = 6            # meses que un nivel queda asegurado
    COMISION_PISO_MENSUAL = 2_000_000    # venta neta minima por mes, ya sin gracia

    # ------------------------------------------------------------------
    # v0.18.2 · Redes del NEGOCIO (para el "Seguinos en" de la tienda)
    # ------------------------------------------------------------------
    # Completa solo las que tengas; las vacias no se muestran.
    # Pega el link completo (https://...).
    REDES = {
        'instagram': '',
        'facebook': '',
        'youtube': '',
        'tiktok': '',
        'linkedin': '',
        'whatsapp_canal': '',   # link del canal de WhatsApp (boton "Sumate al canal")
    }

    # Base de datos (SQLite en instance/)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'saludables.db')


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False


config = {
    'dev': DevConfig,
    'prod': ProdConfig,
    'default': DevConfig,
}
