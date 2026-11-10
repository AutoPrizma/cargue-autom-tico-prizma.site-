"""Iconos SVG de la interfaz.

Trazos de 24x24 que toman el color del texto (currentColor); el tamano lo
fija el CSS (.icono).
"""

_TRAZOS = {
    # Menu lateral
    "inicio": '<path d="m3 10 9-7 9 7"/><path d="M5 9v12h14V9"/><path d="M10 21v-6h4v6"/>',
    "torre": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M12 3v4M21 12h-4M12 21v-4M3 12h4"/><path d="m16.2 7.8-2.8 2.8"/>',
    "test": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    "moodle": '<path d="M3 19V9l4 4 5-6 5 6 4-4v10"/><path d="M3 19h18"/>',
    "subir": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "historial": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "reportes": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18"/>',
    "clave": '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3"/><path d="m16 7 3 3"/><path d="m19 4 2 2"/>',
    "salir": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
    # Barra superior
    "luna": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "sol": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    # Estado del servicio
    "chromium": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="M12 8.5h8.4M9 13.8 4.8 6.5M15 13.8l-4.2 7.2"/>',
    "wifi": '<path d="M5 12.6a10 10 0 0 1 14 0"/><path d="M1.5 9a15 15 0 0 1 21 0"/><path d="M8.5 16.1a5 5 0 0 1 7 0"/><path d="M12 20h.01"/>',
    # Archivos y formularios
    "enlace": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7.1-7.1l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7.1 7.1l1.7-1.7"/>',
    "documento": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/>',
    "hoja": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><rect x="8" y="12" width="8" height="6" rx="1"/><path d="M12 12v6M8 15h8"/>',
    "zip": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M10 4h1.5M10 7h1.5M10 10h1.5M10 13h1.5"/><rect x="9.5" y="15.5" width="3" height="3.5" rx=".8"/>',
    "word": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m8 12 1.5 6 2.5-4.5 2.5 4.5 1.5-6"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "check-circulo": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "alerta-circulo": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5h.01"/>',
    "alerta": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
    "cerrar": '<path d="M18 6 6 18M6 6l12 12"/>',
    "girar": '<path d="M21 12a9 9 0 1 1-6.2-8.6"/>',
    # Tablas y acciones
    "mas": '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
    "ver": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "descargar": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "copiar": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "filtro": '<path d="M3 4h18l-7 8.5V19l-4 2v-8.5z"/>',
    "ordenar": '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
    "birrete": '<path d="M22 10 12 5 2 10l10 5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/><path d="M22 10v6"/>',
    "libro": '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>',
    "calendario": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "externo": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "play": '<path d="M7 4v16l13-8z"/>',
    "flecha-derecha": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "flecha-izquierda": '<path d="M19 12H5M11 18l-6-6 6-6"/>',
    "anterior": '<path d="m15 18-6-6 6-6"/>',
    "siguiente": '<path d="m9 18 6-6-6-6"/>',
    "escudo": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "usuario": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "matraz": '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3"/><path d="M7 15h10"/>',
    # Tipos de actividad y formato
    "ovi": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z"/>',
    "ova": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/><path d="m9 9 2 2 4-4"/>',
    "reto": '<path d="M8 3h8v4a4 4 0 0 1-8 0z"/><path d="M8 5H4v2a4 4 0 0 0 4 4M16 5h4v2a4 4 0 0 1-4 4"/><path d="M12 11v5M8 21h8M10 16h4v5h-4z"/>',
    "paquete": '<path d="m21 8-9-5-9 5 9 5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
    "codigo": '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 4l-4 16"/>',
}

def icon(name, css_class="icono"):
    """SVG en linea del icono pedido (KeyError si no existe: es un error de programacion)."""
    return (
        '<svg class="' + css_class + '" viewBox="0 0 24 24" aria-hidden="true" '
        'focusable="false">' + _TRAZOS[name] + "</svg>"
    )
