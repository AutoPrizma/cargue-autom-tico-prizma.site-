"""Estado acumulado por curso: que actividades ya quedaron en PRIZMA.

Persiste en data/estado_cursos.json un registro por curso con el resultado
ultimo y acumulado de cada actividad (hoja + fila de la matriz). De ahi salen:

- la pagina /cursos (que falta de un curso y por que),
- el pre-marcado de las fallidas al volver a subir la matriz (reintento).

Regla de negocio: una actividad "falta" mientras nunca haya quedado OK. Si ya
se subio alguna vez y un intento posterior fallo, sigue contando como subida
(el archivo ya esta en PRIZMA), pero se conserva el ultimo error visible.
"""

import csv
from datetime import datetime, timedelta
import hashlib
import os
import threading
import unicodedata

from auto_prizma.core.clock import _ahora_colombia, _ahora_colombia_iso
from auto_prizma.core.config import ESTADO_CURSOS_PATH, LOCAL_DATA_RETENTION_DAYS, RESULTADOS_DIR
from auto_prizma.core.storage import read_json, write_json_atomic
from auto_prizma.services.auth import _normalizar_usuario, _usuario_actual
from auto_prizma.services.error_messages import extraer_codigo_error, mensaje_error


ESTADO_LOCK = threading.RLock()
DIAS_CONSERVAR_ESTADO_CURSOS = LOCAL_DATA_RETENTION_DAYS

ESTADO_OK = "ok"
ESTADO_ERROR = "error"


# ============================================================
# LECTURA / ESCRITURA
# ============================================================

def _cargar_estado():
    with ESTADO_LOCK:
        datos = read_json(ESTADO_CURSOS_PATH, {}, dict, errors=(Exception,))
        if not isinstance(datos, dict):
            return {}

        ahora = _ahora_colombia()
        limite = ahora - timedelta(days=DIAS_CONSERVAR_ESTADO_CURSOS)
        vigentes = {}
        for clave, registro in datos.items():
            try:
                fecha = datetime.fromisoformat(str((registro or {}).get("actualizado") or ""))
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=ahora.tzinfo)
            except (AttributeError, TypeError, ValueError):
                # Los registros sin fecha legible se conservan; no se borran por error.
                vigentes[clave] = registro
                continue
            if fecha >= limite:
                vigentes[clave] = registro

        if len(vigentes) != len(datos):
            write_json_atomic(ESTADO_CURSOS_PATH, vigentes)
        return vigentes


def _guardar_estado(datos):
    write_json_atomic(ESTADO_CURSOS_PATH, datos)


def _clave_curso(curso, programa, usuario_app=None):
    base = f"{str(programa or '').strip().casefold()}||{str(curso or '').strip().casefold()}"
    usuario = _normalizar_usuario(usuario_app)
    if not usuario:
        return base
    propietario = hashlib.sha256(usuario.encode("utf-8")).hexdigest()[:20]
    return base + "||usuario:" + propietario


def _clave_actividad(hoja, fila):
    return f"{str(hoja or '').strip()}|{str(fila or '').strip()}"


def _resultado_subido(resultado):
    """True si el resultado significa 'la actividad ya está en PRIZMA'.

    El motor escribe "OK"; el flujo de Tests escriben "Cargado"/"Omitido" y
    un cargue omitible puede venir como "Ya existía"/"Duplicado" (mismas
    reglas que la columna Resultado de los reportes). Todo eso cuenta como
    subido: la meta es que el archivo esté en PRIZMA, no cuántas veces se
    intentó.
    """
    texto = str(resultado or "").strip().casefold()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    if texto in ("ok", "cargado"):
        return True
    return any(
        marca in texto
        for marca in ("cargad", "exit", "omitid", "ya exist", "duplicad")
    )


def _fila_int(fila):
    try:
        return int(fila)
    except (TypeError, ValueError):
        return None


# ============================================================
# REGISTRO (llamado desde guardar_resultado en el motor)
# ============================================================

def registrar_resultado_actividad(actividad, resultado, observacion, recurso=""):
    """Acumula el resultado de una actividad en data/estado_cursos.json.

    Nunca propaga excepciones: un fallo aqui no debe romper un cargue.
    """
    try:
        if not isinstance(actividad, dict):
            return

        curso = str(actividad.get("curso") or "").strip()
        if not curso:
            return

        programa = str(actividad.get("programa") or "").strip()
        usuario = _usuario_actual()
        hoja = str(actividad.get("hoja") or "").strip()
        fila = actividad.get("fila_excel")
        nombre = str(actividad.get("nombre") or "").strip()
        es_ok = _resultado_subido(resultado)
        ahora = _ahora_colombia_iso()

        with ESTADO_LOCK:
            datos = _cargar_estado()
            id_curso = _clave_curso(curso, programa, usuario)

            registro = datos.get(id_curso)
            if not isinstance(registro, dict):
                registro = {
                    "curso": curso,
                    "programa": programa,
                    "actualizado": "",
                    "actividades": {},
                }
                datos[id_curso] = registro

            actividades = registro.get("actividades")
            if not isinstance(actividades, dict):
                actividades = {}
                registro["actividades"] = actividades

            clave = _clave_actividad(hoja, fila)
            item = actividades.get(clave)
            if not isinstance(item, dict):
                item = {
                    "hoja": hoja,
                    "fila": fila,
                    "nombre": nombre,
                    "recurso": "",
                    "estado": ESTADO_ERROR,
                    "codigo": "",
                    "motivo": "",
                    "intentos": 0,
                    "veces_ok": 0,
                    "fallas": 0,
                    "ok_en": "",
                    "ultimo_error_en": "",
                }
                actividades[clave] = item

            item["intentos"] = int(item.get("intentos") or 0) + 1
            item["nombre"] = nombre or item.get("nombre") or ""
            item["hoja"] = hoja
            item["fila"] = fila
            if recurso:
                item["recurso"] = str(recurso)

            # Detalle que necesitan el reintento individual y la verificacion
            # en PRIZMA. Los registros antiguos no lo traen y se regeneran
            # desde el reporte CSV del cargue (ver _completar_desde_reportes).
            categoria = str(actividad.get("categoria_prizma") or "").strip()
            if categoria:
                item["categoria"] = categoria
            for campo in (
                "semana",
                "unidad",
                "tipo_archivo",
                "tipo_recurso",
                "enlace",
            ):
                valor = actividad.get(campo)
                if valor is not None and str(valor).strip():
                    item[campo] = str(valor).strip()

            if es_ok:
                item["veces_ok"] = int(item.get("veces_ok") or 0) + 1
                item["ok_en"] = str(item.get("ok_en") or "") or ahora
                item["estado"] = ESTADO_OK
                item["codigo"] = ""
                item["motivo"] = ""
            else:
                item["fallas"] = int(item.get("fallas") or 0) + 1
                item["estado"] = ESTADO_ERROR
                codigo = extraer_codigo_error(observacion)
                item["codigo"] = codigo
                item["motivo"] = mensaje_error(observacion)
                item["ultimo_error_en"] = ahora

            registro["curso"] = curso
            registro["programa"] = programa
            registro["actualizado"] = ahora
            # El hilo de cargue fija USUARIO_ACTUAL; fuera de uno (tests,
            # registro manual) no se cambia el dueno existente.
            if usuario:
                registro["usuario_app"] = str(usuario)

            _guardar_estado(datos)
    except Exception:
        pass


# ============================================================
# CONSULTAS
# ============================================================

def _es_faltante(item):
    """Falta mientras nunca haya quedado OK en ningun intento."""
    return not str(item.get("ok_en") or "")


def _cursos_del_usuario(datos, usuario_app=None):
    registros = []
    for registro in datos.values():
        if not isinstance(registro, dict):
            continue
        if usuario_app is not None and _normalizar_usuario(registro.get("usuario_app")) != _normalizar_usuario(usuario_app):
            continue
        registros.append(registro)
    return registros


def resumen_cursos(usuario_app=None):
    """Lista de cursos con progreso: total, subidas, faltantes y detalle."""
    datos = _cargar_estado()
    salida = []

    for registro in _cursos_del_usuario(datos, usuario_app):
        actividades = registro.get("actividades")
        if not isinstance(actividades, dict):
            continue

        items = []
        for item in actividades.values():
            if isinstance(item, dict):
                items.append(item)

        subidas = [i for i in items if not _es_faltante(i)]
        faltantes = [i for i in items if _es_faltante(i)]

        salida.append(
            {
                "id": _clave_curso(
                    registro.get("curso"), registro.get("programa"), registro.get("usuario_app")
                ),
                "curso": str(registro.get("curso") or "Curso sin nombre"),
                "programa": str(registro.get("programa") or ""),
                "actualizado": str(registro.get("actualizado") or ""),
                "total": len(items),
                "subidas": len(subidas),
                "faltantes": len(faltantes),
                "detalle_faltantes": _ordenar_por_fila(faltantes),
                "detalle_subidas": _ordenar_por_fila(subidas),
            }
        )

    salida.sort(key=lambda c: (c["programa"].casefold(), c["curso"].casefold()))
    return salida


def _ordenar_por_fila(items):
    def clave(item):
        fila = _fila_int(item.get("fila"))
        return (0, fila, "") if fila is not None else (1, 0, str(item.get("fila") or ""))

    return sorted(items, key=clave)


def cursos_con_faltantes(usuario_app=None, nombres_cursos=None):
    """Cursos (de la lista dada) que tienen actividades nunca subidas.

    ``nombres_cursos`` permite acotar a los cursos de la matriz recien subida.
    """
    nombres = {str(n or "").strip().casefold() for n in nombres_cursos or []}
    salida = []

    for resumen in resumen_cursos(usuario_app):
        if nombres and resumen["curso"].casefold() not in nombres:
            continue
        if resumen["faltantes"]:
            salida.append(resumen)

    return salida


def claves_faltantes(usuario_app=None, nombres_cursos=None):
    """Claves [[hoja, fila], ...] de las actividades nunca subidas.

    Solo se devuelven claves reales (fila numerica) porque son las que el motor
    puede volver a procesar via `filtrar_actividades_seleccionadas`.
    """
    claves = []
    for resumen in cursos_con_faltantes(usuario_app, nombres_cursos):
        for item in resumen["detalle_faltantes"]:
            fila = _fila_int(item.get("fila"))
            if fila is None:
                continue
            claves.append([str(item.get("hoja") or ""), fila])
    return claves


def _norm(texto):
    """Minusculas, sin acentos y con espacios colapsados (para comparar nombres)."""
    texto = str(texto or "").strip().casefold()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def preseleccion_faltantes(hojas_analizadas, usuario_app=None):
    """Que claves [[hoja, fila]] pre-marcar al volver a subir una matriz.

    Cruza las actividades recien analizadas (estructura de ``analizar_excel``:
    hojas[].actividades[].fila) con las faltantes registradas del usuario.

    Solo se marca una fila si:
    - esa (hoja, fila) sigue sin subirse, y
    - el nombre coincide con el registrado (si la matriz cambio y la fila ahora
      es otra actividad, no se marca nada).

    Returns:
        (claves, cursos): claves para pre-marcar y nombres de curso afectados.
    """
    registradas = {}
    for resumen in resumen_cursos(usuario_app):
        for item in resumen["detalle_faltantes"]:
            fila = _fila_int(item.get("fila"))
            if fila is None:
                continue
            registradas[(str(item.get("hoja") or ""), fila)] = _norm(item.get("nombre"))

    claves = []
    cursos = set()

    for hoja in hojas_analizadas or []:
        if not isinstance(hoja, dict):
            continue
        nombre_hoja = str(hoja.get("hoja") or "")
        curso = str(hoja.get("curso") or "")

        for actividad in hoja.get("actividades") or []:
            fila = _fila_int(actividad.get("fila"))
            if fila is None:
                continue
            nombre_registrado = registradas.get((nombre_hoja, fila))
            if nombre_registrado is None:
                continue
            nombre_actual = _norm(actividad.get("nombre"))
            if nombre_registrado and nombre_actual != nombre_registrado:
                continue
            claves.append([nombre_hoja, fila])
            if curso:
                cursos.add(curso)

    return claves, sorted(cursos)


def total_faltantes(usuario_app=None):
    return sum(r["faltantes"] for r in resumen_cursos(usuario_app))


# ============================================================
# REINTENTO INDIVIDUAL Y VERIFICACION EN PRIZMA
# ============================================================

CATEGORIAS_PRIZMA = ("OVI", "OVA", "CHALLENGE")

MENSAJE_SIN_DETALLE = (
    "Este registro es anterior y no guardo el detalle de la actividad. "
    "Sube la matriz otra vez en Inicio (aunque sea sin cargar nada) para "
    "regenerarlo y vuelve a intentarlo."
)


def _falta_detalle(item):
    """True si el registro aun no guarda categoria/tipo de la actividad."""
    return (
        not str(item.get("categoria") or "").strip()
        or not str(item.get("tipo_archivo") or "").strip()
    )


def _fila_reporte(curso, hoja, fila):
    """Semana/unidad/categoria/tipo de la fila en el reporte CSV mas reciente.

    Los registros hechos antes de guardar el detalle no lo traen; el CSV de
    data/reportes tiene una fila por actividad con esos datos, asi que se usa
    para regenerarlo. Solo se busca el curso indicado (una hoja "Matriz" fila
    9 puede ser otra actividad en otro curso).
    """
    fila_int = _fila_int(fila)
    if fila_int is None or not curso:
        return None

    try:
        nombres = sorted(os.listdir(RESULTADOS_DIR), reverse=True)
    except OSError:
        return None

    for nombre in nombres:
        if not nombre.endswith(".csv"):
            continue
        try:
            with open(
                os.path.join(RESULTADOS_DIR, nombre),
                newline="",
                encoding="utf-8-sig",
            ) as fh:
                for fila_csv in csv.DictReader(fh):
                    if str(fila_csv.get("Hoja") or "").strip() != str(hoja or "").strip():
                        continue
                    if (
                        str(fila_csv.get("Curso") or "").strip().casefold()
                        != str(curso).strip().casefold()
                    ):
                        continue
                    if _fila_int(fila_csv.get("Fila Excel")) != fila_int:
                        continue
                    return {
                        "semana": str(fila_csv.get("Semana") or "").strip(),
                        "unidad": str(fila_csv.get("Unidad") or "").strip(),
                        "categoria": str(fila_csv.get("Categoría") or "").strip().upper(),
                        "tipo_archivo": str(fila_csv.get("Tipo") or "").strip().upper(),
                    }
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return None


def _completar_desde_reportes(curso, actividades):
    """Rellena en sitio los items sin categoria/tipo usando el reporte CSV.

    Returns:
        True si se completo al menos un item (el caller debe guardar).
    """
    pendientes = [
        item
        for item in actividades.values()
        if isinstance(item, dict) and _falta_detalle(item)
    ]
    if not pendientes:
        return False

    completado = False
    for item in pendientes:
        extra = _fila_reporte(curso, item.get("hoja"), item.get("fila"))
        if not extra:
            continue
        for campo, valor in extra.items():
            if not str(item.get(campo) or "").strip():
                item[campo] = valor
        completado = True
    return completado


def _actividad_desde_item(registro, item):
    """Diccionario con la forma que espera el motor, o (None, motivo humano)."""
    nombre = str(item.get("nombre") or "").strip()
    programa = str(registro.get("programa") or "").strip()
    categoria = str(item.get("categoria") or "").strip().upper()
    tipo_archivo = str(item.get("tipo_archivo") or "").strip().upper()

    if not nombre:
        return None, "La actividad no tiene nombre registrado."
    if not programa:
        return None, "El curso no tiene programa registrado."
    if not categoria or not tipo_archivo:
        return None, MENSAJE_SIN_DETALLE
    if categoria not in CATEGORIAS_PRIZMA:
        return None, (
            "La categoria registrada (" + categoria + ") no es valida en PRIZMA."
        )

    return {
        "fila_excel": item.get("fila"),
        "hoja": str(item.get("hoja") or ""),
        "programa": programa,
        "curso": str(registro.get("curso") or ""),
        "semana": str(item.get("semana") or ""),
        "unidad": str(item.get("unidad") or ""),
        "nombre": nombre,
        "categoria_prizma": categoria,
        "tipo_recurso": str(item.get("tipo_recurso") or ""),
        "tipo_archivo": tipo_archivo,
        "enlace": str(item.get("enlace") or ""),
        "recurso": str(item.get("recurso") or ""),
    }, None


def _registro_del_curso(datos, id_curso, usuario_app):
    """Registro del curso o (None, motivo) si no existe o no es del usuario."""
    registro = datos.get(id_curso)
    if not isinstance(registro, dict):
        return None, "Ese curso no tiene actividades registradas."
    if usuario_app is not None and _normalizar_usuario(registro.get("usuario_app")) != _normalizar_usuario(usuario_app):
        return None, "Ese curso no pertenece a tu usuario."
    return registro, None


def actividad_para_reintento(id_curso, clave, usuario_app=None):
    """(actividad, error) para subir un recurso elegido a mano a UNA actividad.

    La actividad se reconstruye con lo registrado en data/estado_cursos.json;
    si le faltan datos (registros antiguos) se regeneran desde el reporte CSV
    del cargue que los produjo.
    """
    with ESTADO_LOCK:
        datos = _cargar_estado()
        registro, error = _registro_del_curso(datos, id_curso, usuario_app)
        if error:
            return None, error

        actividades = registro.get("actividades")
        item = actividades.get(clave) if isinstance(actividades, dict) else None
        if not isinstance(item, dict):
            return None, "Esa actividad no esta registrada en el curso."

        if _falta_detalle(item) and _completar_desde_reportes(
            str(registro.get("curso") or ""),
            actividades,
        ):
            _guardar_estado(datos)

        return _actividad_desde_item(registro, item)


def actividades_para_verificar(id_curso, usuario_app=None):
    """(lista de (clave, actividad), sin_datos, error) de un curso.

    `lista` es lo que se puede consultar en PRIZMA; `sin_datos` son registros
    incompletos que se informan como "sin datos" en vez de omitirse en silencio.
    """
    with ESTADO_LOCK:
        datos = _cargar_estado()
        registro, error = _registro_del_curso(datos, id_curso, usuario_app)
        if error:
            return None, None, error

        actividades = registro.get("actividades")
        if not isinstance(actividades, dict) or not actividades:
            return None, None, "Ese curso no tiene actividades registradas."

        if _completar_desde_reportes(str(registro.get("curso") or ""), actividades):
            _guardar_estado(datos)

        lista = []
        sin_datos = []
        for clave, item in actividades.items():
            if not isinstance(item, dict):
                continue
            actividad, motivo = _actividad_desde_item(registro, item)
            if actividad is None:
                sin_datos.append(
                    {
                        "clave": clave,
                        "nombre": str(item.get("nombre") or "(sin nombre)"),
                        "motivo": motivo,
                    }
                )
            else:
                lista.append((clave, actividad))

        return lista, sin_datos, None


def marcar_verificacion(id_curso, resultados, usuario_app=None):
    """Aplica al estado lo que encontro la verificacion en PRIZMA.

    resultados: [{"clave", "verificacion"}] con "existe", "no_esta" o
    "no_se_pudo". Solo se tocan hechos comprobados:

    - "no_esta" en una actividad que estaba subida: vuelve a faltar (no
      aparece en PRIZMA).
    - Todo lo demas deja constancia (verificacion + fecha) sin cambiar si
      cuenta como subida o faltante.

    Nunca propaga excepciones.
    """
    try:
        with ESTADO_LOCK:
            datos = _cargar_estado()
            registro, error = _registro_del_curso(datos, id_curso, usuario_app)
            if error:
                return

            actividades = registro.get("actividades")
            if not isinstance(actividades, dict):
                return

            ahora = _ahora_colombia_iso()
            for entrada in resultados or []:
                if not isinstance(entrada, dict):
                    continue
                item = actividades.get(str(entrada.get("clave") or ""))
                if not isinstance(item, dict):
                    continue

                verificacion = str(entrada.get("verificacion") or "").strip()
                item["verificacion"] = verificacion
                item["verificado_en"] = ahora
                item["verificacion_detalle"] = str(entrada.get("detalle") or "").strip()

                if verificacion == "no_esta" and str(item.get("ok_en") or ""):
                    item["ok_en"] = ""
                    item["estado"] = ESTADO_ERROR
                    item["codigo"] = "ERROR_NO_ESTA_EN_PRIZMA"
                    item["motivo"] = "Verificación: la actividad no aparece en PRIZMA."
                    item["ultimo_error_en"] = ahora

            registro["actualizado"] = ahora
            _guardar_estado(datos)
    except Exception:
        pass
