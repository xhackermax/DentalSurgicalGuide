# DSG 9.22.26: falsos rechazos de longitud

El mapa 2D exigía un encaje del 100 % de sus celdas para permitir la comprobación final. Un candidato de 12 mm tenía un encaje aproximado del 97 % en ese mapa, aunque sus muestras 3D estaban dentro del espacio clasificado y las estructuras protegidas no se invadían. Al mantener el rechazo del mapa, la interfaz acababa mostrando una referencia corta no admisible.

Ahora el mapa prioriza candidatos. La validación 3D muestreada puede resolver los falsos rechazos de pared, espacio desconocido o proximidad del mapa. Comprueba las superficies originales y también los puntos interiores que el mapa no clasifica. Un vacío interior real sigue bloqueando la propuesta. No se considera demostrado que no existan defectos más pequeños que el muestreo de 0,25 mm.

La búsqueda conjunta compara la trayectoria inicial y, cuando hay un único diente extraído correspondiente al FDI objetivo y un eje geométrico identificable, su trayectoria anatómica. Se conserva la referencia de plataforma y los límites de traslación. El trayecto anatómico tiene un límite de búsqueda explícito de 15°; es un límite de ingeniería, no una recomendación clínica. La búsqueda de posición independiente conserva su límite anterior de 5°.

Todos los candidatos compiten por el mismo orden: mayor longitud admisible y después mayor diámetro. Permanecen las comprobaciones de soporte y los márgenes de raíces, nervios, otros implantes y cavidades. Con longitudes de 10 mm o más sigue sin permitirse penetración en el seno.

Aceptar vuelve a calcular el eje autorizado y verifica posición y orientación con una instantánea nueva antes de modificar el modelo de referencia DSG. Descartar conserva el implante original. La geometría muestreada no predice torque ni estabilidad primaria clínica.

Comprobaciones: prueba que fallaba por un falso rechazo 2D; bloqueo de un vacío interior real; elección conjunta entre trayectos; rechazo de ejes no autorizados; aplicación y reversión del control del implante; búsqueda y revalidación separadas en una instantánea del caso.
