# Roadmap de UI/UX y paridad con upstream

Este documento prioriza las mejoras que hacen PokeTokenBar para Windows más agradable, sencillo, bonito y funcional. No persigue copiar indiscriminadamente proveedores, arneses internos ni componentes exclusivos de macOS.

## Referencia de la auditoría

- Windows: `3ae423c` (`master`, migración de la ventana principal a Qt Quick/QML).
- Upstream fijado anteriormente: `37763d3c367068492c18f6e51b45977c2d27f6d5` (después de `v2.5.3`).
- Upstream revisado ahora: `5f1ef524a104dceee681a21c13a92a7404c6f176`, 2026-09-03.
- Fuente: [chattymin/PokeTokenBar](https://github.com/chattymin/PokeTokenBar).

La comparación se ha hecho contra el código que realmente se ejecuta. La aplicación actual instancia `QmlMainWindow`; por tanto, una función presente únicamente en la ventana Qt Widgets antigua o en el backend se considera **parcial**, no terminada.

Estados usados:

- **Hecho**: está disponible y utilizable en la interfaz QML actual.
- **Parcial**: existe en el backend, en Widgets o de forma incompleta, pero falta exposición o pulido en QML.
- **Pendiente**: no existe en la versión Windows actual.
- **Diferencia intencionada**: Windows resuelve la necesidad de otra forma o se ha descartado por poco valor visible.

## Inventario funcional visible del proyecto original

### Barra de menú y mascota flotante

- Compañero animado en la barra de menú con campos configurables de tokens, coste y límite.
- Mascota flotante redimensionable entre 48 y 192 px, arrastrable y con posición persistente.
- Consumo al pasar el cursor, apertura con clic y menú contextual con clic derecho.
- Burbujas de alertas de límites y eventos.
- Selector de calidad de animación: ahorro, equilibrado y fluido.

### Inicio y consumo

- Compañero actual, rareza, naturaleza, estado Shiny y progreso hasta eclosión, evolución o graduación.
- Tokens de hoy, semana y mes, coste estimado y previsión de agotamiento.
- Resumen combinado y pestañas por proveedor.
- Desglose por tipo de token: entrada, salida, escritura de caché y lectura de caché.
- Desglose por modelo.
- Estados vacíos, carga, datos obsoletos y errores sin mostrar detalles técnicos innecesarios.

### Límites oficiales y estado de servicios

- Límites de Claude, Codex y Antigravity con porcentaje, reinicio y estado de autenticación.
- Modo usado/restante y formato tiempo restante/fecha y hora.
- Cuenta, organización o plan cuando están disponibles.
- Actualización manual de límites y avisos cuando la sesión ha caducado.
- Luna Reserve y límites individuales de modelos de Antigravity.
- Límites personales de gasto.
- Banners de incidencias del proveedor con severidad y detalle.

### Juego y colección

- Ciclo huevo → eclosión → evoluciones reales → graduación para generaciones I–V.
- Rareza, naturaleza, Shiny, Shiny Charm y recompensas Rare Candy al completar límites.
- Pokédex consolidada y registro individual de capturas como vistas separadas.
- Colección paginada, contadores/filtros compactos y variante normal/Shiny.
- Línea evolutiva con formas obtenidas, actual y futuras ocultas.
- Pokémon representante independiente del compañero en crianza.
- Celebraciones de eclosión, evolución, graduación y Shiny.

### Bolsa y tienda

- Rare Candy, Mint y Shiny Charm con cantidades, efectos y estados de disponibilidad.
- Huevos Normal, Uncommon y Rare.
- Tarjetas que permanecen visibles aunque la acción esté bloqueada y explican el motivo.
- Confirmaciones integradas en la propia vista y advertencia reforzada al sustituir un Shiny.
- Retorno a Inicio tras comprar un huevo para mostrar el nuevo estado.

### Ajustes, mantenimiento y soporte

- Idioma completo de la interfaz en coreano, inglés, japonés, español, francés, portugués y alemán.
- Intervalo y actualización manual, inicio con el sistema y campos visibles en la barra.
- Tamaño/visibilidad de la mascota, calidad de animación y notificaciones configurables.
- Umbrales de avisos de límites y comprobación de estado de servicios.
- Carpetas de escaneo adicionales por proveedor, con comodines y recuento de coincidencias.
- Clave de sesión opcional de Claude, validación y selección de cuenta/organización.
- Importación y exportación de la partida.
- Comprobación y aplicación de actualizaciones dentro de la app.
- Acceso al registro y flujo para informar de un problema.

### Proveedores visibles en upstream

Claude, Codex, Gemini, Antigravity, OpenCode, Hermes, Cursor, Grok, GitHub Copilot, Kiro, Pi y omp. Esta lista sirve para detectar huecos, pero la paridad completa de proveedores no es una prioridad por sí misma.

## Comparación con la interfaz Windows actual

| Área | Estado | Situación real en QML |
| --- | --- | --- |
| Ventana moderna y navegación | **Hecho** | QML responsive con Inicio, Colección, Bolsa, Tienda y Ajustes; tema claro, oscuro o del sistema. |
| Bandeja del sistema | **Parcial / diferencia intencionada** | Muestra el representante como icono y el resumen en el tooltip; Windows no replica el texto y la animación incrustados en la barra de menús de macOS. QML permite ocultar tokens y coste, pero no el límite. |
| Mascota flotante | **Parcial** | Arrastre, posición persistente, clic, menú contextual, alertas y permanencia en pantallas válidas funcionan. El hover incluye el porcentaje hasta la siguiente evolución. QML solo permite 64–192 px aunque el backend admite 48–192 px. |
| Calidad de animación | **Pendiente** | Las animaciones existen, pero no hay perfiles de ahorro/equilibrado/fluido. |
| Juego y celebraciones | **Hecho** | Huevo, evoluciones, graduación, rareza, naturaleza, Shiny, recompensas y avisos breves funcionan. |
| Inicio: compañero y resumen | **Hecho** | Compañero, progreso, cuatro métricas, límites y lista de proveedores tienen tratamiento visual QML. |
| Detalle de consumo | **Parcial** | QML muestra hoy y semana por proveedor. No ofrece pestañas, mes/coste en el detalle, tipos de token ni desglose por modelo. |
| Límites oficiales | **Parcial** | Claude y Codex, barras, reinicios y usado/restante funcionan. El backend calcula previsiones y Luna Reserve, pero QML no muestra la previsión, no muestra plan/cuenta aunque recibe `plan`, no ofrece refresco manual ni estados de autenticación claros y limita la vista a tres filas. |
| Estados del servicio | **Pendiente** | No hay banners de incidencias del proveedor. |
| Pokédex y capturas | **Parcial** | QML muestra una cuadrícula y el historial seguido en la misma página. La paginación, vistas separadas, filtros/contadores, alternancia normal/Shiny y línea evolutiva solo existen en Widgets o faltan. |
| Pokémon representante | **Hecho** | Se puede elegir una captura o volver a seguir al compañero activo; se refleja en bandeja y mascota. |
| Bolsa y tienda | **Parcial** | Las operaciones y tarjetas funcionan. Las confirmaciones siguen usando diálogos Widgets; faltan motivos visibles en botones desactivados y el flujo QML no replica toda la respuesta contextual de upstream. |
| Ajustes generales | **Hecho** | Intervalo, nombres Pokémon, inicio con Windows, mascota, avisos, usado/restante, previsión, notificaciones, tema e importar/exportar. |
| Ajustes avanzados ya soportados por backend | **Parcial** | QML no expone el límite en bandeja, umbrales warning/critical ni tiempo restante/fecha y hora. Su slider empieza en 64 px aunque el backend admite 48 px. |
| Idiomas | **Parcial** | Solo se traducen nombres Pokémon. La interfaz QML está escrita en español y no usa un catálogo de traducciones. |
| Carpetas de escaneo adicionales | **Pendiente** | No hay editor por proveedor ni vista previa de coincidencias. |
| Cuenta/sesión de Claude | **Pendiente** | No hay configuración visible de clave de sesión ni selector de organización. |
| Actualizador dentro de la app | **Pendiente** | No hay aviso, descarga ni aplicación de una versión nueva. |
| Importar/exportar partida | **Hecho** | Usa selectores nativos y crea respaldo antes de importar. |
| Ayuda y diagnóstico | **Pendiente** | No hay acceso directo al log ni flujo para informar de un problema. |
| Cobertura de proveedores | **Diferencia intencionada** | Windows cubre 9 proveedores locales y límites de Claude/Codex. Antigravity, Pi y omp quedan supeditados a demanda real. |

## TODO priorizado

### P0 — recuperar funciones visibles perdidas al activar QML

- [ ] Exponer en Ajustes QML `Mostrar límite en la bandeja`.
- [ ] Exponer y validar los umbrales de advertencia y crítico ya existentes en el backend.
- [ ] Exponer el selector compartido `Tiempo restante / Fecha y hora` y aplicarlo a Inicio, bandeja y mascota.
- [ ] Corregir el slider de mascota para cubrir el rango real 48–192 px.
- [ ] Sustituir el `ComboBox` usado/restante por un control segmentado claro y compacto.
- [ ] Separar Pokédex y registro de capturas dentro de Colección.
- [ ] Recuperar paginación, contadores/filtros, alternancia normal/Shiny y línea evolutiva en QML.
- [ ] Añadir foco visible, orden de tabulación y nombres accesibles a los controles QML; verificar teclado completo.
- [ ] Corregir `README.md` para no presentar como accesibles en QML funciones que solo conserva la vista Widgets antigua.

### P1 — mejoras de UI/UX con mayor impacto

- [ ] Mostrar el motivo exacto bajo cada acción desactivada de Bolsa/Tienda, incluidos saldo insuficiente, objeto ya activo y compra de huevo bloqueada durante la fase huevo.
- [ ] Reemplazar confirmaciones modales de compra/uso por confirmaciones inline; mantener una advertencia reforzada para descartar un Shiny.
- [ ] Navegar a Inicio después de comprar un huevo y mostrar allí la transición del nuevo compañero.
- [ ] Añadir detalle por proveedor sin sobrecargar Inicio: hoy/semana/mes/coste, tipos de token y modelos.
- [ ] Mostrar en límites el plan/cuenta disponible, todos los buckets relevantes, estado obsoleto/autenticación caducada y una acción de refresco manual.
- [ ] Diferenciar visualmente `cargando`, `actualizado`, `con advertencias`, `obsoleto` y `error`; conservar los últimos datos válidos.
- [ ] Añadir selector de calidad de animación con ahorro, equilibrado y fluido, incluyendo respeto a movimiento reducido.
- [ ] Traducir toda la interfaz mediante un catálogo único; conservar español e inglés como mínimo antes de añadir los demás idiomas upstream.
- [ ] Incorporar aviso y actualización dentro de la app con opción `Más tarde` y recuperación segura ante fallo.

### P2 — funcionalidad útil, pero no esencial para el pulido inmediato

- [ ] Añadir carpetas de escaneo extra por proveedor con validación, comodines y contador de archivos coincidentes.
- [ ] Añadir configuración opcional de sesión de Claude y selección de cuenta/organización, solo si mejora casos reales de límites ausentes.
- [ ] Mostrar banners compactos de incidencias cuando aporten una explicación accionable.
- [ ] Añadir acceso a la carpeta de logs y un informe de problema que oculte secretos y datos personales.
- [ ] Evaluar límites personales de gasto si hay demanda en Windows.

### P3 — aplazado conscientemente

- [ ] Evaluar Antigravity únicamente con muestras reales de Windows y una ruta de datos estable.
- [ ] Añadir Pi u omp solo cuando exista uso verificable entre usuarios de esta versión.
- [ ] Profundizar en la reconciliación de forks de Codex solo si aparecen diferencias medibles.

No se trasladarán Keychain, Homebrew, LaunchAgent, detalles internos de AppKit ni automatismos sin impacto visible en Windows.

## Diferencias de diseño que se conservan

- La ventana principal de Windows seguirá siendo más amplia que el popover compacto de macOS; permite una jerarquía visual y navegación lateral mejores.
- Los campos de bandeja también gobiernan el contenido compacto del hover de la mascota para evitar preferencias contradictorias.
- La barra de progreso de Inicio sigue el modo usado/restante elegido; colores, alertas y recompensas siempre se calculan con utilización real.
- La previsión se aplica a ventanas oficiales con duración conocida, no solo al bloque de cinco horas de Claude.
- La integración con escritorios virtuales se limita deliberadamente al escritorio virtual actual de Windows.

## Criterio de terminado

Una casilla solo pasa a completada cuando:

1. La función está accesible en la ventana QML que se ejecuta, no únicamente en Widgets o en Python.
2. Tiene estados normal, carga, vacío, desactivado y error cuando correspondan.
3. Funciona con teclado, foco visible, temas claro/oscuro y escalado DPI habitual.
4. Cuenta con pruebas del modelo o controlador y una comprobación visual de la vista afectada.
5. No rompe bandeja, mascota flotante, persistencia de la partida ni actualización en segundo plano.

## Cambios upstream posteriores al punto fijado

Entre `37763d3` y `5f1ef52`, upstream añadió cuatro cambios. Dos afectan a experiencia visible y se incorporan al TODO:

- Los huevos permanecen visibles durante la fase huevo, con el botón desactivado y una explicación.
- Codex localizado dentro de ChatGPT.app vuelve a proporcionar límites; el cambio concreto es de macOS y no se porta literalmente, pero recuerda que en Windows la ausencia de un binario debe explicarse sin ocultar el consumo local.

Los otros dos cambios son optimización del sprite de la barra de menú y corrección de comentarios internos; no crean una función nueva para la interfaz Windows.
