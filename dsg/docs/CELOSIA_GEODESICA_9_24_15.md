# Celosía geodésica sobre el IOS · 9.24.15

La celosía conserva el contorno dibujado. Dos ramas principales conectan con el sleeve y las barras secundarias unen sus nudos y los apoyos restantes mediante rutas de superficie. El cálculo utiliza el IOS cerrado (`DSG_Model_Closed`), no el modelo pasivo de retención.

Se han retirado los puentes elevados del generador. Las propuestas aéreas antiguas no se pueden revisar como candidatos nuevos. Las rutas usan el grafo triangular del IOS y suavizado reproyectado al mismo corredor. Cada tramo secundario se comprueba contra los triángulos, con una tolerancia geométrica de 0,02 mm: comprobar solo los extremos no es suficiente. Las uniones locales al sleeve conservan su comprobación propia.

## Uso

En el paso de refuerzos, pulsa **OPTIMIZAR FRAME**. El cálculo se ejecuta en segundo plano. Los refuerzos principales aparecen en naranja y la celosía secundaria en cian. Revisa la propuesta y pulsa **USAR CELOSÍA** o **Descartar**. Hasta aceptar, se conservan los refuerzos originales y el contorno. Descartar recupera su visibilidad.

Si no existe una conexión válida sobre el IOS, el generador informa de ello; no la sustituye por un puente aéreo. Las rutas son reproducibles y geodésicas aproximadas sobre la triangulación; no se afirma un óptimo geodésico continuo global.

## Límites y siguientes mejoras

La validación comprueba geometría, conectividad y obstáculos registrados. La resistencia mecánica y la booleana final siguen pendientes de evaluación; no es una certificación clínica. Las siguientes mejoras son seleccionar mejor las regiones anatómicas de paso, distribuir las uniones al sleeve y evaluar la rigidez de los candidatos.
