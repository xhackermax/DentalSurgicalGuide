# Cilindro de seguridad del microtornillo · DSG 9.15.10

La vista previa y el microtornillo confirmado generan automáticamente dos envolventes:

- Una banda visible de **2 mm** alrededor del punto de asiento del microtornillo.
- Un cilindro completo invisible que abarca desde la punta real de la malla hasta el asiento, con margen axial en ambos extremos y margen radial de seguridad.

El margen utiliza la configuración existente de seguridad, con el mínimo empleado por los halos de implantes. El cálculo incluye el diámetro, la escala y la orientación del microtornillo; las envolventes siguen su objeto visual y se reconstruyen si cambian sus medidas.

Se comprueba contacto con dientes CBCT conservados, nervios segmentados, implantes y otros microtornillos. El modelo de soporte, el hueso y la estructura propia no se consideran obstáculos, porque el microtornillo debe apoyarse o penetrar en ellos. Los FDI fijados para extracción mantienen su tratamiento diferenciado.

La confirmación del microtornillo, su incorporación a la estructura, el avance desde la estructura y la exportación se bloquean si existe contacto o no se puede verificar una geometría consultada. El implante también comprueba los microtornillos presentes entre sus obstáculos.

En el paso de microtornillos se mantienen visibles las raíces vecinas elegidas y los nervios mandibulares de la planificación inferior. Los cilindros auxiliares no se incorporan a la geometría de la guía, las booleanas ni la animación. Al eliminar una vista previa, se retiran sus envolventes al actualizar el panel.

Se sigue utilizando el flujo de colocación y actualización del microtornillo existente; no hace falta otro botón para crear el cilindro. Mover la vista previa mueve sus envolventes, y la confirmación comprueba la posición actual.

Verificación con el asset real del microtornillo y geometrías sintéticas en Blender: altura visible, trayectoria completa, raíces, nervio, implante, otro microtornillo, rotación y rechazo de confirmación sin consumir la vista previa. No es una evaluación clínica de un paciente.
