+++
doc_id = "procedimiento-incidentes"
title = "Procedimiento de gestión de incidentes para soporte"
version = "2026-02"
effective_date = "2026-02-01"
status = "active"
+++
# Procedimiento de gestión de incidentes para soporte

Este procedimiento indica cómo el equipo de soporte clasifica y escala incidentes.

## Severidades

SEV1: el servicio está caído o la emisión de facturas está bloqueada para múltiples clientes. El tiempo de respuesta objetivo es de 15 minutos.

SEV2: una funcionalidad está degradada pero existe una alternativa temporal. El tiempo de respuesta objetivo es de 1 hora.

SEV3: un problema menor que afecta a un solo cliente. El tiempo de respuesta objetivo es de 1 día hábil.

## Quién declara un incidente

Cualquier agente de soporte puede declarar un incidente SEV2 o SEV3. Un SEV1 debe ser confirmado por el líder de guardia de ingeniería.

## Escalamiento y comunicación

Para un SEV1, el agente escala a la guardia de ingeniería en el canal interno #inc-kestrel y la página de estado se actualiza cada 30 minutos hasta la resolución. Para un SEV2, la página de estado se actualiza cada 2 horas. Los SEV3 no se publican en la página de estado.

## Revisión posterior

Todo SEV1 requiere un informe posterior al incidente (postmortem) dentro de los 5 días hábiles siguientes a su resolución. El informe se comparte con los clientes Enterprise afectados.
