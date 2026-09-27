# @eonarys/integrations

Reservado para los futuros adapters/connectors hacia fuentes conectadas
(Gmail, Calendar, Drive, proveedores financieros, viajes, GitHub,
Microsoft, MCP — ver `docs/ARCHITECTURE.md`), tratadas como sensores de
contexto, no como módulos principales del producto.

## Por qué está vacío en 0.1

Ninguna fuente conectada está en alcance de 0.1 (ver `docs/ROADMAP.md`).
Definir una interfaz de "connector" ahora, sin ningún connector real que la
implemente, sería una abstracción prematura. Este paquete existe solo para
reservar el límite de la capa en la estructura del monorepo.

Se empieza a implementar en **0.2 — Google Context** (ver
`docs/ROADMAP.md`), con Gmail y Google Calendar como primeros connectors.
