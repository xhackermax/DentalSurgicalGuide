# Suavizado de extracción — DSG9.22.20

Corregido el botón SÍ/NO cuando la reconstrucción de alta resolución conserva referencias a un acabado anterior. Una referencia guardada ya no se confunde con una malla suavizada activa. Los resultados en caché se activan y desactivan por diente restaurando la fuente exacta; las mallas nuevas utilizan desplazamientos medidos y reversibles.

La forma visible, la vista previa de extensión y el cortador de la booleana utilizan la misma superficie. El botón no ejecuta ni repite la booleana sobre el IOS. Si la preparación falla, se restaura la elección y la malla anterior, se oculta la vista previa no válida y se muestra el error.

Verificación: reproducción de referencias antiguas, cambio SÍ/NO, mallas suavizadas en caché y restauración tras error. Sobre una copia de la malla de alta resolución del diente15 de la sesión: desplazamiento máximo0,199975mm, error relativo de volumen6,31e-9, misma superficie visible y para la booleana, restauración exacta al desactivar. Se mantienen todos los cambios9.22.19 y el botón Copiar diagnóstico eliminado.
