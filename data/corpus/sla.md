+++
doc_id = "sla"
title = "Acuerdo de nivel de servicio (SLA)"
version = "2026-01"
effective_date = "2026-01-01"
status = "active"
+++
# Acuerdo de nivel de servicio (SLA)

La disponibilidad se mide mensualmente sobre la API y el panel web en producción.

## Planes con SLA contractual

El plan Pro Plus tiene un SLA de 99,9% de disponibilidad mensual. El plan Enterprise tiene un SLA de 99,95% de disponibilidad mensual.

Los planes Starter y Pro no tienen SLA contractual. Para esos planes Kestrel mantiene un objetivo interno de 99,5% de disponibilidad, pero su incumplimiento no genera créditos.

## Créditos del plan Pro Plus

Si la disponibilidad mensual de una cuenta Pro Plus es menor a 99,9% pero igual o mayor a 99,0%, el crédito es del 10% de la cuota mensual. Si es menor a 99,0% pero igual o mayor a 95,0%, el crédito es del 25%. Si es menor a 95,0%, el crédito es del 50%.

## Créditos del plan Enterprise

Si la disponibilidad mensual de una cuenta Enterprise es menor a 99,95% pero igual o mayor a 99,5%, el crédito es del 10% de la cuota mensual. Si es menor a 99,5% pero igual o mayor a 99,0%, el crédito es del 25%. Si es menor a 99,0%, el crédito es del 50%.

## Exclusiones

No cuentan como indisponibilidad el mantenimiento programado notificado con al menos 72 horas de anticipación (hasta 4 horas por mes), los eventos de fuerza mayor, los problemas originados en la infraestructura del cliente ni el entorno sandbox.

## Cómo solicitar un crédito

El cliente debe solicitar el crédito mediante un ticket dentro de los 30 días posteriores al fin del mes en que ocurrió el incidente, indicando los identificadores de incidente publicados en la página de estado. El crédito se aplica en la próxima factura, no es canjeable por dinero y no puede superar el 50% de la cuota mensual.
