# White Paper — Ocean Proto: Infraestructura de Inteligencia Marítima
## Monitoreo de Megacruceros, Yates y Pesca Industrial en Baja California Sur
### Diseño de Dashboard y Visualizador de Grafos Serverless bajo la Doctrina de Diseño Esoteria

---

## 1. Resumen Ejecutivo

**Ocean Proto** es una plataforma de análisis espacial y de red diseñada para evaluar el impacto de la actividad humana en los hábitats de megafauna marina (principalmente cetáceos) en el Golfo de California y la costa de Baja California Sur.

Recientemente, el enfoque del proyecto ha pivotado de la industria de *Oil & Gas* hacia el monitoreo prioritario de:
1. **Megacruceros y Yates**: Embarcaciones de gran calado (`passenger`) que introducen ruido acústico y riesgo de colisiones directas en canales de tránsito y zonas de crianza.
2. **Pesca Industrial**: Flotas activas (`fishing` / `support`) cuyo esfuerzo pesquero y comportamiento espacial alteran las cadenas tróficas y los hábitats críticos.
3. **Eventos Oscuros (Apagones AIS)**: Incidentes donde los barcos desactivan intencionalmente su transpondedor AIS (`AisGapEvent`), sugiriendo potencial pesca ilegal o actividades no reportadas en áreas protegidas.

Este documento detalla la reestructuración de la interfaz web, el desarrollo del explorador interactivo del **Knowledge Graph** (Grafo de Conocimiento) y la transición hacia una arquitectura **serverless cloud-native** en Vercel y Supabase.

---

## 2. Optimización del Dashboard (Diseño de Tres Columnas)

El diseño original utilizaba múltiples paneles flotantes superpuestos sobre el mapa Leaflet, lo que obstruía el análisis geográfico y generaba solapamientos críticos en resoluciones estándar.

Para resolver esto, se implementó una distribución rígida de **tres columnas** mediante un sistema de cajas flex en CSS:

```
┌──────────────────────────────────────────────────────────────────┐
│                         HEADER (Esoteria)                        │
├──────────────┬────────────────────────────────────┬──────────────┤
│              │                                    │              │
│  [ MAPA ]    │                                    │   Intel      │
│  [ GRAFO ]   │            MAIN WORKSPACE          │   Panel      │
│              │            (Map or D3 Graph)       │              │
│  Layer       │                                    │  ──────────  │
│  Panel       │                                    │   KG         │
│              │                                    │   Panel      │
│ (Sidebar L)  │            [ StatsBar ]            │ (Sidebar R)  │
└──────────────┴────────────────────────────────────┴──────────────┘
```

### 2.1. Funcionalidades de Layout:
- **Sidebar Izquierdo (Control, 280px)**: Aloja el selector principal de vista (**[ Mapa ] / [ Grafo ]**) y los filtros de capas o red.
- **Sidebar Derecho (Análisis, 360px)**: Apila de forma limpia el panel de tráfico e inteligencia marina (`IntelPanel`) y el panel de estadísticas del grafo (`KGPanel`) con scroll vertical.
- **Botones de Colapso (Minimalist Toggles)**: Pequeñas pestañas minimalistas (`◀`/`▶`) permiten colapsar las sidebars a `width: 0` instantáneamente, maximizando el espacio de visualización a pantalla completa.
- **ResizeObserver en Leaflet**: Un observador de tamaño se encarga de re-calcular las dimensiones del contenedor del mapa en tiempo real, invocando `map.invalidateSize()` de forma reactiva al abrir/cerrar paneles, eliminando los fallos visuales de renderizado.

---

## 3. Explorador del Knowledge Graph D3.js

El Knowledge Graph modela las complejas relaciones eco-antrópicas del ecosistema marino. Cuenta con **2,051 nodos** y **4,148 aristas**, vinculando celdas espaciales (`HexCell`), avistamientos de megafauna (`MegafaunaOccurrence`), especies de ballenas (`WhaleSpecies`), identidades de barcos (`VesselIdentity`), apagones de radio (`AisGapEvent`) y zonas de alto riesgo de colisión (`RiskZone`).

### 3.1. Estrategia de Visualización y Digestibilidad:
Cargar un grafo de este tamaño directamente genera un desorden visual incomprensible ("hairball effect") y degrada el rendimiento del cliente. Se implementó una doble estrategia de visualización:

1. **Vista Macro (Sin Foco)**: Muestra una red simplificada que incluye únicamente las entidades de alto nivel: especies de cetáceos, zonas de riesgo, plataformas de infraestructura, pesqueros industriales y eventos de apagón AIS. Las celdas espaciales individuales y detecciones se ocultan por defecto.
2. **Vista de Vecindario Local (Foco)**: Al buscar una entidad o hacer doble clic en un nodo, la simulación física de D3.js se re-calcula reactivamente para mostrar **únicamente** el nodo enfocado y sus conexiones a **1-hop o 2-hop** de profundidad. Esto aísla el análisis a un rango de 5 a 50 nodos legibles.

### 3.2. Código de Diseño (Identidad Visual Esoteria):
Fiel a la doctrina de diseño institucional de Esoteria (v1.0), se han prohibido las esquinas redondeadas, las sombras y los degradados. Los nodos se representan con formas geométricas puras SVG sin anti-aliasing cosmético:
- **WhaleSpecies / Species**: Rombos de color cyan (`#44bbff`).
- **SupportVessel (Pesqueros Industriales)**: Cuadrados de color verde (`#22c55e`).
- **OilPlatform (Cruceros e Infraestructura)**: Cuadrados de color violeta (`#a855f7`).
- **AisGapEvent**: Triángulos amarillos de advertencia (`#facc15`).
- **RiskZone**: Hexágonos grandes rojos (`#ef4444`).
- **HexCell (Celdas Espaciales)**: Pequeños hexágonos grises (`#475569`).

Las conexiones (aristas) se dibujan con líneas crispadas de color gris, con flechas de dirección en la punta (`marker-end`) y etiquetas emergentes al hacer hover que revelan la relación semántica (ej. `DARK_NEAR_WHALE`). Un **Inspector de Nodos** lateral despliega las propiedades físicas (latitud/longitud, estado de conservación IUCN, horas de apagón) y proporciona un botón interactivo para alternar a la vista de mapa y centrar automáticamente el visor geográfico en sus coordenadas.

---

## 4. Arquitectura Serverless Cloud-Native (Supabase + Vercel)

Para posibilitar el despliegue del frontend de Next.js en Vercel sin requerir un backend local FastAPI activo en producción, se ha migrado el almacenamiento de los datos estructurados a **Supabase (PostgreSQL + PostgREST)**.

1. **Tabla `knowledge_graph`**: Creada en la base de datos de Supabase para almacenar la estructura completa en formato `JSONB`.
2. **Políticas de Seguridad RLS**: Activado el Row Level Security (RLS) en la tabla, permitiendo acceso público de lectura (`SELECT`) de forma anónima, mientras que la escritura se restringe a las credenciales administrativas.
3. **Pipeline de Datos**: El backend conserva los scripts de ingesta y generación del Knowledge Graph en Python (`knowledge_graph.py`). Una vez compilado el grafo localmente, un script realiza un volcado PostgREST (`upsert`) del JSON directamente en la nube.
4. **Clientes en Frontend**:
   - `supabase.ts` define los clientes `db.knowledgeGraph()` y `db.kgStats()`, que consultan la base de datos de Supabase.
   - Esto permite que tanto el visualizador de redes D3 como el panel de estadísticas (`KGPanel`) funcionen directamente en el cliente en Vercel de manera serverless, garantizando disponibilidad y rapidez global.

---

## 5. Conclusiones y Futuro del Monitoreo

La reestructuración del dashboard de **Ocean Proto** bajo los estándares visuales e institucionales de Esoteria dota a los investigadores y tomadores de decisiones de una herramienta de visualización extremadamente fluida y rigurosa. Al desacoplar la interfaz y unificar las fuentes de datos geográficas y de red bajo Supabase, la plataforma queda optimizada para su consumo en la nube en Vercel, lista para integrarse con modelos de inteligencia artificial en tiempo real.
