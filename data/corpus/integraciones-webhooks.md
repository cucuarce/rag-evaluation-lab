+++
doc_id = "integraciones-webhooks"
title = "Webhooks y exportaciones"
version = "2026-09"
effective_date = "2026-09-05"
status = "active"
+++
# Webhooks y exportaciones

## Eventos disponibles

Kestrel envía webhooks para los siguientes eventos: invoice.created, invoice.paid, invoice.overdue, payment.failed y subscription.canceled.

## Endpoints por plan

Una cuenta Starter puede registrar 1 endpoint de webhook, una cuenta Pro hasta 5 endpoints, una cuenta Pro Plus hasta 20 endpoints y una cuenta Enterprise hasta 50 endpoints.

## Firma y verificación

Cada webhook incluye una firma HMAC-SHA256 en el encabezado Kestrel-Signature, calculada con el secreto del endpoint. El receptor debe verificar esa firma antes de procesar el evento.

## Reintentos

El endpoint debe responder con un código 2xx en menos de 10 segundos. Si no lo hace, Kestrel reintenta el envío hasta 8 veces con espera exponencial durante 24 horas. Después del último intento, el evento queda marcado como fallido y puede reenviarse manualmente desde el panel durante 15 días.

## Exportaciones

Los datos de facturas, clientes y pagos pueden exportarse en formato CSV o JSON desde el panel en todos los planes. Las exportaciones programadas, diarias o semanales, están disponibles en los planes Pro Plus y Enterprise.
