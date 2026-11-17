+++
doc_id = "limites-api"
title = "Límites de uso de la API"
version = "2026-04"
effective_date = "2026-04-10"
status = "active"
+++
# Límites de uso de la API

La API REST de Kestrel Billing aplica límites de velocidad por cuenta. Los límites dependen del plan contratado y se cuentan sobre todas las API keys de la cuenta en conjunto.

## Límite de requests por minuto

Una cuenta Starter puede hacer hasta 60 requests por minuto.

Una cuenta Pro puede hacer hasta 300 requests por minuto.

Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.

Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

## Cuota diaria de llamadas

Además del límite por minuto, existe una cuota diaria. El plan Starter tiene una cuota de 10.000 llamadas por día, el plan Pro de 100.000 llamadas por día y el plan Pro Plus de 250.000 llamadas por día. El plan Enterprise no tiene cuota diaria.

## Qué ocurre al superar un límite

Cuando una cuenta supera el límite, la API responde con el código HTTP 429 (Too Many Requests) e incluye el encabezado Retry-After, que indica cuántos segundos esperar antes de reintentar. Las llamadas rechazadas con 429 no se descuentan de la cuota diaria.

## API keys y entorno sandbox

Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.

El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

## Paginación

Los endpoints que devuelven listas entregan como máximo 100 elementos por página. Para obtener más resultados se debe usar el cursor indicado en el campo next_cursor.
