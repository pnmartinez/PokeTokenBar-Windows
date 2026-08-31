# Folla de ruta de UI/UX

Esta folla de ruta prioriza as melloras que fan PokeTokenBar para Windows máis agradable, sinxelo, atractivo e funcional. Non pretende reproducir toda a infraestrutura interna do proxecto orixinal para macOS.

## Obxectivos principais e continuos

### Modernizar a interface

Evolucionar a capa visual para conseguir unha interface máis moderna, coidada e próxima á experiencia do proxecto upstream. Antes dunha migración ampla, avaliarase mediante prototipos se convén modernizar a implementación actual con Qt Widgets/PySide6, pasar a Qt Quick/QML ou empregar outra alternativa compatible con Windows.

Calquera opción deberá conservar a integración coa bandexa do sistema, a mascota flotante, o empaquetado como aplicación independente, a accesibilidade e o comportamento correcto con distintos escalados DPI, temas e configuracións de monitores.

### Incorporar melloras do upstream

Revisar periodicamente o repositorio upstream e incorporar funcionalidades e melloras que aínda non estean presentes nesta versión, priorizando as máis útiles para as persoas usuarias de Windows e as que ofrezan unha boa relación entre valor, facilidade de adaptación e risco.

Cada revisión debe quedar reflectida en `UPSTREAM.md`, indicando o commit comparado, as decisións de paridade e as diferenzas intencionadas.

## Criterios de alcance

Priorízanse os cambios cun efecto visible na experiencia de uso:

- Claridade da información.
- Facilidade de navegación.
- Calidade visual e consistencia.
- Resposta inmediata ás accións.
- Personalización útil.
- Mellor integración co escritorio de Windows.

Quedan fóra, salvo que resolvan un problema visible en Windows:

- Informes avanzados de fallos.
- Rotación e migración histórica de rexistros.
- Keychain e mecanismos exclusivos de macOS.
- Homebrew, LaunchAgent e outros compoñentes de distribución de macOS.
- Infraestrutura interna sen impacto directo na experiencia.
- Paridade completa e indiscriminada con todos os provedores do upstream.

## Prioridade alta: experiencia principal

### Mascota flotante do escritorio

- [x] Mostrar o compañeiro fóra da bandexa do sistema.
- [x] Permitir arrastralo e lembrar a súa posición.
- [x] Permitir configurar o seu tamaño.
- [x] Abrir a xanela principal ao facer clic.
- [x] Mostrar o consumo ao pasar o cursor.
- [x] Superpoñer ao pasar o cursor a porcentaxe ata a eclosión, evolución ou graduación.
- [x] Ofrecer un menú contextual sinxelo.
- [x] Permitir volver mostralo directamente desde o menú contextual da bandexa.
- [x] Mostrar alertas de límites mediante bocadillos.
- [x] Mantelo dentro dunha pantalla válida ao cambiar monitores ou resolución.

### Sprites e animacións

- [x] Animar o Pokémon actual con sprites da quinta xeración.
- [x] Animar o ovo mentres agarda a eclosión.
- [x] Manter unha alternativa estática cando non exista animación.
- [x] Usar escalado exacto por píxel, sen suavizado borroso.
- [x] Precargar os sprites para evitar saltos ou imaxes tardías.
- [x] Reducir ou deter as animacións cando non sexan visibles.

### Pantalla Home

- [x] Dar protagonismo visual ao Pokémon actual.
- [x] Mostrar claramente o progreso do ovo ou estadio actual.
- [x] Mostrar a evolución actual e a seguinte.
- [x] Mostrar rareza, natureza e condición Shiny.
- [x] Crear un resumo compacto de consumo e límites.
- [x] Evitar grandes zonas baleiras.
- [x] Adaptar correctamente nomes e cifras longas.
- [x] Axustar dinamicamente a altura dos provedores para priorizar os límites oficiais.
- [x] Manter a porcentaxe de progreso lexible fóra do recheo da barra.

### Celebracións e resposta ás accións

- [x] Engadir unha celebración de eclosión.
- [x] Engadir unha celebración de evolución.
- [x] Engadir unha celebración de graduación.
- [x] Engadir unha celebración especial para Shiny.
- [x] Mostrar unha resposta inmediata ao usar Rare Candy.
- [x] Mostrar a nova natureza ao usar Mint.
- [x] Manter as animacións breves e non intrusivas.

### Pokémon representante

- [x] Permitir escoller como representante calquera especie posuída.
- [x] Mostrar o representante na bandexa e na mascota flotante.
- [x] Manter a súa selección independente do compañeiro que se está criando.
- [x] Permitir volver ao modo «seguir o compañeiro actual».

## Colección e progresión

### Pokédex

- [x] Presentar as especies nunha grade ordenada por número.
- [x] Engadir paxinación ou navegación compacta.
- [x] Diferenciar visualmente especies normais e Shiny.
- [x] Permitir alternar o sprite normal/Shiny dunha especie posuída.
- [x] Mostrar contadores totais e por rareza.
- [x] Deseñar coidadosamente os estados baleiros.

### Rexistro de capturas

- [x] Separar o rexistro individual da Pokédex consolidada.
- [x] Ordenar as capturas da máis recente á máis antiga.
- [x] Mostrar liña evolutiva, rareza, natureza e data.
- [x] Identificar claramente as capturas Shiny.

### Liña evolutiva visual

- [x] Diferenciar formas obtidas, actual e futuras.
- [x] Representar ramas evolutivas sen saturar a pantalla.
- [x] Mostrar estados descoñecidos cun tratamento visual coherente.

## Navegación e claridade

- [x] Manter cinco áreas principais: Home, Collection, Bag, Shop e Settings.
- [x] Usar pestanas por provedor só cando haxa varios detectados.
- [x] Manter o resumo combinado facilmente accesible.
- [x] Engadir estados baleiros claros en colección, mochila e provedores.
- [x] Diferenciar visualmente «actualizando», «actualizado», «obsoleto» e «erro».
- [x] Evitar mostrar excepcións ou mensaxes técnicas en bruto á persoa usuaria.
- [x] Facer predicible o peche e a reapertura desde a bandexa.
- [x] Engadir textos de axuda ás accións pouco evidentes.

## Bandexa do sistema

- [x] Ofrecer un modo só personaxe.
- [x] Permitir mostrar ou ocultar os tokens de hoxe.
- [x] Permitir mostrar ou ocultar o custo.
- [x] Permitir mostrar ou ocultar a porcentaxe do límite.
- [x] Manter un texto de axuda compacto co estado esencial.
- [x] Garantir boa lexibilidade con escalado DPI e temas claro/escuro.

## Límites e consumo

- [x] Mostrar os límites mediante barras de progreso claras.
- [x] Mostrar a conta atrás ata o reinicio cando estea dispoñible.
- [x] Permitir alternar entre porcentaxe usada e restante.
- [x] Aplicar cores coherentes para estados normal, de advertencia e crítico.
- [x] Permitir configurar os limiares de advertencia e crítico.
- [x] Evitar notificacións repetidas mentres se manteña o mesmo estado.
- [x] Engadir unha previsión sinxela de esgotamento antes do reinicio.
- [x] Sinalar datos obsoletos sen confundilos cun fallo da aplicación.
- [x] Mostrar Luna Reserve debaixo dos límites principais de Codex e antes dos créditos de reinicio.
- [x] Evitar Rare Candy duplicados cando a marca temporal do reinicio varíe uns segundos.

## Tenda e mochila

- [x] Deseñar tarxetas visuais para obxectos e ovos.
- [x] Mostrar icona, nome, efecto e prezo de forma inmediata.
- [x] Mostrar o saldo dispoñible de maneira consistente.
- [x] Desactivar as accións non dispoñibles explicando o motivo.
- [x] Solicitar confirmación contextual antes de mercar ou usar obxectos.
- [x] Advertir ao substituír un Pokémon activo.
- [x] Mostrar unha advertencia especial antes de descartar un Shiny.
- [x] Diferenciar visualmente ovos Normal, Uncommon e Rare.
- [x] Mostrar unha resposta visual despois de cada compra ou uso.

## Axustes

- [x] Agrupar as opcións en seccións fáciles de percorrer.
- [x] Manter as opcións técnicas dentro dunha sección avanzada pregable.
- [x] Permitir configurar o idioma dos nomes dos Pokémon.
- [x] Permitir configurar o intervalo de actualización.
- [x] Permitir configurar o inicio automático.
- [x] Permitir escoller os elementos visibles na bandexa.
- [x] Permitir configurar a mascota flotante e o seu tamaño.
- [x] Permitir activar por separado as notificacións de límites e eventos.
- [x] Permitir escoller entre porcentaxe usada ou restante.
- [x] Engadir unha adaptación consistente aos temas claro e escuro.
- [x] Engadir importación e exportación da partida mediante selectores de ficheiro.

## Pulido transversal

- [x] Definir unha xerarquía tipográfica consistente.
- [x] Unificar iconas, marxes, radios e espazado.
- [x] Mellorar o comportamento con escalado DPI.
- [x] Evitar pestanexos e cambios bruscos durante as actualizacións.
- [x] Deseñar estados de carga, erro e desconexión.
- [x] Asegurar a navegación por teclado e un foco visible.
- [x] Revisar contraste e lexibilidade.
- [x] Manter a interface compacta sen sacrificar claridade.

## Rexistro de entregas

- [x] Migrar a xanela principal a unha interface funcional Qt Quick/QML, conservando a bandexa, a mascota flotante, o estado local e as accións do xogo.
- [x] Auditar a implementación inicial e marcar unicamente requisitos verificables.
- [x] Engadir a mascota flotante configurable, persistente e adaptada aos cambios de pantalla.
- [x] Separar Bag e Shop e engadir confirmacións, motivos de bloqueo e resposta inmediata.
- [x] Personalizar o contido do texto de axuda da bandexa e usar o personaxe como icona.
- [x] Permitir escoller un representante da colección sen cambiar o compañeiro activo.
- [x] Substituír os límites en texto simple por barras con modo usado/restante e cores de urxencia.
- [x] Completar Home, celebracións, Pokédex paxinada e navegación por provedor.
- [x] Engadir temas, idioma dos nomes dos Pokémon, limiares, estados de actualización e importación/exportación segura.
- [x] Executar controis automáticos, visuais e de accesibilidade sobre a implementación da folla de ruta.
