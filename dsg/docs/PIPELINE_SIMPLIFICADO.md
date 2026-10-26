# Pipeline simplificado · DSG 9.15.4

## DICOM

```text
CARGAR CBCT
├── SIMPLE · 2 ARCADAS
│   └── Revisar → MEJORAR DIENTES (opcional, una vez) → CONFIRMAR
└── INMEDIATO · FDI + ALVÉOLO
    └── Seleccionar dientes → MEJORAR DIENTES (opcional, una vez)
        → FIJAR DIENTES → CONFIRMAR
```

Se retiran los botones FDI CORRECTO, CREAR ALVÉOLOS y CAMBIAR RUTA del panel principal. La selección de extracciones está disponible directamente tras segmentar. FIJAR DIENTES conserva los FDI elegidos y cierra la primera revisión. CONFIRMAR prepara internamente las referencias de ambas arcadas y abre el alineamiento. La preparación de referencias sigue siendo necesaria aunque ya no tenga un botón separado. Se conserva la identificación FDI y la validación de la selección.

En ambas rutas, CONFIRMAR sustituye a CONFIRMAR + ALINEAR.

## Alineamiento

```text
IMPORTAR IOS / USAR IOS SELECCIONADO
→ MARCAR 3 PUNTOS → ALINEAR → SIGUIENTE
```

Se retira DETECTAR. La importación y el uso del IOS seleccionado asignan las entradas del registro. Se mantienen la corrección de puntos y el cambio de IOS.

## Modelo retentivo

```text
CERRAR AGUJEROS SEGUROS → GENERAR MODELO CERRADO
├── Simple: continuar con el modelo
└── Inmediato: seleccionar con C → guardar con P
    → CERRAR HUECO HACIA DENTRO (elimina, suaviza el borde y cierra) → booleana automática
                         ↓
PREPARAR MODELO RETENTIVO
├── Modo Objeto: calcula o actualiza desde la vista y comprueba el asiento.
└── Edición del blockout: aplica alivio a los vértices seleccionados
    y comprueba el asiento sin reconstruir ni borrar esa corrección.
                         ↓
CONFIRMAR MODELO RETENTIVO
```

PREPARAR MODELO RETENTIVO sustituye los botones de calcular, actualizar, volver a comprobar el asiento y aplicar alivio seleccionado. El campo Alivio local permanece para ajustar la magnitud de la corrección. Para alivio local, seleccionar los vértices del blockout en modo Edición y pulsar el mismo botón. En otros modos de edición no se reconstruye el modelo.

La confirmación del resultado sigue separada. Si el cálculo o la comprobación falla, el comando no declara un resultado confirmado. El flujo inmediato mantiene el requisito de cierre cóncavo y booleana antes de preparar el modelo.

## Resto del diseño

```text
Modelo retentivo → implantes → contorno → estructura / microtornillos
→ cilindros → irrigación / apertura lateral → refuerzos
→ canales de fresado → corte final → nombre y exportación
```

Los operadores antiguos siguen registrados para archivos y automatizaciones anteriores; sus botones retirados no forman parte del panel simplificado.
