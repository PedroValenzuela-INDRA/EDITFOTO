'use strict';

/* =====================================================================
   EDITFOTO - interfaz web local (JavaScript puro, sin dependencias)
   Secciones: utilidades, API y avisos, estado, rejilla, procesado por
   lotes, detalle (con giro de 90 grados), pintor, presets, app de escritorio
   (modelos, actualizacion, novedades, carpetas, salir), teclado y arranque.
   ===================================================================== */

/* ---------------------------------------------------------------------
   Utilidades
   --------------------------------------------------------------------- */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));
const limitar = (v, a, b) => Math.min(b, Math.max(a, v));
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function crear(etiqueta, atributos = {}, ...hijos) {
  const n = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (v === false || v == null) continue;
    if (k === 'class') n.className = v;
    else if (k === 'texto') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const h of hijos.flat()) if (h != null) n.append(h);
  return n;
}

const esObjeto = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);

function obtener(obj, ruta) {
  return ruta.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function fijar(obj, ruta, valor) {
  const partes = ruta.split('.');
  let o = obj;
  for (const k of partes.slice(0, -1)) {
    if (!esObjeto(o[k])) o[k] = {};
    o = o[k];
  }
  o[partes[partes.length - 1]] = valor;
  return obj;
}

function fusionar(a, b) {
  const salida = JSON.parse(JSON.stringify(a || {}));
  for (const [k, v] of Object.entries(b || {})) {
    if (esObjeto(v) && esObjeto(salida[k])) salida[k] = fusionar(salida[k], v);
    else salida[k] = JSON.parse(JSON.stringify(v));
  }
  return salida;
}

/** Numero con formato espanol (coma decimal). */
function num(v, dec = 2) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return Number(v).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function conSigno(v, dec = 2, sufijo = '') {
  const n = Math.abs(v) < 0.5 * Math.pow(10, -dec) ? 0 : v;
  return (n > 0 ? '+' : '') + num(n, dec) + sufijo;
}

const almacen = {
  leer(clave, defecto) {
    try {
      const v = localStorage.getItem('editfoto.' + clave);
      return v == null ? defecto : v;
    } catch (e) {
      return defecto;
    }
  },
  guardar(clave, valor) {
    try {
      localStorage.setItem('editfoto.' + clave, String(valor));
    } catch (e) { /* sin almacenamiento: no pasa nada */ }
  },
};

function hexARgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  const n = m ? parseInt(m[1], 16) : 0;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function nombreValido(texto) {
  return texto.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
}

/* ---------------------------------------------------------------------
   API y avisos
   --------------------------------------------------------------------- */

class ErrorApi extends Error {
  constructor(mensaje, estado) {
    super(mensaje);
    this.estado = estado;
  }
}

function detalleATexto(d) {
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((i) => (i && i.msg) || JSON.stringify(i)).join('; ');
  return d ? JSON.stringify(d) : '';
}

function avisar(texto, tipo = 'info') {
  const cont = $('#avisos');
  const n = crear('div', { class: 'aviso ' + tipo, role: tipo === 'error' ? 'alert' : 'status', texto });
  const quitar = () => n.remove();
  n.addEventListener('click', quitar);
  cont.append(n);
  while (cont.children.length > 4) cont.firstElementChild.remove();
  setTimeout(quitar, tipo === 'error' ? 8000 : 4500);
}

async function api(metodo, url, cuerpo, { silencioso = false } = {}) {
  const opc = { method: metodo, headers: {} };
  if (cuerpo instanceof Blob) {
    opc.body = cuerpo;
    opc.headers['Content-Type'] = cuerpo.type || 'image/png';
  } else if (cuerpo !== undefined) {
    opc.body = JSON.stringify(cuerpo);
    opc.headers['Content-Type'] = 'application/json';
  }
  let r;
  try {
    r = await fetch(url, opc);
  } catch (e) {
    const msg = 'No se puede conectar con EDITFOTO. Comprueba que el programa sigue abierto.';
    if (!silencioso && !S.cerrada) avisar(msg, 'error');
    throw new ErrorApi(msg, 0);
  }
  if (!r.ok) {
    let texto = r.statusText || 'Error ' + r.status;
    try {
      const crudo = await r.text();
      try {
        const j = JSON.parse(crudo);
        texto = detalleATexto(j.detail !== undefined ? j.detail : j) || texto;
      } catch (e) {
        if (crudo) texto = crudo.slice(0, 300);
      }
    } catch (e) { /* se queda el texto de estado */ }
    if (!silencioso) avisar(texto, 'error');
    throw new ErrorApi(texto, r.status);
  }
  const tipo = r.headers.get('content-type') || '';
  return tipo.includes('json') ? r.json() : r.text();
}

function confirmar(texto, { titulo = 'Confirmar', si = 'Aceptar', no = 'Cancelar' } = {}) {
  const dlg = $('#dlg-confirmar');
  if (dlg.open) return Promise.resolve(false);
  $('#confirmar-titulo').textContent = titulo;
  $('#confirmar-texto').textContent = texto;
  $('#confirmar-si').textContent = si;
  $('#confirmar-no').textContent = no;
  return new Promise((resolver) => {
    const fin = () => {
      dlg.removeEventListener('close', fin);
      resolver(dlg.returnValue === 'si');
    };
    dlg.addEventListener('close', fin);
    dlg.returnValue = '';
    dlg.showModal();
    $('#confirmar-si').focus();
  });
}

/* ---------------------------------------------------------------------
   Estado global
   --------------------------------------------------------------------- */

const S = {
  fotos: [],
  porId: new Map(),
  estado: null,
  presets: [],
  descripciones: {},
  cachePresets: new Map(),
  filtro: 'todas',
  vista: 'rejilla', // rejilla | detalle | presets
  id: null, // foto abierta en el detalle
  ultimo: null, // ultima foto abierta (para resaltarla al volver)
  modo: 'resultado', // resultado | antes | pintar
  progreso: { activo: false, fase: null, actual: null, hechas: 0, total: 0, errores: 0 },
  vigilando: false,
  trabajoVisto: false,
  scrollRejilla: 0,
  girando: new Map(), // id -> giros en curso (rejilla y detalle)
  modelos: null, // ultima respuesta de /api/modelos
  cerrada: false, // true tras pulsar Salir: se dejan de consultar cosas
};

const FILTROS = {
  todas: () => true,
  pendientes: (f) => f.estado === 'pendiente',
  'sin-aprobar': (f) => f.estado === 'lista' && !f.aprobada,
  aprobadas: (f) => f.aprobada,
  error: (f) => f.estado === 'error',
};

const visibles = () => S.fotos.filter(FILTROS[S.filtro] || FILTROS.todas);
const fotoActual = () => (S.id ? S.porId.get(S.id) : null);

async function presetBase(nombre) {
  if (!S.cachePresets.has(nombre)) {
    S.cachePresets.set(nombre, await api('GET', '/api/presets/' + encodeURIComponent(nombre)));
  }
  return S.cachePresets.get(nombre);
}

async function cargarEstado() {
  S.estado = await api('GET', '/api/estado');
  pintarInsignia();
  $('#marca').title = `Fotos de entrada: ${S.estado.entrada}\nFotos editadas: ${S.estado.salida}`;
  pintarVersion(S.estado.version);
  $('#btn-salir').hidden = !S.estado.exe;
  $('#aprender-carpeta').placeholder = S.estado.ejemplos ? 'vacío = ' + S.estado.ejemplos : 'vacío = la carpeta de fotos de ejemplo de EDITFOTO';
}

async function cargarPresets() {
  const lista = await api('GET', '/api/presets');
  S.descripciones = {};
  for (const p of lista) S.descripciones[p.nombre] = p.descripcion || '';
  S.presets = lista.map((p) => p.nombre);
  rellenarSelectores();
}

function pintarInsignia() {
  const ins = $('#insignia');
  const prov = (S.estado && S.estado.proveedor) || '';
  const nombres = { CUDA: 'GPU (CUDA)', Dml: 'GPU (DirectML)', CoreML: 'GPU (Apple)', CPU: 'CPU' };
  ins.textContent = nombres[prov] || prov || 'CPU';
  ins.classList.toggle('gpu', !!(S.estado && S.estado.gpu));
  ins.classList.toggle('cpu', !(S.estado && S.estado.gpu));
  ins.title = 'Acelerador que usa la IA' + (S.estado && S.estado.modelo_segmentacion ? ` (modelo: ${S.estado.modelo_segmentacion})` : '');
  ins.hidden = false;
}

function rellenarSelect(sel, { conVacio = null, valor = null } = {}) {
  const previo = valor != null ? valor : sel.value;
  sel.replaceChildren();
  if (conVacio) sel.append(crear('option', { value: '', texto: conVacio }));
  for (const n of S.presets) sel.append(crear('option', { value: n, texto: n }));
  if ([...sel.options].some((o) => o.value === previo)) sel.value = previo;
}

function rellenarSelectores() {
  rellenarSelect($('#sel-lote'), { conVacio: 'El de cada foto', valor: almacen.leer('lote', '') });
  rellenarSelect($('#sel-preset-foto'), { valor: fotoActual() ? fotoActual().preset : null });
  rellenarSelect($('#nuevo-base'), { valor: 'generico' });
  rellenarSelect($('#aprender-base'), { valor: 'generico' });
}

/* ---------------------------------------------------------------------
   Imagenes (carga con precarga: no se muestra hasta estar decodificada)
   --------------------------------------------------------------------- */

let cargasImg = 0;

/** Cuartos de vuelta horarios que lleva la foto (ajustes.giro90, de 0 a 3). */
const giroDe = (f) => Number((f && f.ajustes && f.ajustes.giro90) || 0) || 0;

/** URL de la imagen original de trabajo. El ?v= cambia con el giro para que se recargue al girar. */
const urlOriginal = (f, max) => `/img/${f.id}/original?` + (max ? `max=${max}&` : '') + `v=${giroDe(f)}`;

function ponerImagen(img, url) {
  if (img._url === url && img._promesa) return img._promesa;
  img._url = url;
  cargasImg++;
  actualizarOcupado();
  const p = (async () => {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(String(r.status));
      const blob = await r.blob();
      if (img._url !== url) return false;
      const obj = URL.createObjectURL(blob);
      const vieja = img._obj;
      img._obj = obj;
      img.src = obj;
      try { await img.decode(); } catch (e) { /* se ve igualmente */ }
      if (vieja) URL.revokeObjectURL(vieja);
      return true;
    } catch (e) {
      if (img._url === url) {
        img._url = null;
        img._promesa = null;
        avisar('No se ha podido cargar la imagen.', 'error');
      }
      return false;
    } finally {
      cargasImg--;
      actualizarOcupado();
    }
  })();
  img._promesa = p;
  return p;
}

function soltarImagen(img) {
  img._url = null;
  img._promesa = null;
  if (img._obj) URL.revokeObjectURL(img._obj);
  img._obj = null;
  img.removeAttribute('src');
}

/* ---------------------------------------------------------------------
   Actualizacion de fotos
   --------------------------------------------------------------------- */

/** Guarda una foto devuelta por el servidor (ignora respuestas mas viejas). */
function guardarFoto(f) {
  const vieja = S.porId.get(f.id);
  if (vieja && f.version < vieja.version) return vieja;
  S.porId.set(f.id, f);
  const i = S.fotos.findIndex((x) => x.id === f.id);
  if (i >= 0) S.fotos[i] = f;
  else S.fotos.push(f);
  tarjetaActualizar(f);
  actualizarContador();
  if (S.vista === 'detalle' && S.id === f.id) {
    pintarCabeceraDetalle();
    pintarInfo();
    if (S.modo === 'pintar') herramientasActualizar();
  }
  return f;
}

function aplicarLista(lista) {
  const nuevos = new Set(lista.map((f) => f.id));
  let versionCambiada = false;
  for (const f of lista) {
    const vieja = S.porId.get(f.id);
    if (vieja && f.version < vieja.version) {
      lista[lista.indexOf(f)] = vieja;
      continue;
    }
    if (S.id === f.id && vieja && vieja.version !== f.version) versionCambiada = true;
    S.porId.set(f.id, f);
  }
  for (const id of [...S.porId.keys()]) if (!nuevos.has(id)) S.porId.delete(id);
  S.fotos = lista.map((f) => S.porId.get(f.id));
  rejillaSincronizar();
  actualizarContador();
  if (S.vista === 'detalle' && fotoActual()) {
    pintarCabeceraDetalle();
    pintarInfo();
    if (versionCambiada && D.pendientes === 0) actualizarVisor();
  }
}

async function cargarFotos() {
  const r = await api('GET', '/api/fotos');
  aplicarLista(r.fotos);
}

/* ---------------------------------------------------------------------
   Rejilla
   --------------------------------------------------------------------- */

const tarjetas = new Map();

function crearTarjeta(f) {
  const t = crear(
    'article',
    { class: 'tarjeta', 'data-id': f.id, tabindex: '0', role: 'button' },
    crear('div', { class: 'miniatura' }, crear('img', { alt: '', loading: 'lazy', decoding: 'async', draggable: 'false' })),
    crear('label', { class: 'casilla', title: 'Aprobada' }, crear('input', { type: 'checkbox', 'aria-label': 'Foto aprobada' })),
    crear(
      'div',
      { class: 'giros' },
      botonGiro(-1, 'giro'),
      botonGiro(1, 'giro')
    ),
    crear(
      'div',
      { class: 'datos' },
      crear('div', { class: 'nombre' }),
      crear('div', { class: 'meta' }, crear('span', { class: 'chip' }), crear('span', { class: 'insignia-estado' })),
      crear('div', { class: 'linea-error', hidden: true })
    )
  );
  const img = $('img', t);
  img.addEventListener('load', () => img.parentElement.classList.remove('sin-vista'));
  img.addEventListener('error', () => {
    // Si falla la miniatura del resultado, se prueba con la del original.
    const actual = S.porId.get(f.id) || f;
    if (img.dataset.clave && img.dataset.clave[0] !== 'o') {
      img.dataset.clave = 'o' + giroDe(actual);
      img.src = `/img/${f.id}/miniatura/original?v=${giroDe(actual)}`;
    } else {
      img.parentElement.classList.add('sin-vista');
    }
  });
  tarjetas.set(f.id, t);
  return t;
}

function estadoVisible(f) {
  const trabajando = S.progreso.activo && S.progreso.actual === f.id;
  if (S.girando.has(f.id)) return ['procesando', 'Girando'];
  if (trabajando) return ['procesando', 'Procesando'];
  if (f.estado === 'error') return ['error', 'Error'];
  if (f.estado === 'lista') return f.aprobada ? ['aprobada', 'Aprobada'] : ['lista', 'Lista'];
  return ['', 'Pendiente'];
}

function tarjetaActualizar(f) {
  const t = tarjetas.get(f.id) || crearTarjeta(f);
  const lista = f.estado === 'lista';
  const trabajando = (S.progreso.activo && S.progreso.actual === f.id) || S.girando.has(f.id);
  t.classList.toggle('aprobada', !!f.aprobada);
  t.classList.toggle('sin-resultado', !lista);
  t.classList.toggle('procesando', trabajando);
  t.classList.toggle('reciente', S.vista === 'rejilla' && S.ultimo === f.id);
  const img = $('img', t);
  const clave = lista ? 'r' + f.version : 'o' + giroDe(f);
  if (img.dataset.clave !== clave) {
    img.dataset.clave = clave;
    img.src = lista ? `/img/${f.id}/miniatura/resultado?v=${f.version}` : `/img/${f.id}/miniatura/original?v=${giroDe(f)}`;
  }
  const nombre = $('.nombre', t);
  nombre.textContent = '';
  nombre.append(f.nombre);
  if (f.carpeta) nombre.append(' ', crear('small', { texto: f.carpeta + '/' }));
  nombre.title = f.ruta;
  const chip = $('.chip', t);
  chip.textContent = f.preset;
  chip.title = 'Preset: ' + f.preset;
  const [clase, texto] = estadoVisible(f);
  const ins = $('.insignia-estado', t);
  ins.className = 'insignia-estado' + (clase ? ' ' + clase : '');
  ins.textContent = texto;
  const casilla = $('.casilla input', t);
  casilla.checked = !!f.aprobada;
  casilla.disabled = !lista;
  $('.casilla', t).title = lista ? (f.aprobada ? 'Aprobada: pulsa para quitar' : 'Pulsa para aprobar') : 'Procesa la foto antes de aprobarla';
  const err = $('.linea-error', t);
  err.hidden = !(f.estado === 'error' && f.error);
  err.textContent = f.error || '';
  err.title = f.error || '';
  t.setAttribute('aria-label', `${f.nombre}, ${texto}`);
  t.hidden = !(FILTROS[S.filtro] || FILTROS.todas)(f);
  return t;
}

function rejillaSincronizar() {
  const cont = $('#rejilla');
  const ids = new Set(S.fotos.map((f) => f.id));
  for (const [id, t] of tarjetas) {
    if (!ids.has(id)) {
      t.remove();
      tarjetas.delete(id);
    }
  }
  S.fotos.forEach((f, i) => {
    const t = tarjetaActualizar(f);
    if (cont.children[i] !== t) cont.insertBefore(t, cont.children[i] || null);
  });
  rejillaVacia();
}

function rejillaVacia() {
  const v = $('#rejilla-vacia');
  const hay = visibles().length;
  v.hidden = hay > 0;
  if (hay > 0) return;
  const entrada = S.estado ? S.estado.entrada : '';
  const clave = S.fotos.length === 0 ? 'sin-fotos|' + entrada : 'filtro';
  if (v.dataset.clave === clave && v.children.length) return; // ya está pintado: no se pierde el foco
  v.dataset.clave = clave;
  v.replaceChildren();
  if (S.fotos.length === 0) {
    v.append(
      crear('h2', { texto: 'Copia aquí las fotos del día' }),
      entrada
        ? crear('p', {}, 'Carpeta de entrada: ', crear('code', { texto: entrada }))
        : crear('p', { texto: 'Copia las fotos a la carpeta de entrada de EDITFOTO.' }),
      crear(
        'div',
        { class: 'vacio-botones' },
        crear('button', { type: 'button', class: 'btn primario', onclick: () => abrirCarpeta('entrada'), texto: 'Abrir la carpeta de entrada' }),
        crear('button', { type: 'button', class: 'btn', onclick: recargarCarpeta, texto: 'Recargar carpeta' })
      ),
      crear('p', {
        class: 'ayuda',
        texto: 'Si las pones en subcarpetas llamadas como un preset (sudadera, pantalón, jersey...), cada una usa su preset.',
      })
    );
  } else {
    v.append(crear('p', { texto: 'Ninguna foto cumple el filtro elegido.' }));
  }
}

function actualizarContador() {
  const total = S.fotos.length;
  const aprobadas = S.fotos.filter((f) => f.aprobada).length;
  $('#contador').textContent = `${aprobadas} / ${total} aprobadas`;
  const cuenta = (k) => S.fotos.filter(FILTROS[k]).length;
  const etiquetas = {
    todas: 'Todas',
    pendientes: 'Pendientes',
    'sin-aprobar': 'Sin aprobar',
    aprobadas: 'Aprobadas',
    error: 'Con error',
  };
  for (const o of $('#filtro').options) o.textContent = `${etiquetas[o.value]} (${cuenta(o.value)})`;
}

function aplicarFiltro() {
  S.filtro = $('#filtro').value;
  almacen.guardar('filtro', S.filtro);
  for (const f of S.fotos) {
    const t = tarjetas.get(f.id);
    if (t) t.hidden = !FILTROS[S.filtro](f);
  }
  rejillaVacia();
  if (S.vista === 'detalle') pintarCabeceraDetalle();
}

async function fijarAprobada(id, valor) {
  const f = S.porId.get(id);
  if (!f) return;
  const antes = f.aprobada;
  f.aprobada = valor;
  tarjetaActualizar(f);
  actualizarContador();
  if (S.id === id) pintarCabeceraDetalle();
  try {
    guardarFoto(await api('POST', `/api/fotos/${id}/aprobar`, { aprobada: valor }));
  } catch (e) {
    f.aprobada = antes;
    tarjetaActualizar(f);
    actualizarContador();
    if (S.id === id) pintarCabeceraDetalle();
  }
}

/* ---------------------------------------------------------------------
   Procesado por lotes y progreso
   --------------------------------------------------------------------- */

function pintarProgreso() {
  const p = S.progreso;
  $('#progreso').hidden = !p.activo;
  actualizarBotonesLote();
  const cancelar = $('#btn-cancelar');
  if (!p.activo) {
    cancelar.disabled = false;
    cancelar.textContent = 'Cancelar';
  }
  if (p.activo) {
    const pct = p.total > 0 ? Math.round((100 * p.hechas) / p.total) : 3;
    $('#barra-relleno').style.width = Math.max(pct, 3) + '%';
    $('.barra').setAttribute('aria-valuenow', String(pct));
    const fase = p.fase === 'analizando' ? 'Analizando' : p.fase === 'renderizando' ? 'Procesando' : 'Preparando';
    const f = p.actual ? S.porId.get(p.actual) : null;
    $('#progreso-texto').textContent =
      `${fase} ${p.hechas} de ${p.total}` + (f ? ' - ' + f.nombre : '') + (p.errores ? ` - ${p.errores} con error` : '');
  }
  for (const f of S.fotos) {
    const t = tarjetas.get(f.id);
    if (!t) continue;
    const trabajando = (p.activo && p.actual === f.id) || S.girando.has(f.id);
    if (t.classList.contains('procesando') !== trabajando) tarjetaActualizar(f);
  }
}

async function vigilarProgreso() {
  if (S.vigilando) return;
  S.vigilando = true;
  let vueltas = 0;
  let fallos = 0;
  try {
    for (;;) {
      let p;
      try {
        p = await api('GET', '/api/progreso', undefined, { silencioso: true });
        fallos = 0;
      } catch (e) {
        if (++fallos >= 5) {
          if (!S.cerrada) avisar('Se ha perdido la conexión con EDITFOTO.', 'error');
          S.progreso.activo = false;
          break;
        }
        await esperar(1500);
        continue;
      }
      S.progreso = p;
      if (p.activo) S.trabajoVisto = true;
      pintarProgreso();
      if (!p.activo) break;
      vueltas++;
      if (vueltas % 3 === 0) {
        try { await cargarFotos(); } catch (e) { /* se reintenta */ }
      }
      await esperar(1000);
    }
  } finally {
    S.vigilando = false;
    pintarProgreso();
  }
  try { await cargarFotos(); } catch (e) { /* ya se ha avisado */ }
  if (S.trabajoVisto) {
    S.trabajoVisto = false;
    const p = S.progreso;
    const errores = S.fotos.filter((f) => f.estado === 'error').length;
    if (errores) avisar(`Procesado terminado: ${errores} foto(s) con error.`, 'error');
    else avisar('Procesado terminado.', 'ok');
  }
}

async function procesar(forzar) {
  if (modeloBloquea()) {
    avisar(TEXTO_ESPERA_MODELO);
    return;
  }
  const pendientes = S.fotos.filter((f) => f.estado !== 'lista').length;
  if (!forzar && pendientes === 0) {
    avisar('No hay fotos pendientes de procesar.');
    return;
  }
  if (forzar) {
    const ok = await confirmar(
      `Se volverán a procesar las ${S.fotos.length} fotos, también las que ya están listas. Se conservan tus ajustes y pinceles, pero puede tardar bastante.`,
      { titulo: 'Rehacer todas', si: 'Rehacer todas', no: 'Cancelar' }
    );
    if (!ok) return;
  }
  const cuerpo = { forzar: !!forzar };
  const preset = $('#sel-lote').value;
  if (preset) cuerpo.preset = preset;
  try {
    S.progreso = await api('POST', '/api/procesar', cuerpo);
  } catch (e) {
    if (e.estado === 409) {
      // Ya hay un procesado en marcha (por ejemplo, desde otra pestaña): se sigue su progreso.
      S.trabajoVisto = true;
      vigilarProgreso();
    }
    return;
  }
  S.trabajoVisto = true;
  pintarProgreso();
  vigilarProgreso();
}

async function cancelarProcesado() {
  const b = $('#btn-cancelar');
  b.disabled = true;
  b.textContent = 'Cancelando...';
  try {
    await api('POST', '/api/cancelar');
    avisar('Se parará al terminar la foto en curso.');
  } catch (e) {
    b.disabled = false;
    b.textContent = 'Cancelar';
  }
}

async function recargarCarpeta() {
  const b = $('#btn-recargar');
  b.disabled = true;
  try {
    const antes = S.fotos.length;
    const r = await api('POST', '/api/fotos/recargar');
    aplicarLista(r.fotos);
    const dif = r.fotos.length - antes;
    avisar(dif > 0 ? `${dif} foto(s) nueva(s).` : dif < 0 ? `${-dif} foto(s) menos.` : 'La carpeta está al día.', 'ok');
  } catch (e) { /* aviso ya mostrado */ } finally {
    b.disabled = false;
  }
}

/* ---------------------------------------------------------------------
   Navegacion (hash: "", "#foto/ID", "#presets")
   --------------------------------------------------------------------- */

function leerRuta() {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  if (h.startsWith('foto/')) return { vista: 'detalle', id: h.slice(5) };
  if (h === 'presets') return { vista: 'presets' };
  return { vista: 'rejilla' };
}

async function navegar(hash) {
  const destino = leerRutaDe(hash);
  if (S.vista === 'detalle' && P.id === S.id && P.historia.length && !(destino.vista === 'detalle' && destino.id === S.id)) {
    const ok = await confirmar('Tienes trazos de pincel sin aplicar en esta foto. Si sales, se perderán.', {
      titulo: 'Trazos sin aplicar',
      si: 'Salir y descartar',
      no: 'Seguir pintando',
    });
    if (!ok) return false;
    P.historia = [];
    P.rehacer = [];
  }
  const actual = location.hash.replace(/^#\/?$/, '');
  if (actual === hash.replace(/^#\/?$/, '')) await aplicarRuta();
  else location.hash = hash;
  return true;
}

function leerRutaDe(hash) {
  const h = decodeURIComponent(hash.replace(/^#\/?/, ''));
  if (h.startsWith('foto/')) return { vista: 'detalle', id: h.slice(5) };
  if (h === 'presets') return { vista: 'presets' };
  return { vista: 'rejilla' };
}

function mostrarVista(v) {
  if (S.vista === 'rejilla') S.scrollRejilla = $('#vista-rejilla').scrollTop;
  S.vista = v;
  $('#vista-rejilla').hidden = v !== 'rejilla';
  $('#vista-detalle').hidden = v !== 'detalle';
  $('#vista-presets').hidden = v !== 'presets';
  $('#barra-lote').hidden = v !== 'rejilla';
  $('#tab-fotos').classList.toggle('activa', v !== 'presets');
  $('#tab-presets').classList.toggle('activa', v === 'presets');
}

async function aplicarRuta() {
  const r = leerRuta();
  if (S.vista === 'detalle' && !(r.vista === 'detalle')) salirDelDetalle();
  if (r.vista === 'detalle') {
    await mostrarDetalle(r.id);
  } else if (r.vista === 'presets') {
    mostrarVista('presets');
    await presetsMostrar();
  } else {
    mostrarVista('rejilla');
    $('#vista-rejilla').scrollTop = S.scrollRejilla;
    for (const f of S.fotos) {
      const t = tarjetas.get(f.id);
      if (t) t.classList.toggle('reciente', S.ultimo === f.id);
    }
    const t = S.ultimo ? tarjetas.get(S.ultimo) : null;
    if (t && !t.hidden) t.scrollIntoView({ block: 'nearest' });
  }
}

/* ---------------------------------------------------------------------
   Detalle de la foto
   --------------------------------------------------------------------- */

const AJUSTES = [
  { id: 'arrugas', grupo: 'retoque', et: 'Arrugas', ruta: 'preset.arrugas.fuerza', min: 0, max: 1, paso: 0.05, neutro: 0.5, fmt: (v) => num(v, 2) },
  { id: 'nitidez', grupo: 'retoque', et: 'Nitidez', ruta: 'preset.nitidez', min: 0, max: 1, paso: 0.05, neutro: 0.3, fmt: (v) => num(v, 2) },
  { id: 'brillo', grupo: 'color', et: 'Brillo', ruta: 'preset.color.brillo', min: -1, max: 1, paso: 0.05, neutro: 0, fmt: (v) => conSigno(v, 2) },
  { id: 'contraste', grupo: 'color', et: 'Contraste', ruta: 'preset.color.contraste', min: -0.5, max: 0.5, paso: 0.01, neutro: 0, fmt: (v) => conSigno(v, 2) },
  { id: 'saturacion', grupo: 'color', et: 'Saturación', ruta: 'preset.color.saturacion', min: 0.5, max: 1.5, paso: 0.01, neutro: 1, fmt: (v) => num(v, 2) },
  { id: 'rotacion', grupo: 'posicion', et: 'Rotación', ruta: 'rotacion', min: -15, max: 15, paso: 0.1, neutro: 0, fmt: (v) => conSigno(v, 1, '°') },
  { id: 'escala', grupo: 'posicion', et: 'Tamaño', ruta: 'escala', min: 0.6, max: 1.4, paso: 0.01, neutro: 1, fmt: (v) => num(v * 100, 0) + ' %' },
  { id: 'mover_x', grupo: 'posicion', et: 'Mover X', ruta: 'mover_x', min: -0.25, max: 0.25, paso: 0.005, neutro: 0, fmt: (v) => conSigno(v * 100, 1, ' %') },
  { id: 'mover_y', grupo: 'posicion', et: 'Mover Y', ruta: 'mover_y', min: -0.25, max: 0.25, paso: 0.005, neutro: 0, fmt: (v) => conSigno(v * 100, 1, ' %') },
];

const D = {
  base: null, // preset completo de la foto abierta
  valores: {}, // valor actual de cada deslizador
  cambios: {}, // {id, ajustes}: cambios esperando el debounce
  espera: null, // {id, ajustes}: peticion en cola que aun no ha empezado
  timer: null,
  cola: Promise.resolve(),
  pendientes: 0,
  seq: 0,
  texto: 'Procesando...',
};

function construirAjustes() {
  for (const def of AJUSTES) {
    const salida = crear('output', { class: 'valor', for: 'aj-' + def.id });
    const entrada = crear('input', {
      type: 'range', id: 'aj-' + def.id, min: def.min, max: def.max, step: def.paso, value: def.neutro,
    });
    const reset = crear('button', { type: 'button', class: 'mini', title: 'Volver al valor del preset', 'aria-label': 'Restablecer ' + def.et, texto: '↺' });
    const bloque = crear(
      'div',
      { class: 'ajuste', 'data-id': def.id },
      crear('div', { class: 'ajuste-cab' }, crear('label', { for: 'aj-' + def.id, texto: def.et }), salida, reset),
      entrada
    );
    $('#sl-' + def.grupo).append(bloque);
    entrada.addEventListener('input', () => {
      const v = parseFloat(entrada.value);
      D.valores[def.id] = v;
      ajusteVisual(def);
      pedirAjuste(fijar({}, def.ruta, v));
    });
    entrada.addEventListener('pointerup', () => entrada.blur());
    entrada.addEventListener('dblclick', () => reset.click());
    reset.addEventListener('click', () => {
      const v = valorDefecto(def);
      entrada.value = v;
      D.valores[def.id] = parseFloat(entrada.value);
      ajusteVisual(def);
      pedirAjuste(fijar({}, def.ruta, parseFloat(entrada.value)));
    });
  }
  $('#aj-enderezar').addEventListener('change', (e) => pedirAjuste({ enderezar_auto: e.target.checked }));
}

function valorDefecto(def) {
  if (def.ruta.startsWith('preset.') && D.base) {
    const v = obtener(D.base, def.ruta.slice(7));
    if (typeof v === 'number') return v;
  }
  return def.neutro;
}

function ajusteVisual(def) {
  const bloque = $(`.ajuste[data-id="${def.id}"]`);
  const v = D.valores[def.id];
  $('output', bloque).textContent = def.fmt(v);
  bloque.classList.toggle('modificado', Math.abs(v - valorDefecto(def)) > def.paso / 2);
}

function iniciarControles() {
  const f = fotoActual();
  if (!f) return;
  for (const def of AJUSTES) {
    const propio = obtener(f.ajustes || {}, def.ruta);
    const v = typeof propio === 'number' ? propio : valorDefecto(def);
    const entrada = $('#aj-' + def.id);
    entrada.value = v;
    D.valores[def.id] = parseFloat(entrada.value);
    ajusteVisual(def);
  }
  const auto = (f.ajustes || {}).enderezar_auto;
  $('#aj-enderezar').checked = auto === undefined ? true : !!auto;
  const activo = D.base ? obtener(D.base, 'enderezar.activo') : true;
  $('#aj-enderezar-ayuda').hidden = activo !== false;
  rellenarSelect($('#sel-preset-foto'), { valor: f.preset });
}

/* ---- cola de renders: debounce, un solo envio a la vez, respuestas viejas descartadas ---- */

function actualizarOcupado() {
  const ocupado = D.pendientes > 0;
  const p = $('#procesando');
  p.hidden = !ocupado;
  $('#procesando-texto').textContent = D.texto;
  $('#visor').classList.toggle('ocupado', ocupado || cargasImg > 0);
}

function encolar(trabajo, texto = 'Procesando...') {
  D.pendientes++;
  D.texto = texto;
  actualizarOcupado();
  const p = D.cola.then(async () => {
    try {
      return await trabajo();
    } finally {
      D.pendientes--;
      D.texto = 'Procesando...';
      actualizarOcupado();
    }
  });
  D.cola = p.catch(() => {});
  return p;
}

function esVigente(id, seq) {
  return S.vista === 'detalle' && S.id === id && seq === D.seq;
}

function pedirAjuste(cambio) {
  const id = S.id;
  if (D.cambios.id && D.cambios.id !== id) vaciarCambios();
  D.cambios = { id, ajustes: fusionar(D.cambios.ajustes || {}, cambio) };
  clearTimeout(D.timer);
  D.timer = setTimeout(vaciarCambios, 400);
}

/** Envia ya los cambios pendientes de deslizadores (si los hay). */
function vaciarCambios() {
  clearTimeout(D.timer);
  D.timer = null;
  const c = D.cambios;
  D.cambios = {};
  if (!c.id) return Promise.resolve();
  if (D.espera && D.espera.id === c.id) {
    // Ya hay una peticion esperando su turno: se le suman los cambios.
    D.espera.ajustes = fusionar(D.espera.ajustes, c.ajustes);
    return Promise.resolve();
  }
  const espera = { id: c.id, ajustes: c.ajustes };
  D.espera = espera;
  const seq = ++D.seq;
  return encolar(async () => {
    if (D.espera === espera) D.espera = null;
    const f = guardarFoto(await api('POST', `/api/fotos/${espera.id}/render`, { ajustes: espera.ajustes }));
    if (esVigente(espera.id, seq)) await actualizarVisor();
    return f;
  }).catch(() => {});
}

function enviarRender(id, cuerpo, texto) {
  const seq = ++D.seq;
  return encolar(async () => {
    const f = guardarFoto(await api('POST', `/api/fotos/${id}/render`, cuerpo));
    if (esVigente(id, seq)) await actualizarVisor();
    return f;
  }, texto);
}

async function restablecer() {
  const f = fotoActual();
  if (!f) return;
  clearTimeout(D.timer);
  D.cambios = {};
  D.espera = null;
  try {
    await enviarRender(f.id, { ajustes: {}, reemplazar: true });
    if (S.id === f.id) iniciarControles();
    avisar('Ajustes restablecidos.', 'ok');
  } catch (e) { /* aviso ya mostrado */ }
}

/* ---- giro de 90 grados (detalle y rejilla) ---- */

/** Icono de flecha curva (sentido -1 = izquierda, 1 = derecha), clonado de las plantillas del HTML. */
function iconoGiro(sentido) {
  return $(sentido < 0 ? '#tpl-giro-izq' : '#tpl-giro-der').content.firstElementChild.cloneNode(true);
}

function botonGiro(sentido, clase) {
  const texto = sentido < 0 ? 'Girar a la izquierda' : 'Girar a la derecha';
  return crear('button', { type: 'button', class: clase, 'data-sentido': String(sentido), title: texto, 'aria-label': texto }, iconoGiro(sentido));
}

function marcarGirando(id, delta) {
  const n = (S.girando.get(id) || 0) + delta;
  if (n > 0) S.girando.set(id, n);
  else S.girando.delete(id);
  const f = S.porId.get(id);
  if (f) tarjetaActualizar(f);
  if (S.vista === 'detalle' && S.id === id) pintarCabeceraDetalle();
}

/** Gira la foto 90 grados: sentido 1 = horario (derecha), -1 = antihorario (izquierda). */
async function girar(id, sentido) {
  const f = S.porId.get(id);
  if (!f || S.cerrada) return;
  if (!f.analizada && modeloBloquea()) {
    avisar('El modelo de IA aún se está descargando: no se puede girar una foto sin analizar todavía.');
    return;
  }
  const enDetalle = S.vista === 'detalle' && S.id === id;
  if (enDetalle && P.id === id && P.historia.length) {
    const ok = await confirmar('Tienes trazos de pincel sin aplicar en esta foto. Si la giras, se perderán.', {
      titulo: 'Trazos sin aplicar',
      si: 'Girar y descartar',
      no: 'Seguir pintando',
    });
    if (!ok) return;
  }
  marcarGirando(id, 1);
  try {
    if (enDetalle) {
      await vaciarCambios(); // los ajustes pendientes de los deslizadores van antes del giro
      const seq = ++D.seq;
      await encolar(async () => {
        const g = guardarFoto(await api('POST', `/api/fotos/${id}/girar`, { sentido }));
        if (P.id === id && P.giro !== giroDe(g)) pintorLimpiar(); // se descartan trazos, capas y máscara antiguos
        if (esVigente(id, seq)) await actualizarVisor();
        return g;
      }, 'Girando la foto...');
    } else {
      guardarFoto(await api('POST', `/api/fotos/${id}/girar`, { sentido }));
    }
  } catch (e) { /* aviso ya mostrado */ } finally {
    marcarGirando(id, -1);
  }
}

async function cambiarPresetFoto(nombre) {
  const f = fotoActual();
  if (!f || nombre === f.preset) return;
  await vaciarCambios();
  try {
    await enviarRender(f.id, { preset: nombre });
    D.base = await presetBase(nombre);
    if (S.id === f.id) iniciarControles();
  } catch (e) {
    rellenarSelect($('#sel-preset-foto'), { valor: f.preset });
  }
}

async function guardarEnPreset() {
  const f = fotoActual();
  if (!f) return;
  await vaciarCambios();
  await D.cola;
  const actual = fotoActual();
  const cambios = actual && actual.ajustes ? actual.ajustes.preset : null;
  const partes = [];
  for (const def of AJUSTES) {
    if (!def.ruta.startsWith('preset.') || !cambios) continue;
    const v = obtener(cambios, def.ruta.slice(7));
    if (typeof v === 'number') partes.push(`${def.et} ${def.fmt(v)}`);
  }
  if (!cambios || !Object.keys(cambios).length) {
    avisar('Esta foto no tiene cambios de retoque ni de color que guardar en el preset.');
    return;
  }
  const ok = await confirmar(
    `Se guardarán en el preset "${actual.preset}" estos valores: ${partes.join(', ') || 'los cambios de esta foto'}. Las fotos que se procesen con este preset saldrán así.`,
    { titulo: 'Guardar en el preset', si: 'Guardar en el preset', no: 'Cancelar' }
  );
  if (!ok) return;
  try {
    await api('PUT', '/api/presets/' + encodeURIComponent(actual.preset), cambios);
  } catch (e) {
    return;
  }
  S.cachePresets.delete(actual.preset);
  D.base = await presetBase(actual.preset);
  if (S.id === actual.id) iniciarControles();
  avisar(`Preset "${actual.preset}" actualizado.`, 'ok');
}

/* ---- cabecera, informacion y visor ---- */

function vecino(delta) {
  const idx = S.fotos.findIndex((f) => f.id === S.id);
  if (idx < 0) return null;
  const ok = FILTROS[S.filtro] || FILTROS.todas;
  for (let j = idx + delta; j >= 0 && j < S.fotos.length; j += delta) if (ok(S.fotos[j])) return S.fotos[j];
  return null;
}

function pintarCabeceraDetalle() {
  const f = fotoActual();
  if (!f) return;
  $('#d-nombre').textContent = f.carpeta ? `${f.carpeta}/${f.nombre}` : f.nombre;
  $('#d-nombre').title = f.ruta;
  const [clase, texto] = estadoVisible(f);
  const ins = $('#d-estado');
  ins.className = 'insignia-estado' + (clase ? ' ' + clase : '');
  ins.textContent = texto;
  const vis = visibles();
  const i = vis.findIndex((x) => x.id === f.id);
  $('#d-pos').textContent = i >= 0 ? `${i + 1} de ${vis.length}` : `fuera del filtro (${S.fotos.length} en total)`;
  $('#d-ant').disabled = !vecino(-1);
  $('#d-sig').disabled = !vecino(1);
  const b = $('#d-aprobar');
  b.disabled = f.estado !== 'lista';
  b.classList.toggle('aprobada', !!f.aprobada);
  b.replaceChildren(...(f.aprobada ? ['Aprobada (quitar)'] : ['Aprobar y siguiente ', crear('kbd', { texto: 'A' })]));
  b.title = f.aprobada ? 'Quitar la aprobación (A)' : 'Aprobar y pasar a la siguiente (A)';
}

function pintarInfo() {
  const f = fotoActual();
  if (!f) return;
  const info = f.info || {};
  const filas = [
    ['Preset', f.preset],
    ['Ángulo automático', info.angulo_auto != null ? num(info.angulo_auto, 1) + '°' : '-'],
    ['Ángulo aplicado', info.angulo != null ? num(info.angulo, 1) + '°' : '-'],
    ['Ampliación', info.escala != null ? num(info.escala, 2) + 'x' : '-'],
    ['Tiempo de render', info.segundos != null ? num(info.segundos, 1) + ' s' : '-'],
    ['Imagen de trabajo', f.ancho ? `${f.ancho} x ${f.alto}` : 'sin analizar'],
    ['Giro', ['ninguno', '90° a la derecha', '180°', '90° a la izquierda'][giroDe(f) % 4]],
  ];
  $('#info-foto').replaceChildren(...filas.flatMap(([k, v]) => [crear('dt', { texto: k }), crear('dd', { texto: String(v) })]));
  const e = $('#info-error');
  e.hidden = !f.error;
  e.textContent = f.error || '';
}

function botonProcesarFoto(f, texto, textoOcupado) {
  const b = crear('button', {
    type: 'button',
    class: 'btn primario',
    'data-procesar-foto': '1',
    onclick: () => {
      if (modeloBloquea()) {
        avisar(TEXTO_ESPERA_MODELO);
        return;
      }
      enviarRender(f.id, {}, textoOcupado).catch(() => {});
    },
    texto,
  });
  b.disabled = modeloBloquea();
  if (b.disabled) b.title = TEXTO_ESPERA_MODELO;
  return b;
}

function mensajeResultado(contenedor, f, compacto) {
  contenedor.replaceChildren();
  if (f.estado === 'error') {
    contenedor.append(crear('strong', { texto: 'No se ha podido procesar esta foto.' }));
    if (f.error && !compacto) contenedor.append(crear('div', { class: 'aviso-error', texto: f.error }));
    contenedor.append(botonProcesarFoto(f, 'Reintentar', undefined));
  } else {
    contenedor.append(crear('strong', { texto: 'Esta foto todavía no está procesada.' }));
    if (!compacto) contenedor.append(crear('span', { texto: 'Pulsa el botón para pasarle la IA ahora (tarda unos segundos), o usa "Procesar pendientes" en la rejilla.' }));
    contenedor.append(botonProcesarFoto(f, 'Procesar esta foto', 'Procesando la foto...'));
  }
}

function mostrarResultadoEn(img, msg, f, compacto) {
  if (f.estado === 'lista') {
    msg.hidden = true;
    img.hidden = false;
    return ponerImagen(img, `/img/${f.id}/resultado?v=${f.version}`);
  }
  img.hidden = true;
  soltarImagen(img);
  msg.hidden = false;
  mensajeResultado(msg, f, compacto);
  return Promise.resolve();
}

async function actualizarVisor() {
  const f = fotoActual();
  if (!f) return;
  const id = f.id;
  if (S.modo === 'resultado') {
    await mostrarResultadoEn($('#img-resultado'), $('#msg-resultado'), f, false);
  } else if (S.modo === 'antes') {
    await Promise.all([
      ponerImagen($('#img-antes'), urlOriginal(f, 1600)),
      mostrarResultadoEn($('#img-despues'), $('#msg-despues'), f, true),
    ]);
  } else {
    await pintorEntrar(f);
  }
}

function ponerModo(modo) {
  if (!['resultado', 'antes', 'pintar'].includes(modo)) return;
  S.modo = modo;
  almacen.guardar('modo', modo);
  $$('.modo').forEach((b) => {
    const activo = b.dataset.modo === modo;
    b.classList.toggle('activa', activo);
    b.setAttribute('aria-selected', String(activo));
  });
  $('#pane-resultado').hidden = modo !== 'resultado';
  $('#pane-antes').hidden = modo !== 'antes';
  $('#pane-pintar').hidden = modo !== 'pintar';
  $('#panel-pinceles').hidden = modo !== 'pintar';
  $$('#ajustes details').forEach((d) => { d.open = modo !== 'pintar'; });
  if (modo === 'pintar') herramientasActualizar();
  actualizarVisor();
}

async function mostrarDetalle(id) {
  const f0 = S.porId.get(id);
  if (!f0) {
    avisar('No se encuentra esa foto.', 'error');
    location.hash = '';
    return;
  }
  const cambio = S.id !== id || S.vista !== 'detalle';
  if (S.id && S.id !== id) {
    vaciarCambios();
    pintorLimpiar();
  }
  S.id = id;
  S.ultimo = id;
  mostrarVista('detalle');
  pintarCabeceraDetalle();
  if (cambio) {
    try {
      guardarFoto(await api('GET', '/api/fotos/' + encodeURIComponent(id), undefined, { silencioso: true }));
    } catch (e) { /* se usa la copia de la lista */ }
    if (S.id !== id) return;
    const f = fotoActual();
    try { D.base = await presetBase(f.preset); } catch (e) { D.base = null; }
    if (S.id !== id) return;
    iniciarControles();
    rellenarSelectores();
  }
  pintarCabeceraDetalle();
  pintarInfo();
  ponerModo(S.modo);
}

function salirDelDetalle() {
  vaciarCambios();
  pintorLimpiar();
  S.id = null;
}

async function irAVecina(delta) {
  const v = vecino(delta);
  if (v) await navegar('#foto/' + v.id);
}

/** Boton "Aprobar": aprueba y pasa a la siguiente; si ya estaba aprobada, quita la aprobacion. */
async function aprobarActual() {
  const f = fotoActual();
  if (!f) return;
  if (f.estado !== 'lista') {
    avisar('Procesa la foto antes de aprobarla.');
    return;
  }
  if (f.aprobada) {
    await fijarAprobada(f.id, false);
    return;
  }
  await aprobarYSiguiente();
}

/** Tecla A: aprueba (si no lo estaba) y pasa a la siguiente foto del filtro. */
async function aprobarYSiguiente() {
  const f = fotoActual();
  if (!f) return;
  if (f.estado !== 'lista') {
    avisar('Procesa la foto antes de aprobarla.');
    return;
  }
  const sig = vecino(1);
  if (!f.aprobada) await fijarAprobada(f.id, true);
  if (sig) await navegar('#foto/' + sig.id);
  else avisar('Era la última foto del filtro.', 'ok');
}

/* ---------------------------------------------------------------------
   Pintor (pinceles sobre la foto original)
   --------------------------------------------------------------------- */

const TIPOS = [
  { tipo: 'borrar', nombre: 'Borrar objeto', color: '#e5484d', texto: 'La IA borra lo pintado: cables o pinzas encima de la prenda.' },
  { tipo: 'proteger', nombre: 'Proteger defecto', color: '#30b46c', texto: 'Nunca se suaviza: manchas, rotos, bolitas.' },
  { tipo: 'sumar', nombre: 'Es prenda', color: '#3b82f6', texto: 'Esta zona sí es prenda: úsalo si el recorte se ha comido una parte.' },
  { tipo: 'restar', nombre: 'No es prenda', color: '#f08a24', texto: 'Percha, mano, pinza: se quita del recorte.' },
];

const P = {
  id: null,
  giro: null, // giro90 de la foto cuando se cargo la imagen
  token: 0,
  listo: false,
  W: 0,
  H: 0,
  capas: {}, // tipo -> {canvas, ctx, base}
  historia: [], // trazos aun sin aplicar (de cualquier capa)
  rehacer: [],
  activo: 'borrar',
  goma: false,
  tam: 48,
  s: 1,
  fit: 1,
  tx: 0,
  ty: 0,
  ajustado: true,
  espacio: false,
  trazo: null,
  mover: null,
  mascara: false,
  mascaraV: null,
  ratonX: null,
  ratonY: null,
};

const colorDe = (tipo) => TIPOS.find((t) => t.tipo === tipo).color;
const sucia = (tipo) => P.historia.some((t) => t.tipo === tipo);

function tamDesdeControl(v) {
  return Math.round(2 * Math.pow(200, v / 100)); // 2 .. 400 px, escala logaritmica
}
function controlDesdeTam(px) {
  return (100 * Math.log(px / 2)) / Math.log(200);
}

function construirPinceles() {
  const lista = $('#lista-pinceles');
  for (const t of TIPOS) {
    const b = crear(
      'button',
      { type: 'button', class: 'pincel', 'data-tipo': t.tipo },
      crear('span', { class: 'punto' }),
      crear('span', { class: 'nom', texto: t.nombre }),
      crear('span', { class: 'marca-estado' }),
      crear('span', { class: 'txt', texto: t.texto })
    );
    b.style.setProperty('--color', t.color);
    b.addEventListener('click', () => {
      P.activo = t.tipo;
      P.goma = false;
      herramientasActualizar();
    });
    lista.append(b);
  }
  const tam = $('#pincel-tam');
  tam.value = String(Math.round(controlDesdeTam(P.tam)));
  tam.addEventListener('input', () => ponerTam(tamDesdeControl(parseFloat(tam.value))));
  tam.addEventListener('pointerup', () => tam.blur());
  $('#p-goma').addEventListener('click', () => { P.goma = !P.goma; herramientasActualizar(); });
  $('#p-deshacer').addEventListener('click', deshacer);
  $('#p-rehacer').addEventListener('click', rehacer);
  $('#p-aplicar').addEventListener('click', aplicarPincel);
  $('#p-quitar').addEventListener('click', quitarCapa);
  $('#p-mascara').addEventListener('change', (e) => ponerMascara(e.target.checked));
  $('#z-mas').addEventListener('click', () => zoomCentro(1.25));
  $('#z-menos').addEventListener('click', () => zoomCentro(0.8));
  $('#z-ajustar').addEventListener('click', () => ajustarVista());

  const pintor = $('#pintor');
  pintor.addEventListener('pointerdown', pintorAbajo);
  pintor.addEventListener('pointermove', pintorMueve);
  pintor.addEventListener('pointerup', pintorArriba);
  pintor.addEventListener('pointercancel', pintorArriba);
  pintor.addEventListener('pointerenter', (e) => { actualizarCursor(e); });
  pintor.addEventListener('pointerleave', () => { if (!P.trazo) $('#cursor-pincel').hidden = true; });
  pintor.addEventListener('wheel', pintorRueda, { passive: false });
  pintor.addEventListener('contextmenu', (e) => e.preventDefault());
  pintor.addEventListener('mousedown', (e) => { if (e.button === 1) e.preventDefault(); });
  new ResizeObserver(() => { if (P.listo && P.ajustado) ajustarVista(); }).observe(pintor);
}

function ponerTam(px) {
  P.tam = limitar(Math.round(px), 2, 400);
  $('#pincel-tam').value = String(Math.round(controlDesdeTam(P.tam)));
  $('#pincel-tam-valor').textContent = P.tam + ' px';
  actualizarCursor();
}

function cambiarTam(factor) {
  const nuevo = factor > 1 ? Math.max(P.tam + 1, Math.round(P.tam * factor)) : Math.min(P.tam - 1, Math.round(P.tam * factor));
  ponerTam(nuevo);
}

function herramientasActualizar() {
  const f = fotoActual();
  $$('.pincel').forEach((b) => {
    const t = b.dataset.tipo;
    b.classList.toggle('activo', t === P.activo && !P.goma);
    const m = $('.marca-estado', b);
    const s = P.id === S.id && sucia(t);
    const aplicada = !!(f && f.pinceles && f.pinceles[t]);
    m.className = 'marca-estado' + (s ? ' sucio' : aplicada ? ' aplicada' : '');
    m.textContent = s ? 'sin aplicar' : aplicada ? 'aplicada' : '';
  });
  const goma = $('#p-goma');
  goma.setAttribute('aria-pressed', String(P.goma));
  const hayFoto = P.id === S.id;
  $('#p-deshacer').disabled = !(hayFoto && P.historia.length);
  $('#p-rehacer').disabled = !(hayFoto && P.rehacer.length);
  $('#p-aplicar').disabled = !(hayFoto && sucia(P.activo));
  $('#p-quitar').disabled = !((f && f.pinceles && f.pinceles[P.activo]) || (hayFoto && sucia(P.activo)));
  const nombre = TIPOS.find((t) => t.tipo === P.activo).nombre;
  $('#p-aplicar').textContent = 'Aplicar pincel';
  $('#p-aplicar').title = `Envía la capa "${nombre}" y rehace la foto`;
  $('#pincel-tam-valor').textContent = P.tam + ' px';
  $('#p-estado').textContent = P.goma
    ? `Goma sobre la capa "${nombre}".`
    : `Pintando en "${nombre}". Los trazos no cuentan hasta que pulses "Aplicar pincel".`;
  $('#z-valor').textContent = Math.round(P.s * 100) + ' %';
  actualizarCursor();
}

function asegurarCapa(tipo) {
  if (P.capas[tipo]) return P.capas[tipo];
  const canvas = document.createElement('canvas');
  canvas.width = P.W;
  canvas.height = P.H;
  canvas.dataset.tipo = tipo;
  canvas.style.zIndex = String(TIPOS.findIndex((t) => t.tipo === tipo) + 1);
  $('#capas').append(canvas);
  const capa = { canvas, ctx: canvas.getContext('2d'), base: null };
  P.capas[tipo] = capa;
  return capa;
}

function copiaCanvas(origen) {
  const c = document.createElement('canvas');
  c.width = origen.width;
  c.height = origen.height;
  c.getContext('2d').drawImage(origen, 0, 0);
  return c;
}

function pintorLimpiar() {
  P.token++;
  P.id = null;
  P.giro = null;
  P.listo = false;
  P.capas = {};
  P.historia = [];
  P.rehacer = [];
  P.trazo = null;
  P.mover = null;
  $('#capas').replaceChildren();
  const mc = $('#mascara-canvas');
  mc.width = 1;
  mc.height = 1;
  mc.hidden = true;
  P.mascaraV = null;
  soltarImagen($('#pintor-img'));
  $('#cursor-pincel').hidden = true;
}

async function pintorEntrar(f) {
  if (P.id === f.id && P.giro !== giroDe(f)) pintorLimpiar(); // la foto se ha girado: ancho, alto y capas son otros
  if (P.id === f.id && P.listo) {
    if (P.ajustado) ajustarVista();
    else aplicarVista();
    if (P.mascara && P.mascaraV !== f.version) cargarMascara();
    herramientasActualizar();
    return;
  }
  if (P.id === f.id && !P.listo) return; // ya se esta cargando
  pintorLimpiar();
  P.id = f.id;
  const token = P.token;
  const img = $('#pintor-img');
  P.giro = giroDe(f);
  const ok = await ponerImagen(img, urlOriginal(S.porId.get(f.id) || f));
  if (token !== P.token) return;
  if (!ok) {
    P.id = null;
    return;
  }
  P.W = img.naturalWidth;
  P.H = img.naturalHeight;
  const mundo = $('#mundo');
  mundo.style.width = P.W + 'px';
  mundo.style.height = P.H + 'px';
  const mc = $('#mascara-canvas');
  mc.width = P.W;
  mc.height = P.H;
  const actual = S.porId.get(f.id) || f;
  for (const t of TIPOS) {
    if (actual.pinceles && actual.pinceles[t.tipo]) {
      await cargarCapaServidor(t.tipo, token);
      if (token !== P.token) return;
    }
  }
  P.listo = true;
  mc.hidden = !P.mascara;
  ajustarVista();
  herramientasActualizar();
  if (P.mascara) cargarMascara();
}

async function cargarCapaServidor(tipo, token) {
  const r = await fetch(`/img/${P.id}/pincel/${tipo}?t=${Date.now()}`);
  if (!r.ok) return;
  const bmp = await createImageBitmap(await r.blob());
  if (token !== P.token) return;
  const tmp = document.createElement('canvas');
  tmp.width = P.W;
  tmp.height = P.H;
  const c = tmp.getContext('2d', { willReadFrequently: true });
  c.drawImage(bmp, 0, 0, P.W, P.H);
  const datos = c.getImageData(0, 0, P.W, P.H);
  const d = datos.data;
  const [rr, gg, bb] = hexARgb(colorDe(tipo));
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i]; // la capa del servidor es gris: blanco = pintado
    d[i] = rr;
    d[i + 1] = gg;
    d[i + 2] = bb;
    d[i + 3] = a;
  }
  c.putImageData(datos, 0, 0);
  const capa = asegurarCapa(tipo);
  capa.ctx.clearRect(0, 0, P.W, P.H);
  capa.ctx.drawImage(tmp, 0, 0);
  capa.base = tmp;
}

/* ---- trazos ---- */

function estiloTrazo(ctx, t) {
  ctx.globalCompositeOperation = t.goma ? 'destination-out' : 'source-over';
  ctx.globalAlpha = 1;
  ctx.strokeStyle = ctx.fillStyle = colorDe(t.tipo);
  ctx.lineWidth = t.tam;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
}

function dibujarTrazo(ctx, t) {
  ctx.save();
  estiloTrazo(ctx, t);
  const p = t.pts;
  ctx.beginPath();
  if (p.length <= 2) {
    ctx.arc(p[0], p[1], t.tam / 2, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.moveTo(p[0], p[1]);
    for (let i = 2; i < p.length; i += 2) ctx.lineTo(p[i], p[i + 1]);
    ctx.stroke();
  }
  ctx.restore();
}

function redibujarCapa(tipo) {
  const capa = P.capas[tipo];
  if (!capa) return;
  capa.ctx.clearRect(0, 0, P.W, P.H);
  if (capa.base) capa.ctx.drawImage(capa.base, 0, 0);
  for (const t of P.historia) if (t.tipo === tipo) dibujarTrazo(capa.ctx, t);
}

function aNatural(e, rect) {
  const r = rect || $('#mundo').getBoundingClientRect();
  return [((e.clientX - r.left) * P.W) / r.width, ((e.clientY - r.top) * P.H) / r.height];
}

function pintorAbajo(e) {
  if (!P.listo || P.id !== S.id) return;
  const pintor = $('#pintor');
  if (e.button === 1 || (e.button === 0 && P.espacio)) {
    P.mover = { x: e.clientX, y: e.clientY, tx: P.tx, ty: P.ty };
    pintor.classList.add('moviendo');
    pintor.setPointerCapture(e.pointerId);
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;
  pintor.setPointerCapture(e.pointerId);
  const [x, y] = aNatural(e);
  const capa = asegurarCapa(P.activo);
  P.trazo = { tipo: P.activo, goma: P.goma, tam: P.tam, pts: [x, y] };
  dibujarTrazo(capa.ctx, P.trazo);
  e.preventDefault();
}

function pintorMueve(e) {
  actualizarCursor(e);
  if (P.mover) {
    P.tx = P.mover.tx + (e.clientX - P.mover.x);
    P.ty = P.mover.ty + (e.clientY - P.mover.y);
    aplicarVista();
    return;
  }
  const t = P.trazo;
  if (!t) return;
  const capa = P.capas[t.tipo];
  const rect = $('#mundo').getBoundingClientRect();
  const eventos = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  const lista = eventos.length ? eventos : [e];
  const ctx = capa.ctx;
  ctx.save();
  estiloTrazo(ctx, t);
  for (const ev of lista) {
    const [x, y] = aNatural(ev, rect);
    const n = t.pts.length;
    const px = t.pts[n - 2];
    const py = t.pts[n - 1];
    if (x === px && y === py) continue;
    t.pts.push(x, y);
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(x, y);
    ctx.stroke();
  }
  ctx.restore();
}

function pintorArriba(e) {
  const pintor = $('#pintor');
  if (P.mover) {
    P.mover = null;
    pintor.classList.remove('moviendo');
  }
  if (P.trazo) {
    P.historia.push(P.trazo);
    P.rehacer = [];
    P.trazo = null;
    herramientasActualizar();
  }
  if (pintor.hasPointerCapture && pintor.hasPointerCapture(e.pointerId)) pintor.releasePointerCapture(e.pointerId);
}

function deshacer() {
  if (P.id !== S.id || !P.historia.length) return;
  const t = P.historia.pop();
  P.rehacer.push(t);
  redibujarCapa(t.tipo);
  herramientasActualizar();
}

function rehacer() {
  if (P.id !== S.id || !P.rehacer.length) return;
  const t = P.rehacer.pop();
  P.historia.push(t);
  dibujarTrazo(asegurarCapa(t.tipo).ctx, t);
  herramientasActualizar();
}

/* ---- cursor, zoom y desplazamiento ---- */

function actualizarCursor(e) {
  const c = $('#cursor-pincel');
  if (e && e.clientX !== undefined) {
    const r = $('#pintor').getBoundingClientRect();
    P.ratonX = e.clientX - r.left;
    P.ratonY = e.clientY - r.top;
  }
  if (S.modo !== 'pintar' || !P.listo || P.ratonX == null || P.espacio || P.mover) {
    c.hidden = true;
    return;
  }
  const d = Math.max(4, P.tam * P.s);
  c.hidden = false;
  c.style.width = c.style.height = d + 'px';
  c.style.left = P.ratonX + 'px';
  c.style.top = P.ratonY + 'px';
  c.style.borderColor = P.goma ? '#ffffff' : colorDe(P.activo);
  c.classList.toggle('goma', P.goma);
}

function aplicarVista() {
  const r = $('#pintor').getBoundingClientRect();
  const margen = 80;
  P.tx = limitar(P.tx, margen - P.W * P.s, r.width - margen);
  P.ty = limitar(P.ty, margen - P.H * P.s, r.height - margen);
  $('#mundo').style.transform = `translate(${P.tx}px, ${P.ty}px) scale(${P.s})`;
  $('#z-valor').textContent = Math.round(P.s * 100) + ' %';
  actualizarCursor();
}

function ajustarVista() {
  const r = $('#pintor').getBoundingClientRect();
  if (!r.width || !r.height || !P.W) return;
  P.fit = Math.min(r.width / P.W, r.height / P.H) * 0.98;
  P.s = P.fit;
  P.tx = (r.width - P.W * P.s) / 2;
  P.ty = (r.height - P.H * P.s) / 2;
  P.ajustado = true;
  aplicarVista();
}

function zoomEn(factor, cx, cy) {
  if (!P.listo) return;
  const maximo = Math.max(8, P.fit * 4);
  const nuevo = limitar(P.s * factor, P.fit, maximo);
  if (nuevo === P.s) return;
  const wx = (cx - P.tx) / P.s;
  const wy = (cy - P.ty) / P.s;
  P.s = nuevo;
  P.tx = cx - wx * nuevo;
  P.ty = cy - wy * nuevo;
  P.ajustado = false;
  if (Math.abs(nuevo - P.fit) < 1e-6) {
    ajustarVista();
    return;
  }
  aplicarVista();
}

function zoomCentro(factor) {
  const r = $('#pintor').getBoundingClientRect();
  zoomEn(factor, r.width / 2, r.height / 2);
}

function pintorRueda(e) {
  if (!P.listo) return;
  e.preventDefault();
  const r = $('#pintor').getBoundingClientRect();
  zoomEn(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
}

/* ---- mascara ---- */

function ponerMascara(visible) {
  P.mascara = visible;
  $('#p-mascara').checked = visible;
  $('#mascara-canvas').hidden = !visible;
  if (visible && P.listo) cargarMascara();
}

async function cargarMascara() {
  const id = P.id;
  const token = P.token;
  if (!id || !P.listo) return;
  const version = (S.porId.get(id) || {}).version;
  try {
    await encolar(async () => {
      const r = await fetch(`/img/${id}/mascara?t=${Date.now()}`);
      if (!r.ok) throw new Error('mascara ' + r.status);
      const bmp = await createImageBitmap(await r.blob());
      if (token !== P.token) return;
      const mc = $('#mascara-canvas');
      const c = mc.getContext('2d', { willReadFrequently: true });
      c.clearRect(0, 0, mc.width, mc.height);
      c.drawImage(bmp, 0, 0, mc.width, mc.height);
      const datos = c.getImageData(0, 0, mc.width, mc.height);
      const d = datos.data;
      for (let i = 0; i < d.length; i += 4) {
        const g = d[i]; // blanco = prenda: se sombrea lo que NO es prenda
        d[i] = 150;
        d[i + 1] = 40;
        d[i + 2] = 200;
        d[i + 3] = Math.round((255 - g) * 0.5);
      }
      c.putImageData(datos, 0, 0);
      P.mascaraV = version;
    }, 'Calculando la máscara...');
  } catch (e) {
    avisar('No se ha podido cargar la máscara.', 'error');
  }
}

/* ---- aplicar / quitar ---- */

async function aplicarPincel() {
  const tipo = P.activo;
  const id = P.id;
  if (id !== S.id || !sucia(tipo)) return;
  const canvas = P.capas[tipo].canvas;
  const blob = await new Promise((res) => canvas.toBlob(res, 'image/png'));
  if (!blob) {
    avisar('No se ha podido preparar el pincel.', 'error');
    return;
  }
  try {
    const f = await encolar(async () => {
      const f2 = guardarFoto(await api('PUT', `/api/fotos/${id}/pincel/${tipo}`, blob));
      return f2;
    }, 'Aplicando el pincel...');
    if (P.id !== id) return;
    P.historia = P.historia.filter((t) => t.tipo !== tipo);
    P.rehacer = P.rehacer.filter((t) => t.tipo !== tipo);
    const capa = P.capas[tipo];
    if (f.pinceles && f.pinceles[tipo]) {
      capa.base = copiaCanvas(capa.canvas);
    } else {
      capa.base = null;
      capa.ctx.clearRect(0, 0, P.W, P.H);
    }
    herramientasActualizar();
    avisar('Pincel aplicado. Pulsa 1 para ver el resultado.', 'ok');
    if (P.mascara) cargarMascara();
  } catch (e) { /* aviso ya mostrado */ }
}

async function quitarCapa() {
  const tipo = P.activo;
  const id = P.id;
  if (id !== S.id) return;
  const f = fotoActual();
  const enServidor = !!(f && f.pinceles && f.pinceles[tipo]);
  const limpiarLocal = () => {
    P.historia = P.historia.filter((t) => t.tipo !== tipo);
    P.rehacer = P.rehacer.filter((t) => t.tipo !== tipo);
    const capa = P.capas[tipo];
    if (capa) {
      capa.base = null;
      capa.ctx.clearRect(0, 0, P.W, P.H);
    }
    herramientasActualizar();
  };
  if (!enServidor) {
    limpiarLocal();
    return;
  }
  try {
    await encolar(async () => guardarFoto(await api('DELETE', `/api/fotos/${id}/pincel/${tipo}`)), 'Quitando la capa...');
    if (P.id !== id) return;
    limpiarLocal();
    avisar('Capa quitada.', 'ok');
    if (P.mascara) cargarMascara();
  } catch (e) { /* aviso ya mostrado */ }
}

/* ---------------------------------------------------------------------
   Presets
   --------------------------------------------------------------------- */

const SECCIONES = [
  { titulo: 'General', ancho: true, campos: [{ r: 'descripcion', et: 'Descripción', t: 'texto' }] },
  {
    titulo: 'Lienzo (tamaño de la foto final)',
    campos: [
      { r: 'lienzo.ancho', et: 'Ancho (px)', t: 'num', min: 300, max: 8000, paso: 10 },
      { r: 'lienzo.alto', et: 'Alto (px)', t: 'num', min: 300, max: 8000, paso: 10 },
    ],
  },
  {
    titulo: 'Orientación',
    campos: [
      {
        r: 'giro_inicial', et: 'Girar las fotos nuevas', t: 'sel', entero: true,
        opciones: [['0', 'No girar'], ['1', '90 grados a la derecha'], ['2', '180 grados'], ['3', '90 grados a la izquierda']],
      },
    ],
    nota: 'Se aplica a las fotos que entren nuevas en la carpeta; las que ya están se giran con R / Mayús+R.',
  },
  {
    titulo: 'Encuadre',
    campos: [
      { r: 'encuadre.relleno', et: 'Relleno (si no hay ancho y alto máximos)', t: 'num', min: 0.3, max: 1, paso: 0.001 },
      { r: 'encuadre.relleno_x', et: 'Ancho máximo de la prenda (fracción del lienzo)', t: 'num', min: 0.2, max: 0.97, paso: 0.001, vacio: true, ph: 'igual que Relleno' },
      { r: 'encuadre.relleno_y', et: 'Alto máximo de la prenda (fracción del lienzo)', t: 'num', min: 0.2, max: 0.97, paso: 0.001, vacio: true, ph: 'igual que Relleno' },
      { r: 'encuadre.centro_x', et: 'Centro horizontal (0,5 = centrada)', t: 'num', min: 0, max: 1, paso: 0.001 },
      { r: 'encuadre.centro_y', et: 'Centro vertical (0,5 = centrada)', t: 'num', min: 0, max: 1, paso: 0.001 },
    ],
  },
  {
    titulo: 'Fondo',
    campos: [
      { r: 'fondo.tipo', et: 'Tipo de fondo', t: 'sel', opciones: [['color', 'Color liso'], ['imagen', 'Imagen de fondo'], ['original', 'Mantener el fondo original']] },
      { r: 'fondo.color', et: 'Color', t: 'color' },
      { r: 'fondo.imagen', et: 'Ruta de la imagen de fondo', t: 'texto', ph: 'por ejemplo: fondos/madera.jpg' },
    ],
  },
  {
    titulo: 'Sombra',
    campos: [
      { r: 'sombra.opacidad', et: 'Opacidad (0 a 1)', t: 'num', min: 0, max: 1, paso: 0.01 },
      { r: 'sombra.desenfoque', et: 'Desenfoque (relativo a la prenda)', t: 'num', min: 0, max: 0.3, paso: 0.005 },
      { r: 'sombra.desplazamiento_y', et: 'Desplazamiento vertical', t: 'num', min: -0.1, max: 0.1, paso: 0.001 },
    ],
  },
  {
    titulo: 'Arrugas',
    campos: [
      { r: 'arrugas.fuerza', et: 'Fuerza (0 a 1)', t: 'num', min: 0, max: 1, paso: 0.05 },
      { r: 'arrugas.escala', et: 'Escala de las arrugas', t: 'num', min: 0.005, max: 0.3, paso: 0.005 },
      { r: 'arrugas.respeto_bordes', et: 'Respeto a los bordes (0 a 1)', t: 'num', min: 0, max: 1, paso: 0.05 },
    ],
  },
  {
    titulo: 'Enderezado',
    campos: [
      { r: 'enderezar.activo', et: 'Enderezar la prenda automáticamente', t: 'check' },
      { r: 'enderezar.max_grados', et: 'Máximo de grados que puede girar', t: 'num', min: 0, max: 15, paso: 0.5 },
    ],
  },
  {
    titulo: 'Nitidez y color',
    campos: [
      { r: 'nitidez', et: 'Nitidez (0 a 1)', t: 'num', min: 0, max: 1, paso: 0.05 },
      { r: 'color.igualar_con_fondo', et: 'Igualar el color con el fondo del lote', t: 'check' },
      { r: 'color.balance_blancos', et: 'Balance de blancos con el fondo', t: 'check' },
    ],
  },
];

const PV = { nombre: null, datos: null, sucio: false };

function construirFormPreset() {
  const cont = $('#preset-campos');
  for (const sec of SECCIONES) {
    const fs = crear('fieldset', { class: 'grupo-preset' + (sec.ancho ? ' ancho' : '') }, crear('legend', { texto: sec.titulo }));
    for (const c of sec.campos) {
      const id = 'pf-' + c.r.replace(/\./g, '-');
      let ctrl;
      if (c.t === 'num') {
        ctrl = crear('input', {
          type: 'number', id, min: c.min, max: c.max, step: c.paso, placeholder: c.ph || '',
          'data-ruta': c.r, 'data-tipo': 'num', 'data-et': c.et.split(' (')[0], 'data-vacio': c.vacio ? 'nulo' : '',
        });
      }
      else if (c.t === 'texto') ctrl = crear('input', { type: 'text', id, placeholder: c.ph || '', 'data-ruta': c.r, 'data-tipo': 'texto' });
      else if (c.t === 'sel') {
        ctrl = crear('select', { id, 'data-ruta': c.r, 'data-tipo': 'sel', 'data-entero': c.entero ? '1' : '' }, c.opciones.map(([v, n]) => crear('option', { value: v, texto: n })));
      } else if (c.t === 'check') {
        ctrl = crear('input', { type: 'checkbox', id, 'data-ruta': c.r, 'data-tipo': 'check' });
        fs.append(crear('label', { class: 'campo campo-check', for: id }, ctrl, c.et));
        continue;
      } else if (c.t === 'color') {
        const picker = crear('input', { type: 'color', id, 'data-ruta': c.r, 'data-tipo': 'color', 'aria-label': 'Elegir color' });
        const texto = crear('input', { type: 'text', id: id + '-hex', maxlength: '7', placeholder: '#F4F4F2', 'aria-label': 'Color en hexadecimal' });
        picker.addEventListener('input', () => { texto.value = picker.value.toUpperCase(); });
        texto.addEventListener('input', () => {
          if (/^#[0-9a-f]{6}$/i.test(texto.value)) picker.value = texto.value.toLowerCase();
        });
        fs.append(crear('label', { class: 'campo', for: id }, c.et, crear('div', { class: 'campo-color' }, picker, texto)));
        continue;
      }
      fs.append(crear('label', { class: 'campo', for: id }, c.et, ctrl));
      if (c.r === 'fondo.imagen') fs.append(crear('p', { class: 'ayuda', id: 'pf-fondo-nota', hidden: true }));
    }
    if (sec.nota) fs.append(crear('p', { class: 'ayuda', texto: sec.nota }));
    cont.append(fs);
  }
  const tipoFondo = $('#pf-fondo-tipo');
  tipoFondo.addEventListener('change', fondoAjustarCampos);
  $('#pf-fondo-imagen').addEventListener('input', fondoAjustarCampos);
  $('#form-preset').addEventListener('input', () => marcarPresetSucio(true));
  $('#form-preset').addEventListener('change', () => marcarPresetSucio(true));
}

function fondoAjustarCampos() {
  const t = $('#pf-fondo-tipo').value;
  $('#pf-fondo-color').disabled = t !== 'color';
  $('#pf-fondo-color-hex').disabled = t !== 'color';
  $('#pf-fondo-imagen').disabled = t !== 'imagen';
  const nota = $('#pf-fondo-nota');
  const ruta = $('#pf-fondo-imagen').value.trim();
  nota.hidden = t !== 'imagen';
  nota.textContent = ruta
    ? `Este preset usa como fondo la imagen "${ruta}" (la ruta es relativa a la carpeta de datos de EDITFOTO, Documentos\\EDITFOTO). Aquí no se muestra una vista previa.`
    : 'Este preset usa una imagen de fondo, pero todavía no has indicado su ruta.';
}

function marcarPresetSucio(v) {
  PV.sucio = v;
  $('#preset-sucio').hidden = !v;
}

function rellenarFormPreset(preset) {
  PV.datos = preset;
  $('#preset-titulo').textContent = 'Preset: ' + preset.nombre;
  for (const el of $$('#preset-campos [data-ruta]')) {
    const v = obtener(preset, el.dataset.ruta);
    const tipo = el.dataset.tipo;
    if (tipo === 'check') el.checked = !!v;
    else if (tipo === 'color') {
      const hex = /^#[0-9a-f]{6}$/i.test(v || '') ? v.toLowerCase() : '#f4f4f2';
      el.value = hex;
      $('#' + el.id + '-hex').value = hex.toUpperCase();
    } else if (el.dataset.entero) {
      const n = Math.round(Number(v));
      el.value = String(Number.isFinite(n) ? ((n % 4) + 4) % 4 : 0);
    } else el.value = v == null ? '' : v;
  }
  fondoAjustarCampos();
  marcarPresetSucio(false);
}

/** Revisa los campos numéricos del formulario; devuelve el primero que no sea válido, o null. */
function campoPresetInvalido() {
  for (const el of $$('#preset-campos input[data-tipo="num"]')) {
    const nombre = el.dataset.et || 'Este campo';
    if (el.validity.badInput) return { el, texto: `${nombre} tiene que ser un número.` };
    if (el.value.trim() === '') continue;
    const v = parseFloat(el.value);
    const min = parseFloat(el.min);
    const max = parseFloat(el.max);
    if (Number.isNaN(v) || (!Number.isNaN(min) && v < min) || (!Number.isNaN(max) && v > max)) {
      const f = (x) => x.toLocaleString('es-ES', { maximumFractionDigits: 3 });
      return { el, texto: `${nombre} tiene que estar entre ${f(min)} y ${f(max)}.` };
    }
  }
  return null;
}

function leerFormPreset() {
  const salida = {};
  for (const el of $$('#preset-campos [data-ruta]')) {
    const tipo = el.dataset.tipo;
    let v;
    if (tipo === 'check') v = el.checked;
    else if (tipo === 'num') {
      v = parseFloat(el.value);
      if (Number.isNaN(v)) {
        if (el.dataset.vacio !== 'nulo') continue;
        v = null; // campo opcional vacío: el preset vuelve a usar el valor general
      }
    } else if (tipo === 'color') {
      const hex = $('#' + el.id + '-hex').value;
      v = /^#[0-9a-f]{6}$/i.test(hex) ? hex.toUpperCase() : el.value.toUpperCase();
    } else if (el.dataset.entero) v = parseInt(el.value, 10) || 0;
    else v = el.value;
    fijar(salida, el.dataset.ruta, v);
  }
  return salida;
}

function pintarListaPresets() {
  const ul = $('#presets-lista');
  ul.replaceChildren();
  for (const n of S.presets) {
    const b = crear(
      'button',
      { type: 'button', class: n === PV.nombre ? 'activo' : '' },
      crear('strong', { texto: n }),
      crear('small', { texto: S.descripciones[n] || 'Sin descripción' })
    );
    b.addEventListener('click', () => presetAbrir(n));
    ul.append(crear('li', {}, b));
  }
}

async function presetAbrir(nombre, { forzar = false } = {}) {
  if (!forzar && PV.sucio && nombre !== PV.nombre) {
    const ok = await confirmar(`Tienes cambios sin guardar en el preset "${PV.nombre}". ¿Descartarlos?`, { titulo: 'Cambios sin guardar', si: 'Descartar', no: 'Seguir editando' });
    if (!ok) return;
  }
  try {
    const p = await api('GET', '/api/presets/' + encodeURIComponent(nombre));
    PV.nombre = nombre;
    S.cachePresets.set(nombre, p);
    rellenarFormPreset(p);
    pintarListaPresets();
  } catch (e) { /* aviso ya mostrado */ }
}

async function presetsMostrar() {
  try { await cargarPresets(); } catch (e) { return; }
  if (!PV.nombre || !S.presets.includes(PV.nombre)) {
    PV.nombre = S.presets.includes(S.estado && S.estado.preset_por_defecto) ? S.estado.preset_por_defecto : S.presets[0];
    PV.sucio = false;
  }
  pintarListaPresets();
  if (!PV.sucio) await presetAbrir(PV.nombre, { forzar: true });
}

async function presetGuardar(ev) {
  ev.preventDefault();
  if (!PV.nombre) return;
  const malo = campoPresetInvalido();
  if (malo) {
    avisar(malo.texto, 'error');
    malo.el.focus();
    return;
  }
  try {
    const guardado = await api('PUT', '/api/presets/' + encodeURIComponent(PV.nombre), leerFormPreset());
    S.cachePresets.set(PV.nombre, guardado);
    if (D.base && fotoActual() && fotoActual().preset === PV.nombre) D.base = guardado;
    rellenarFormPreset(guardado);
    await cargarPresets();
    pintarListaPresets();
    avisar(`Preset "${PV.nombre}" guardado. Para aplicarlo a las fotos ya hechas usa "Rehacer todas".`, 'ok');
  } catch (e) { /* aviso ya mostrado */ }
}

async function presetCrear(ev) {
  ev.preventDefault();
  const nombre = nombreValido($('#nuevo-nombre').value);
  if (!nombre) {
    avisar('Escribe un nombre para el preset nuevo.', 'error');
    return;
  }
  if (S.presets.includes(nombre)) {
    avisar(`Ya existe un preset llamado "${nombre}".`, 'error');
    return;
  }
  try {
    const base = await api('GET', '/api/presets/' + encodeURIComponent($('#nuevo-base').value));
    delete base.nombre;
    const nuevo = await api('PUT', '/api/presets/' + encodeURIComponent(nombre), base);
    $('#nuevo-nombre').value = '';
    await cargarPresets();
    PV.nombre = nuevo.nombre;
    PV.sucio = false;
    pintarListaPresets();
    rellenarFormPreset(nuevo);
    avisar(`Preset "${nuevo.nombre}" creado.`, 'ok');
  } catch (e) { /* aviso ya mostrado */ }
}

async function presetAprender(ev) {
  ev.preventDefault();
  const nombre = nombreValido($('#aprender-nombre').value);
  if ($('#aprender-nombre').value.trim() && !nombre) {
    avisar('Ese nombre no es válido: usa letras, números o guiones bajos.', 'error');
    return;
  }
  const cuerpo = {};
  if (nombre) {
    cuerpo.nombre = nombre;
    cuerpo.base = $('#aprender-base').value || 'generico';
  }
  const carpeta = $('#aprender-carpeta').value.trim();
  if (carpeta) cuerpo.carpeta = carpeta;
  const boton = $('#aprender-boton');
  boton.disabled = true;
  $('#aprender-ocupado').hidden = false;
  $('#aprender-estado').textContent = '';
  $('#aprender-resumen').hidden = true;
  try {
    const r = await api('POST', '/api/aprender', cuerpo);
    const resumen = r.resumen || {};
    const lineas = Array.isArray(resumen.texto) ? resumen.texto : [String(resumen.texto || '')];
    $('#aprender-resumen').textContent = lineas.join('\n');
    $('#aprender-resumen').hidden = false;
    const nuevos = (Array.isArray(r.presets) && r.presets.length ? r.presets : r.preset ? [r.preset] : []).filter(Boolean);
    const nombres = nuevos.map((p) => p.nombre);
    $('#aprender-estado').textContent = nombres.length === 1
      ? `Preset "${nombres[0]}" creado.`
      : `${nombres.length} presets creados: ${nombres.join(', ')}.`;
    for (const n of nombres) S.cachePresets.delete(n);
    await cargarPresets();
    if (nuevos.length) {
      PV.nombre = nuevos[0].nombre;
      PV.sucio = false;
      pintarListaPresets();
      rellenarFormPreset(nuevos[0]);
    }
    $('#aprender-resumen').scrollIntoView({ block: 'nearest' });
  } catch (e) {
    $('#aprender-estado').textContent = '';
  } finally {
    boton.disabled = false;
    $('#aprender-ocupado').hidden = true;
  }
}

/* ---------------------------------------------------------------------
   App de escritorio: versión, modelos, actualización, novedades, carpetas, salir
   --------------------------------------------------------------------- */

const quitarV = (v) => String(v == null ? '' : v).replace(/^v/i, '');

function pintarVersion(v) {
  const el = $('#version');
  const limpia = quitarV(v);
  el.hidden = !limpia;
  if (limpia) el.textContent = 'v' + limpia;
}

/* ---- descarga de los modelos de IA (primera vez) ---- */

const TEXTO_ESPERA_MODELO = 'Espera a que termine la descarga del modelo de IA (solo la primera vez): hasta entonces no se pueden procesar fotos.';

/** Mientras falte el modelo de recorte (birefnet_lite) no se puede analizar ninguna foto. */
function modeloBloquea() {
  const m = S.modelos;
  return !!(m && !m.listos && Array.isArray(m.faltan) && m.faltan.includes('birefnet_lite'));
}

function actualizarBotonesLote() {
  const activo = !!S.progreso.activo;
  const bloquea = modeloBloquea();
  for (const [id, titulo] of [
    ['#btn-procesar', 'Procesa todas las fotos pendientes con la IA'],
    ['#btn-rehacer', 'Vuelve a procesar todas las fotos, también las que ya están listas'],
  ]) {
    const b = $(id);
    b.disabled = activo || bloquea;
    b.title = bloquea ? TEXTO_ESPERA_MODELO : titulo;
  }
  // Los botones "Procesar esta foto" / "Reintentar" del detalle siguen el mismo criterio.
  for (const b of $$('[data-procesar-foto]')) {
    b.disabled = bloquea;
    if (bloquea) b.title = TEXTO_ESPERA_MODELO;
    else b.removeAttribute('title');
  }
}

const mb = (bytes) => num(bytes / 1048576, 0);

function pintarModelos(m) {
  S.modelos = m;
  const franja = $('#franja-modelos');
  franja.hidden = !!m.listos;
  if (!m.listos) {
    const sub = $('#modelos-sub');
    const barra = $('#modelos-barra');
    if (m.error) {
      franja.classList.add('error');
      $('#modelos-texto').textContent = 'No se han podido descargar los modelos de IA: ' + m.error;
      sub.textContent = 'Comprueba tu conexión y vuelve a abrir EDITFOTO.';
      sub.hidden = false;
    } else {
      franja.classList.remove('error');
      const total = Number(m.total) || 0;
      const hecho = Number(m.hecho) || 0;
      const pct = total > 0 ? limitar(Math.floor((100 * hecho) / total), 0, 100) : 0;
      const partes = [];
      const desc = m.descripcion || m.modelo || '';
      if (desc) partes.push(desc);
      if (total > 0) partes.push(`${pct} % (${mb(hecho)} de ${mb(total)} MB)`);
      $('#modelos-texto').textContent =
        'Descargando los modelos de IA (solo la primera vez)' + (partes.length ? ': ' + partes.join(', ') : '...');
      const puedeProcesar = !modeloBloquea();
      sub.textContent = puedeProcesar ? 'Ya puedes procesar fotos; el modelo grande sigue bajando.' : '';
      sub.hidden = !puedeProcesar;
      $('#modelos-relleno').style.width = pct + '%';
      barra.setAttribute('aria-valuenow', String(pct));
    }
  }
  actualizarBotonesLote();
}

async function vigilarModelos() {
  let fallos = 0;
  while (!S.cerrada) {
    let m = null;
    try {
      m = await api('GET', '/api/modelos', undefined, { silencioso: true });
      fallos = 0;
    } catch (e) {
      if (e.estado === 404 || ++fallos >= 30) return; // servidor sin esa ruta, o sin servidor
    }
    if (m) {
      pintarModelos(m);
      if (m.listos) return;
    }
    await esperar(1000);
  }
}

/* ---- actualización automática ---- */

const U = { fase: null, bloquea: false };

function pintarActualizacion(a) {
  U.fase = a.fase;
  pintarVersion(a.version_actual || (S.estado && S.estado.version));
  $('#franja-actualizacion').hidden = a.fase !== 'esperando';
  const dlg = $('#dlg-actualizacion');
  U.bloquea = ['detectada', 'descargando', 'instalando'].includes(a.fase);
  if (!U.bloquea) {
    if (dlg.open) dlg.close();
    return;
  }
  const v = quitarV(a.version);
  $('#act-titulo').textContent = 'Actualización disponible' + (v ? ': v' + v : '');
  const barra = $('#act-barra');
  const descargando = a.fase === 'descargando';
  const pct = limitar(Math.round(Number(a.progreso) || 0), 0, 100);
  barra.hidden = !descargando;
  $('#act-spinner').hidden = descargando;
  if (descargando) {
    $('#act-sub').textContent = `Descargando... ${pct} %`;
    $('#act-relleno').style.width = pct + '%';
    barra.setAttribute('aria-valuenow', String(pct));
  } else if (a.fase === 'instalando') {
    $('#act-sub').textContent = 'Instalando: EDITFOTO se reinicia solo';
  } else {
    $('#act-sub').textContent = 'Preparando la descarga...';
  }
  if (!dlg.open) dlg.showModal();
}

/** Consulta /api/actualizacion cada segundo (máx. 40 s si no hay nada que hacer). */
async function vigilarActualizacion() {
  const t0 = Date.now();
  let quieto = null;
  let caido = false;
  while (!S.cerrada) {
    let a = null;
    try {
      a = await api('GET', '/api/actualizacion', undefined, { silencioso: true });
    } catch (e) {
      if (e.estado === 404) return;
      caido = true;
    }
    if (a) {
      if (caido && U.fase === 'instalando') {
        location.reload(); // la app ha vuelto a arrancar con la versión nueva
        return;
      }
      caido = false;
      pintarActualizacion(a);
      const fase = a.fase;
      if (fase === 'al_dia' || fase === 'desarrollo') return;
      if (fase === 'error') {
        avisar(a.mensaje || 'No se ha podido comprobar si hay una versión nueva.');
        return;
      }
      if (fase === 'inactivo') {
        if (quieto == null) quieto = Date.now();
        if (Date.now() - quieto >= 5000) return;
      } else {
        quieto = null;
      }
    }
    // Con una versión en camino se sigue vigilando; si no hay nada, el límite es de 40 s.
    const enCamino = ['detectada', 'descargando', 'esperando', 'instalando'].includes(U.fase);
    if (!enCamino && Date.now() - t0 >= 40000) return;
    await esperar(1000);
  }
}

/* ---- novedades de la versión ---- */

/** Trozos de texto con **negrita**, sin innerHTML. */
function enLinea(texto) {
  const partes = texto.split('**');
  if (partes.length % 2 === 0) partes.splice(-2, 2, partes.slice(-2).join('**')); // ** sin cerrar: se deja como texto
  return partes.map((t, i) => (i % 2 ? crear('strong', { texto: t }) : t)).filter((n) => n !== '');
}

/** Markdown sencillo: "## título", "- elemento", "**negrita**" y párrafos. Devuelve nodos del DOM. */
function markdownSencillo(md) {
  const salida = [];
  let lista = null;
  let parrafo = [];
  const cerrarParrafo = () => {
    if (parrafo.length) salida.push(crear('p', {}, ...enLinea(parrafo.join(' '))));
    parrafo = [];
  };
  for (const cruda of String(md).split(/\r?\n/)) {
    const l = cruda.trim();
    let m;
    if (!l) {
      cerrarParrafo();
      lista = null;
    } else if ((m = /^#{1,6}\s+(.*)$/.exec(l))) {
      cerrarParrafo();
      lista = null;
      salida.push(crear('h3', {}, ...enLinea(m[1])));
    } else if ((m = /^[-*]\s+(.*)$/.exec(l))) {
      cerrarParrafo();
      if (!lista) {
        lista = crear('ul');
        salida.push(lista);
      }
      lista.append(crear('li', {}, ...enLinea(m[1])));
    } else {
      lista = null;
      parrafo.push(l);
    }
  }
  cerrarParrafo();
  return salida;
}

async function cargarNovedades() {
  let n;
  try {
    n = await api('GET', '/api/novedades', undefined, { silencioso: true });
  } catch (e) {
    return;
  }
  if (!n || !n.notas) return;
  const v = quitarV(n.version);
  $('#novedades-titulo').textContent = 'Novedades de la versión' + (v ? ' v' + v : '');
  $('#novedades-cuerpo').replaceChildren(...markdownSencillo(n.notas));
  const dlg = $('#dlg-novedades');
  if (!dlg.open) dlg.showModal();
  $('#novedades-ok').focus();
}

/* ---- carpetas ---- */

const menuAbierto = () => !$('#menu-carpetas').hidden;

function abrirMenuCarpetas() {
  const rutas = (S.estado && { entrada: S.estado.entrada, salida: S.estado.salida, ejemplos: S.estado.ejemplos }) || {};
  for (const b of $$('#menu-carpetas .menu-op')) {
    const ruta = rutas[b.dataset.cual];
    if (ruta) b.title = ruta;
    else b.removeAttribute('title');
  }
  $('#menu-carpetas').hidden = false;
  $('#btn-carpetas').setAttribute('aria-expanded', 'true');
  $('#menu-carpetas .menu-op').focus();
}

function cerrarMenuCarpetas(devolverFoco) {
  if (!menuAbierto()) return;
  $('#menu-carpetas').hidden = true;
  $('#btn-carpetas').setAttribute('aria-expanded', 'false');
  if (devolverFoco) $('#btn-carpetas').focus();
}

function menuTeclado(e) {
  const ops = $$('#menu-carpetas .menu-op');
  const i = ops.indexOf(document.activeElement);
  let destino = null;
  if (e.key === 'ArrowDown') destino = ops[(i + 1) % ops.length];
  else if (e.key === 'ArrowUp') destino = ops[(i - 1 + ops.length) % ops.length];
  else if (e.key === 'Home') destino = ops[0];
  else if (e.key === 'End') destino = ops[ops.length - 1];
  else if (e.key === 'Tab') cerrarMenuCarpetas(false);
  if (destino) {
    e.preventDefault();
    destino.focus();
  }
}

async function abrirCarpeta(cual) {
  try {
    const r = await api('POST', '/api/abrir_carpeta', { cual }, { silencioso: true });
    avisar('Carpeta abierta' + (r && r.ruta ? ': ' + r.ruta : '.'), 'ok');
  } catch (e) {
    // El mensaje del servidor puede ser técnico: se da la ruta para abrirla a mano.
    const ruta = S.estado && S.estado[cual];
    avisar('No se ha podido abrir la carpeta automáticamente.' + (ruta ? ' Ábrela a mano: ' + ruta : ''), 'error');
  }
}

/* ---- salir ---- */

async function salir() {
  try {
    S.progreso = await api('GET', '/api/progreso', undefined, { silencioso: true });
  } catch (e) { /* se usa lo último que se sabía */ }
  const avisos = [];
  if (S.progreso.activo) {
    avisos.push(`Hay un procesado en marcha (${S.progreso.hechas} de ${S.progreso.total} fotos). Si sales ahora, se para y las que falten se quedarán sin procesar.`);
  }
  if (P.id && P.historia.length) avisos.push('Tienes trazos de pincel sin aplicar: se perderán.');
  if (PV.sucio) avisos.push('Tienes cambios sin guardar en un preset: se perderán.');
  if (avisos.length) {
    const ok = await confirmar(avisos.join(' '), { titulo: 'Salir de EDITFOTO', si: 'Salir de todos modos', no: 'Seguir en EDITFOTO' });
    if (!ok) return;
  }
  try {
    await api('POST', '/api/salir');
  } catch (e) {
    return;
  }
  S.cerrada = true;
  P.historia = [];
  PV.sucio = false;
  U.bloquea = false;
  for (const d of $$('dialog[open]')) if (d.id !== 'dlg-cerrada') d.close();
  $('#dlg-cerrada').showModal();
}

/* ---------------------------------------------------------------------
   Teclado
   --------------------------------------------------------------------- */

function esCampoDeTexto(t) {
  if (!t || !t.closest) return false;
  if (t.closest('textarea, select, [contenteditable="true"]')) return true;
  const i = t.closest('input');
  if (!i) return false;
  return !['range', 'checkbox', 'radio', 'button'].includes(i.type);
}

function alternarAyuda() {
  const d = $('#dlg-ayuda');
  if (d.open) d.close();
  else if (!$('dialog[open]')) d.showModal();
}

document.addEventListener('keydown', (e) => {
  const t = e.target;
  if (esCampoDeTexto(t)) return;
  const dialogoAbierto = $('dialog[open]');
  if (e.key === '?') {
    e.preventDefault();
    alternarAyuda();
    return;
  }
  if (dialogoAbierto) return;

  if (e.key === 'Escape') {
    if (menuAbierto()) {
      cerrarMenuCarpetas(true);
      return;
    }
    if (S.vista === 'detalle') navegar('#');
    return;
  }
  if (S.vista !== 'detalle') return;

  const enRango = t && t.type === 'range';
  const conCtrl = (e.ctrlKey || e.metaKey) && !e.altKey;
  if (conCtrl) {
    if (S.modo === 'pintar') {
      const k = e.key.toLowerCase();
      if (k === 'z' && !e.shiftKey) { e.preventDefault(); deshacer(); }
      else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); rehacer(); }
    }
    return;
  }

  switch (e.key) {
    case 'ArrowLeft':
    case 'ArrowRight':
      if (enRango) return;
      e.preventDefault();
      irAVecina(e.key === 'ArrowLeft' ? -1 : 1);
      break;
    case 'a':
    case 'A':
      if (e.repeat) return;
      e.preventDefault();
      aprobarYSiguiente();
      break;
    case 'r':
    case 'R':
      if (e.repeat || e.altKey) return;
      e.preventDefault();
      girar(S.id, e.shiftKey ? -1 : 1);
      break;
    case '1': ponerModo('resultado'); break;
    case '2': ponerModo('antes'); break;
    case '3': ponerModo('pintar'); break;
    case ' ':
      if (S.modo === 'pintar') {
        e.preventDefault();
        if (!P.espacio) {
          P.espacio = true;
          $('#pintor').classList.add('mover');
          actualizarCursor();
        }
      }
      break;
    default:
      if (S.modo !== 'pintar') return;
      if (e.key === '[' || e.key === '-') { e.preventDefault(); cambiarTam(0.85); }
      else if (e.key === ']' || e.key === '+') { e.preventDefault(); cambiarTam(1 / 0.85); }
      else if (e.key === 'e' || e.key === 'E') { P.goma = !P.goma; herramientasActualizar(); }
      else if (e.key === 'm' || e.key === 'M') { ponerMascara(!P.mascara); }
      else if (e.key === '0') { ajustarVista(); }
  }
});

document.addEventListener('keyup', (e) => {
  if (e.key === ' ' && P.espacio) {
    e.preventDefault();
    P.espacio = false;
    $('#pintor').classList.remove('mover');
    actualizarCursor();
  }
});

window.addEventListener('blur', () => {
  P.espacio = false;
  $('#pintor').classList.remove('mover');
});

/* ---------------------------------------------------------------------
   Arranque
   --------------------------------------------------------------------- */

function enlazarEventos() {
  $('#marca').addEventListener('click', (e) => { e.preventDefault(); navegar('#'); });
  $('#tab-fotos').addEventListener('click', () => navegar('#'));
  $('#tab-presets').addEventListener('click', () => navegar('#presets'));
  $('#btn-ayuda').addEventListener('click', alternarAyuda);
  $('#btn-procesar').addEventListener('click', () => procesar(false));
  $('#btn-rehacer').addEventListener('click', () => procesar(true));
  $('#btn-recargar').addEventListener('click', recargarCarpeta);
  $('#btn-cancelar').addEventListener('click', cancelarProcesado);
  $('#sel-lote').addEventListener('change', (e) => almacen.guardar('lote', e.target.value));
  $('#filtro').addEventListener('change', aplicarFiltro);
  $('#tam-miniaturas').addEventListener('input', (e) => {
    document.documentElement.style.setProperty('--columnas', e.target.value + 'px');
    almacen.guardar('columnas', e.target.value);
  });

  const rejilla = $('#rejilla');
  rejilla.addEventListener('click', (e) => {
    if (e.target.closest('.casilla')) return;
    const g = e.target.closest('.giro');
    if (g) {
      e.stopPropagation();
      girar(g.closest('.tarjeta').dataset.id, Number(g.dataset.sentido));
      return;
    }
    const t = e.target.closest('.tarjeta');
    if (t) navegar('#foto/' + t.dataset.id);
  });
  rejilla.addEventListener('change', (e) => {
    const casilla = e.target.closest('.casilla input');
    const t = e.target.closest('.tarjeta');
    if (casilla && t) fijarAprobada(t.dataset.id, casilla.checked);
  });
  rejilla.addEventListener('keydown', (e) => {
    const t = e.target.closest && e.target.closest('.tarjeta');
    if (t && e.target === t && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      navegar('#foto/' + t.dataset.id);
    }
  });

  $('#d-volver').addEventListener('click', () => navegar('#'));
  $('#d-ant').addEventListener('click', () => irAVecina(-1));
  $('#d-sig').addEventListener('click', () => irAVecina(1));
  $('#d-aprobar').addEventListener('click', aprobarActual);
  $$('.modo').forEach((b) => b.addEventListener('click', () => ponerModo(b.dataset.modo)));
  $('#sel-preset-foto').addEventListener('change', (e) => cambiarPresetFoto(e.target.value));
  $('#btn-restablecer').addEventListener('click', restablecer);
  $('#btn-guardar-preset').addEventListener('click', guardarEnPreset);

  $('#form-preset').addEventListener('submit', presetGuardar);
  $('#form-nuevo').addEventListener('submit', presetCrear);
  $('#form-aprender').addEventListener('submit', presetAprender);
  $('#aprender-abrir').addEventListener('click', () => abrirCarpeta('ejemplos'));

  $('#d-girar-izq').append(iconoGiro(-1));
  $('#d-girar-der').append(iconoGiro(1));
  $('#d-girar-izq').addEventListener('click', () => girar(S.id, -1));
  $('#d-girar-der').addEventListener('click', () => girar(S.id, 1));

  $('#btn-carpetas').addEventListener('click', () => (menuAbierto() ? cerrarMenuCarpetas(true) : abrirMenuCarpetas()));
  $('#menu-carpetas').addEventListener('keydown', menuTeclado);
  $$('#menu-carpetas .menu-op').forEach((b) =>
    b.addEventListener('click', () => {
      cerrarMenuCarpetas(false);
      abrirCarpeta(b.dataset.cual);
    })
  );
  document.addEventListener('click', (e) => {
    if (menuAbierto() && !e.target.closest('.menu-caja')) cerrarMenuCarpetas(false);
  });
  $('#btn-salir').addEventListener('click', salir);
  const dlgAct = $('#dlg-actualizacion');
  dlgAct.addEventListener('cancel', (e) => e.preventDefault()); // sin cierre: la app se reinicia sola
  dlgAct.addEventListener('close', () => { if (U.bloquea && !S.cerrada) dlgAct.showModal(); });
  const dlgFin = $('#dlg-cerrada');
  dlgFin.addEventListener('cancel', (e) => e.preventDefault());
  dlgFin.addEventListener('close', () => { if (S.cerrada) dlgFin.showModal(); });

  window.addEventListener('hashchange', aplicarRuta);
  window.addEventListener('beforeunload', (e) => {
    if ((P.id && P.id === S.id && P.historia.length) || PV.sucio) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

async function iniciar() {
  construirAjustes();
  construirPinceles();
  construirFormPreset();
  enlazarEventos();
  ponerTam(P.tam);

  const filtro = almacen.leer('filtro', 'todas');
  if (FILTROS[filtro]) {
    S.filtro = filtro;
    $('#filtro').value = filtro;
  }
  const columnas = almacen.leer('columnas', '210');
  $('#tam-miniaturas').value = columnas;
  document.documentElement.style.setProperty('--columnas', $('#tam-miniaturas').value + 'px');
  const modo = almacen.leer('modo', 'resultado');
  S.modo = modo === 'antes' ? 'antes' : 'resultado'; // al abrir una foto no se arranca en Pintar

  // Lo propio de la app de escritorio arranca ya, sin esperar a la rejilla.
  vigilarModelos();
  vigilarActualizacion();

  await Promise.all([cargarEstado().catch(() => {}), cargarPresets().catch(() => {}), cargarFotos().catch(() => {})]);
  rejillaSincronizar();
  actualizarContador();
  await aplicarRuta();
  cargarNovedades();

  try {
    S.progreso = await api('GET', '/api/progreso', undefined, { silencioso: true });
    if (S.progreso.activo) {
      S.trabajoVisto = true;
      pintarProgreso();
      vigilarProgreso();
    }
  } catch (e) { /* sin servidor */ }
}

iniciar();
