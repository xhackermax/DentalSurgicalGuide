# Celosía entre refuerzos con prioridad en el sleeve · 9.24.13

Diseño solicitado: conservar el contorno y construir una celosía entre los refuerzos principales, según el esquema B aportado por el usuario. El sleeve es el objetivo prioritario del soporte. Las barras secundarias enlazan barras entre sí y con los apoyos del frame.

El generador conserva las dos conexiones principales verificadas hacia el sleeve. Divide cada trayectoria en nudos compartidos sobre puntos reales del recorrido; añade dos travesaños y una diagonal para formar triángulos. Después intenta enlazar los apoyos restantes a esos nudos. No transforma cruces en proyección en uniones tridimensionales.

Las barras principales mantienen el diámetro elegido por el usuario. Las secundarias usan un radio de diseño de 0,7 veces el principal, mínimo 0,6 mm sin superar el principal: es una heurística geométrica, no una dimensión validada mecánicamente. Se visualizan principales en naranja y secundarias en cian. No se añaden controles de parámetros al panel.

Todas las barras nuevas se calculan sobre la superficie, se suavizan dentro de su corredor y se comprueban con su grosor real. Una penalización favorece separarlas de los tubos existentes. Las uniones declaradas permiten contacto conectado al nudo y limitado por el radio y el ángulo de salida, con un máximo geométrico de ocho radios principales. Se rechaza tanto un cruce posterior como un extremo no declarado dentro de otra barra. Este límite de diseño no sustituye el análisis de la unión booleana final. El acceso de la fresa y los conductos de irrigación mantienen sus restricciones. Si falta una de las tres conexiones internas obligatorias, se informa de que no hay celosía válida: no se presenta un par de barras como una celosía terminada.

Uso: OPTIMIZAR FRAME genera una propuesta; USAR CELOSÍA la acepta y Descartar celosía recupera los refuerzos anteriores. El contorno y el modelo originales se conservan. El proceso sigue ejecutándose fuera de la interfaz.

La prioridad del sleeve determina la disposición de las conexiones, no demuestra un aumento cuantificado de rigidez. Esta entrega no incluye ensayo mecánico ni validación de la unión booleana final o de secciones fabricables. Las estaciones de nudo 40 % y 72 % son decisiones de distribución geométrica; la validación posterior debe usar las trayectorias curvas y geometría unida reales.
