# DSG 9.7.1 — Irrigación con apertura secuencial

> **Actualizado en 9.7.2:** la pared frangible y sus marcas se rediseñaron (membrana 0,10/0,25 mm dentro de cada salida, avellanado y número grabado). Ver [`PAREDES_FRANGIBLES_9_7_2.md`](PAREDES_FRANGIBLES_9_7_2.md).

## 1. Qué hace

```
 entrada Ø4 ══Y(C)══▶══Y(B)══▶══ cilindro A    ← abierto: el agua llega primero aquí
               ║          ║
          cilindro C  cilindro B               ← pared frangible de 0,10 mm, marcada
          (perforar 3º) (perforar 2º)
```

1. El usuario dibuja el **conducto principal**: el primer clic en el cilindro inicial **A** y el resto de puntos en el aire, hasta la entrada.
2. En el panel **Red de irrigación · apertura secuencial** marca los implantes que se unen a ese conducto y pulsa **VINCULAR SELECCIONADOS**. Cada uno recibe su rama (Link) con una Y colocada automáticamente en el punto del conducto más cercano a su cilindro.
3. DSG asigna los papeles automáticamente:

   | Cilindro | Estado | Orden |
   |---|---|---|
   | A (inicio del conducto) | **Abierto** | 1 |
   | Vinculados | **Pared frangible de 0,10 mm** con marca de perforación (diana Ø2,5 mm y cruz) | 2, 3… según su posición en el conducto |

4. **Orden de perforación:** desde la Y más cercana a A hacia la Y más cercana a la entrada. El agua va primero al cilindro más lejano (A) y después se abren los más cercanos a la entrada.
5. **Embudos internos invertidos:** en cada Y, el tronco que sigue hacia A lleva un estrechamiento suave (garganta) justo después de la división, y la rama del cilindro vinculado mantiene el lumen completo de Ø1 mm. Así, cuando se perfora un cilindro, ese cilindro se lleva la mayor parte del agua y le cuesta más llegar a A.

## 2. Cálculo hidráulico

Se usa flujo laminar de Hagen–Poiseuille: la resistencia de cada tramo es proporcional a ∫ds/D⁴.

Cada garganta se dimensiona para el momento en que se perfora su cilindro. En ese momento están abiertos todos los cilindros más cercanos a A y siguen cerrados los más cercanos a la entrada. La condición es que el cilindro recién abierto reciba al menos la fracción objetivo del agua que llega a su Y: **75 % por defecto**, ajustable entre 55 % y 90 % con el control "Agua al cilindro abierto".

| Parámetro | Valor | Motivo |
|---|---|---|
| Diámetro de la garganta | 0,72 – 0,94 mm | 0,72 mm es el mínimo imprimible; por encima de 0,94 mm no compensa imprimir una garganta |
| Longitud nominal | 0,90 mm | Se alarga, sin pasar del mínimo de diámetro, si hace falta más resistencia |
| Separación respecto a la Y | 0,70 mm | No toca la cámara (plenum) de la división |
| Distancia a la siguiente Y o al cilindro | ≥ 1,20 mm | Espacio libre para las transiciones |

Si con estas limitaciones no se alcanza la fracción objetivo, DSG **lo avisa y muestra el valor real previsto**; nunca lo oculta.

Ejemplo real (escena de prueba en Blender 5.2.2: tres implantes en fila, separados 12 mm):

| Etapa | A | B | C |
|---|---|---|---|
| Solo A abierto | 100 % | — | — |
| Perforado B | 25 % | **75 %** | — |
| Perforado C | 6 % | 18 % | **76 %** |

## 3. Colocación automática de las Y

- Cada Y queda a ≥ 5 mm del cilindro A (para no invadir su puerto en C).
- Cada Y queda a ≥ 7,5 mm del extremo de entrada (embudo Ø4 más la reducción de 2 mm).
- Entre dos Y hay ≥ 4,5 mm (dos cámaras más una garganta).
- Si el punto más cercano al cilindro está ocupado, la Y se desplaza al hueco libre más próximo. Si no queda hueco, ese implante no se vincula y se explica el motivo.

## 4. Dónde queda registrado

- **Implantes:** `DSG_irrigation_open_order` (1, 2, 3…), `DSG_irrigation_network_role` (`SOURCE_OPEN` o `LINKED_FRANGIBLE`) y `DSG_irrigation_predicted_share_at_opening`.
- **Guía, tras "Aplicar irrigación":** `DSG_irrigation_network_json`, con el diseño completo: orden, gargantas y reparto de agua por etapa.
- **Informe de exportación (`.dsg-report.json`):** sección `irrigation_network`, y en cada implante `irrigation_open_order` e `irrigation_frangible_wall`.
- **Simulación de flujo:** usa el reparto con todos los cilindros abiertos.

## 5. Errores corregidos durante este trabajo

1. **Las paredes frangibles no se podían construir.** `bmesh.ops.create_circle` devuelve `{'verts': …}` desde Blender 3, pero el código leía `ret['geom']`, que siempre venía vacío. Por eso **cualquier exportación con un cilindro sellado se cancelaba**. Está corregido y cubierto por un test en Blender 5.2.
2. **Link sobre otro Link:** esa rama nunca se montaba en "Aplicar irrigación" y desaparecía sin aviso. Ahora el clic se redirige al conducto principal.
3. **`deselect_all_objects`** fallaba si la capa de vista devolvía un objeto `None` justo después de borrar objetos.
4. **Links sin sello automático:** los Links no pasaban por la asignación automática de sellos. Ahora sí.
5. **Mensaje de "Aplicar irrigación":** anunciaba "boquillas compensadas Ø0,72–0,86 mm" aunque estaban desactivadas. Ahora describe el modo real.

## 6. Diseño (SOLID)

- **`dsg/irrigation_network.py`:** módulo puro, sin `bpy`. Contiene la política (`NetworkPolicy`, `PlacementRules`), la resistencia, el dimensionado de gargantas, el diseño de la red, el reparto por etapas y la colocación de las Y. Tiene 17 tests unitarios.
- **`dsg/_guide_parts/06_irrigation_c_sequential.py`:** el adaptador de Blender. Convierte las rutas guardadas en muestras, aplica las gargantas y los papeles, y define los dos operadores nuevos y el panel.
- **`commit_irrigation_link()`:** extraído del operador modal, para que el Link por dos clics y el "Vincular seleccionados" usen la misma lógica (una sola fuente).
- **Modo anterior:** se conserva. Desactivando "Apertura secuencial", la red vuelve a usar Ø1 mm en todas las ramas.

## 7. Verificación

```
SUMMARY: compileall=PASS, ruff=PASS, pytest=PASS (104), blender_smoke=PASS, install_smoke=PASS
```

`tests/test_irrigation_sequential_integration.py` (Blender 5.2.2) cubre:

- Vincular seleccionados, con el orden por posición y no por el orden de selección.
- Los papeles de cada cilindro y el reparto por etapas.
- Que el estrechamiento está solo en el tronco hacia A.
- El modo anterior.
- La construcción del cortador y de la pared de la red.
- La pared frangible de 0,10 mm: cerrada y numerada.
- "Aplicar irrigación" completo.
- El dibujo del panel.

## 8. Pendiente de validar en banco

- La presión real y la rotura de la pared de 0,10 mm dependen de la resina y de la impresora. La marca grabada deja 0,075 mm en la diana y la cruz, que es donde debe romper.
- El reparto es un modelo laminar ideal: no incluye pérdidas en los codos ni en las cámaras de las Y. Conviene medir con una jeringa y una guía impresa antes del uso clínico.
