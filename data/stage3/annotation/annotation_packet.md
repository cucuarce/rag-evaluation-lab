# Paquete de anotación — Etapa 3A

Generado por `rag-lab faith-prepare`. No editar: se regenera. Las etiquetas van en `annotation_sheet.csv`. Guía: `docs/annotation_guide.md`.

No se muestran la corrida (A/B), métricas, respuestas de referencia ni hechos esperados: se evalúa solo si los fragmentos respaldan cada afirmación.

## Grupo 1 — e31 (answer_id `7b038a978a39d986`)

**Pregunta:** ¿Cómo puede un receptor verificar que un webhook fue enviado por Kestrel?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El receptor debe validar la firma HMAC‑SHA256 incluida en el encabezado Kestrel‑Signature, calculada con el secreto del endpoint, para confirmar que el webhook proviene de Kestrel.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e31-c1` — El receptor debe validar la firma HMAC‑SHA256 incluida en el encabezado Kestrel‑Signature.
- `e31-c2` — Validar la firma permite confirmar que el webhook proviene de Kestrel.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `integraciones-webhooks` v2026-09 — VIGENTE (desde 2026-09-05) — **CITADO**

> Cada webhook incluye una firma HMAC-SHA256 en el encabezado Kestrel-Signature, calculada con el secreto del endpoint. El receptor debe verificar esa firma antes de procesar el evento.

**[S2]** `integraciones-webhooks` v2026-09 — VIGENTE (desde 2026-09-05)

> El endpoint debe responder con un código 2xx en menos de 10 segundos. Si no lo hace, Kestrel reintenta el envío hasta 8 veces con espera exponencial durante 24 horas. Después del último intento, el evento queda marcado como fallido y puede reenviarse manualmente desde el panel durante 15 días.

**[S3]** `integraciones-webhooks` v2026-09 — VIGENTE (desde 2026-09-05)

> Kestrel envía webhooks para los siguientes eventos: invoice.created, invoice.paid, invoice.overdue, payment.failed y subscription.canceled.

**[S4]** `seguridad-de-cuenta` v2026-01 — VIGENTE (desde 2026-01-15)

> Kestrel tiene cuatro roles. El Propietario controla la suscripción y todos los permisos. El Administrador gestiona usuarios y configuración, pero no la suscripción. El Contador puede emitir facturas y ver reportes, pero no cambiar la configuración. El rol Solo lectura puede consultar datos sin modificarlos.

**[S5]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01)

> Si un cobro falla, Kestrel lo reintenta automáticamente tres veces: al día 1, al día 3 y al día 7 después del fallo. Si los reintentos fallan, la cuenta pasa al estado "pago pendiente" y se bloquea la emisión de nuevas facturas. Si la deuda no se regulariza, la cuenta se suspende a los 21 días del primer cobro fallido.

---

## Grupo 2 — e27 (answer_id `4e2212fe94da9b58`)

**Pregunta:** ¿El plan Pro tiene SLA de disponibilidad?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El plan Pro no tiene SLA contractual; solo cuenta con un objetivo interno de disponibilidad del 99,5% sin generación de créditos.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e27-c1` — El plan Pro no tiene SLA contractual.
- `e27-c2` — El plan Pro cuenta con un objetivo interno de disponibilidad del 99,5% cuyo incumplimiento no genera créditos.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `sla` v2026-01 — VIGENTE (desde 2026-01-01) — **CITADO**

> El plan Pro Plus tiene un SLA de 99,9% de disponibilidad mensual. El plan Enterprise tiene un SLA de 99,95% de disponibilidad mensual.
>
> Los planes Starter y Pro no tienen SLA contractual. Para esos planes Kestrel mantiene un objetivo interno de 99,5% de disponibilidad, pero su incumplimiento no genera créditos.

**[S2]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> Si la disponibilidad mensual de una cuenta Pro Plus es menor a 99,9% pero igual o mayor a 99,0%, el crédito es del 10% de la cuota mensual. Si es menor a 99,0% pero igual o mayor a 95,0%, el crédito es del 25%. Si es menor a 95,0%, el crédito es del 50%.

**[S3]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> La disponibilidad se mide mensualmente sobre la API y el panel web en producción.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S5]** `novedades-2026` v2026-09 — VIGENTE (desde 2026-09-05)

> El límite de la API del plan Pro aumenta de 200 a 300 requests por minuto.

---

## Grupo 3 — e04 (answer_id `58d7c6bbb6f3fb68`)

**Pregunta:** ¿Qué código de respuesta devuelve la API cuando una cuenta supera el límite de requests?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** La API devuelve el código HTTP 429 (Too Many Requests) cuando una cuenta supera el límite de requests.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e04-c1` — La API devuelve el código HTTP 429 (Too Many Requests) cuando una cuenta supera el límite de requests.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10) — **CITADO**

> Cuando una cuenta supera el límite, la API responde con el código HTTP 429 (Too Many Requests) e incluye el encabezado Retry-After, que indica cuántos segundos esperar antes de reintentar. Las llamadas rechazadas con 429 no se descuentan de la cuota diaria.

**[S2]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.
>
> El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

**[S3]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> La API REST de Kestrel Billing aplica límites de velocidad por cuenta. Los límites dependen del plan contratado y se cuentan sobre todas las API keys de la cuenta en conjunto.

**[S4]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede hacer hasta 60 requests por minuto.
>
> Una cuenta Pro puede hacer hasta 300 requests por minuto.
>
> Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.
>
> Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Los endpoints que devuelven listas entregan como máximo 100 elementos por página. Para obtener más resultados se debe usar el cursor indicado en el campo next_cursor.

---

## Grupo 4 — e36 (answer_id `57e4ee93ccb0fef4`)

**Pregunta:** ¿Puede un cliente del plan Pro usar inicio de sesión único (SSO)? Si no, ¿qué debe hacer para habilitarlo?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** No, el plan Pro no incluye inicio de sesión único (SSO); para habilitarlo debe pasar al plan Pro Plus y, como propietario o administrador, configurar el proveedor de identidad en Configuración > Seguridad > SSO.

**Citó:** S2, S1

**Afirmaciones a etiquetar:**

- `e36-c1` — El plan Pro no incluye inicio de sesión único (SSO).
- `e36-c2` — Para habilitar SSO, un cliente Pro debe pasar al plan Pro Plus.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> Un cambio de Starter a Pro, o de Pro a Pro Plus, se aplica de inmediato. Las facturas históricas y la configuración de la cuenta se conservan.
>
> Al pasar de Pro a Pro Plus se habilita el inicio de sesión único (SSO). Para usarlo, el Propietario o un Administrador debe configurar el proveedor de identidad en Configuración > Seguridad > SSO.

**[S2]** `seguridad-de-cuenta` v2026-01 — VIGENTE (desde 2026-01-15) — **CITADO**

> El inicio de sesión único mediante SAML está disponible en los planes Pro Plus y Enterprise. El aprovisionamiento automático de usuarios mediante SCIM está disponible solo en el plan Enterprise.

**[S3]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S5]** `seguridad-de-cuenta` v2026-01 — VIGENTE (desde 2026-01-15)

> Las sesiones expiran tras 12 horas de inactividad. En el plan Enterprise ese plazo es configurable entre 1 y 24 horas.
>
> Después de 5 intentos fallidos de inicio de sesión, la cuenta del usuario se bloquea durante 15 minutos.

---

## Grupo 5 — e05 (answer_id `ea636b1aa5f0e7cf`)

**Pregunta:** Un cliente Pro Plus con 18 usuarios activos pasa al plan Pro. ¿Cuánto pagará por mes por los usuarios que exceden lo incluido en Pro?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Pagará USD 96 por mes por los usuarios que exceden lo incluido en el plan Pro (8 usuarios adicionales a USD 12 cada uno).

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e05-c1` — 8 usuarios de la cuenta exceden lo incluido en el plan Pro.
- `e05-c2` — Cada usuario adicional del plan Pro cuesta USD 12 por mes.
- `e05-c3` — El cliente pagará USD 96 por mes por los usuarios que exceden lo incluido en el plan Pro.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> En los planes Pro y Pro Plus se pueden agregar usuarios por encima de los incluidos. Cada usuario adicional cuesta USD 12 por mes.

**[S2]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S3]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro cuesta USD 99 por mes. Permite emitir hasta 5.000 facturas por mes e incluye 10 usuarios. El soporte es por email y chat, con un tiempo de primera respuesta de 24 horas hábiles.
>
> El plan Pro incluye facturación recurrente y emisión de facturas en hasta 5 monedas distintas. Cada factura que supere el límite mensual se cobra como excedente a USD 0,02 por factura.

**[S4]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> El plan Pro Plus tiene un SLA de 99,9% de disponibilidad mensual. El plan Enterprise tiene un SLA de 99,95% de disponibilidad mensual.
>
> Los planes Starter y Pro no tienen SLA contractual. Para esos planes Kestrel mantiene un objetivo interno de 99,5% de disponibilidad, pero su incumplimiento no genera créditos.

**[S5]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> Si la disponibilidad mensual de una cuenta Pro Plus es menor a 99,9% pero igual o mayor a 99,0%, el crédito es del 10% de la cuota mensual. Si es menor a 99,0% pero igual o mayor a 95,0%, el crédito es del 25%. Si es menor a 95,0%, el crédito es del 50%.

---

## Grupo 6 — e21 (answer_id `f0cde5d7e08982bf`)

**Pregunta:** Al pasar a un plan inferior, ¿se devuelve la diferencia de precio al medio de pago?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** No, al pasar a un plan inferior la diferencia de precio no se devuelve al medio de pago; se acredita como saldo a favor en la cuenta.

**Citó:** S2

**Afirmaciones a etiquetar:**

- `e21-c1` — Al pasar a un plan inferior, la diferencia de precio no se devuelve al medio de pago.
- `e21-c2` — Al pasar a un plan inferior, la diferencia de precio se acredita como saldo a favor en la cuenta.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Cuando un cliente pasa a un plan inferior, la diferencia de precio se reembolsa al medio de pago original al final del ciclo de facturación.

**[S2]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01) — **CITADO**

> Cuando un cliente pasa a un plan inferior, la diferencia de precio no se devuelve al medio de pago: se acredita como saldo a favor en la cuenta y se descuenta de las próximas facturas de Kestrel.

**[S3]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01)

> Un cambio a un plan superior se aplica de inmediato y se cobra la diferencia prorrateada por los días restantes del ciclo. Un cambio a un plan inferior se aplica al final del ciclo de facturación en curso.

**[S4]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

**[S5]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Enterprise tiene precio a medida y se negocia con el equipo comercial. Incluye facturas ilimitadas sujetas a una política de uso razonable, usuarios ilimitados y un gerente de cuenta dedicado.

---

## Grupo 7 — e06 (answer_id `2c3e03f61602861b`)

**Pregunta:** ¿Cuántos días tiene un cliente para pedir el reembolso de una suscripción mensual nueva?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El cliente tiene 30 días corridos desde el primer cobro para solicitar el reembolso de una suscripción mensual nueva.

**Citó:** S2

**Afirmaciones a etiquetar:**

- `e06-c1` — Un cliente tiene 30 días corridos desde el primer cobro para solicitar el reembolso de una suscripción mensual nueva.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 14 días corridos posteriores al primer cobro. Las renovaciones mensuales no son reembolsables.

**[S2]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01) — **CITADO**

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 30 días corridos posteriores al primer cobro. Las renovaciones mensuales posteriores al primer cobro no son reembolsables.

**[S3]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Si un cliente con pago anual cancela dentro de los primeros 60 días desde el cobro, recibe un reembolso prorrateado por los meses completos no utilizados. Pasados esos 60 días, el pago anual no es reembolsable.

**[S4]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> El cliente debe enviar un ticket a soporte. El equipo de Finanzas aprueba o rechaza la solicitud en un plazo de hasta 10 días hábiles. Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de hasta 15 días hábiles.

**[S5]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> El cliente puede solicitarlo desde Configuración > Facturación > Solicitar reembolso, o mediante un ticket a soporte. El equipo de Finanzas aprueba o rechaza la solicitud en un plazo de hasta 5 días hábiles. Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de 5 a 10 días hábiles.

---

## Grupo 8 — e36 (answer_id `c5d903217dc5f081`)

**Pregunta:** ¿Puede un cliente del plan Pro usar inicio de sesión único (SSO)? Si no, ¿qué debe hacer para habilitarlo?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** No, el plan Pro no incluye inicio de sesión único (SSO); para habilitarlo debe cambiarse a un plan que lo soporte, como Pro Plus o Enterprise, y luego el Propietario o un Administrador configura el proveedor de identidad en Configuración > Seguridad > SSO.

**Citó:** S2, S1

**Afirmaciones a etiquetar:**

- `e36-c3` — Para habilitar SSO, un cliente Pro debe cambiarse a un plan que lo soporte, como Pro Plus o Enterprise.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> Un cambio de Starter a Pro, o de Pro a Pro Plus, se aplica de inmediato. Las facturas históricas y la configuración de la cuenta se conservan.
>
> Al pasar de Pro a Pro Plus se habilita el inicio de sesión único (SSO). Para usarlo, el Propietario o un Administrador debe configurar el proveedor de identidad en Configuración > Seguridad > SSO.

**[S2]** `seguridad-de-cuenta` v2026-01 — VIGENTE (desde 2026-01-15) — **CITADO**

> El inicio de sesión único mediante SAML está disponible en los planes Pro Plus y Enterprise. El aprovisionamiento automático de usuarios mediante SCIM está disponible solo en el plan Enterprise.

**[S3]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S4]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede hacer hasta 60 requests por minuto.
>
> Una cuenta Pro puede hacer hasta 300 requests por minuto.
>
> Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.
>
> Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

---

## Grupo 9 — e05 (answer_id `19e2246093db3ef7`)

**Pregunta:** Un cliente Pro Plus con 18 usuarios activos pasa al plan Pro. ¿Cuánto pagará por mes por los usuarios que exceden lo incluido en Pro?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Pagará USD 96 al mes por los 8 usuarios que exceden el límite del plan Pro (8 usuarios × USD 12 cada uno).

**Citó:** S1, S4

**Afirmaciones a etiquetar:**

- `e05-c4` — El cliente pagará USD 96 al mes por los 8 usuarios que exceden el límite del plan Pro.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> En los planes Pro y Pro Plus se pueden agregar usuarios por encima de los incluidos. Cada usuario adicional cuesta USD 12 por mes.

**[S2]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S3]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> El plan Pro cuesta USD 99 por mes. Permite emitir hasta 5.000 facturas por mes e incluye 10 usuarios. El soporte es por email y chat, con un tiempo de primera respuesta de 24 horas hábiles.
>
> El plan Pro incluye facturación recurrente y emisión de facturas en hasta 5 monedas distintas. Cada factura que supere el límite mensual se cobra como excedente a USD 0,02 por factura.

**[S5]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> Kestrel Billing ofrece cuatro planes: Starter, Pro, Pro Plus y Enterprise. Todos los precios se expresan en dólares estadounidenses (USD) por mes y no incluyen impuestos. Este documento es de uso interno del equipo de soporte.

---

## Grupo 10 — e01 (answer_id `2ad5c8f56623b9b8`)

**Pregunta:** ¿Cuántas facturas por mes puede emitir una cuenta del plan Starter?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Una cuenta del plan Starter puede emitir hasta 500 facturas por mes.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e01-c1` — Una cuenta del plan Starter puede emitir hasta 500 facturas por mes.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> El plan Starter cuesta USD 29 por mes. Permite emitir hasta 500 facturas por mes e incluye 2 usuarios. El soporte es solo por email, con un tiempo de primera respuesta de 48 horas hábiles.
>
> En el plan Starter no se pueden agregar usuarios adicionales. Si una cuenta Starter alcanza el límite de 500 facturas, la emisión de nuevas facturas queda bloqueada hasta el inicio del próximo ciclo de facturación o hasta que la cuenta pase a un plan superior.

**[S2]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro cuesta USD 99 por mes. Permite emitir hasta 5.000 facturas por mes e incluye 10 usuarios. El soporte es por email y chat, con un tiempo de primera respuesta de 24 horas hábiles.
>
> El plan Pro incluye facturación recurrente y emisión de facturas en hasta 5 monedas distintas. Cada factura que supere el límite mensual se cobra como excedente a USD 0,02 por factura.

**[S3]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Además del límite por minuto, existe una cuota diaria. El plan Starter tiene una cuota de 10.000 llamadas por día, el plan Pro de 100.000 llamadas por día y el plan Pro Plus de 250.000 llamadas por día. El plan Enterprise no tiene cuota diaria.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S5]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> Kestrel Billing ofrece cuatro planes: Starter, Pro, Pro Plus y Enterprise. Todos los precios se expresan en dólares estadounidenses (USD) por mes y no incluyen impuestos. Este documento es de uso interno del equipo de soporte.

---

## Grupo 11 — e18 (answer_id `cba7d4869635a13b`)

**Pregunta:** ¿Qué ocurre si falla el cobro de la suscripción de un cliente?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Si un cobro falla, Kestrel lo reintenta automáticamente tres veces (día 1, día 3 y día 7); si los reintentos también fallan, la cuenta pasa a "pago pendiente" y se bloquea la emisión de nuevas facturas, y si la deuda no se regulariza la cuenta se suspende a los 21 días del primer cobro fallido.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e18-c1` — Si un cobro falla, Kestrel lo reintenta automáticamente tres veces: el día 1, el día 3 y el día 7.
- `e18-c2` — Si la deuda no se regulariza, la cuenta se suspende a los 21 días del primer cobro fallido.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01) — **CITADO**

> Si un cobro falla, Kestrel lo reintenta automáticamente tres veces: al día 1, al día 3 y al día 7 después del fallo. Si los reintentos fallan, la cuenta pasa al estado "pago pendiente" y se bloquea la emisión de nuevas facturas. Si la deuda no se regulariza, la cuenta se suspende a los 21 días del primer cobro fallido.

**[S2]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01)

> El ciclo de facturación comienza el día de alta de la cuenta y el cobro se realiza automáticamente con la tarjeta registrada. Los clientes Enterprise pueden pagar por transferencia bancaria con vencimiento a 30 días.

**[S3]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 30 días corridos posteriores al primer cobro. Las renovaciones mensuales posteriores al primer cobro no son reembolsables.

**[S4]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 14 días corridos posteriores al primer cobro. Las renovaciones mensuales no son reembolsables.

**[S5]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01)

> La suscripción se cobra en dólares estadounidenses (USD). Las cuentas alojadas en la región Unión Europea pueden elegir que se les cobre en euros (EUR).

---

## Grupo 12 — e19 (answer_id `adef7af2e6d5c203`)

**Pregunta:** Un cliente Pro en la región Unión Europea migra a Enterprise. ¿Hasta cuántos días puede conservar sus logs de API y desde cuándo aplica?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Una vez finalizada la migración a Enterprise, los logs de la API pueden conservarse hasta 365 días; antes de la finalización se aplican los 90 días estándar.

**Citó:** S1, S2

**Afirmaciones a etiquetar:**

- `e19-c1` — Una vez finalizada la migración a Enterprise, los logs de la API pueden conservarse hasta 365 días.
- `e19-c2` — Antes de que finalice la migración a Enterprise, se aplica la retención estándar de 90 días para los logs de la API.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `retencion-de-datos` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> Los logs de llamadas a la API se conservan durante 90 días en todas las regiones. Las cuentas Enterprise pueden extender la retención de logs hasta 365 días.

**[S2]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> La migración a Enterprise requiere un contrato firmado. El gerente de cuenta coordina la transición en un plazo de hasta 10 días hábiles y, mientras tanto, el plan anterior sigue vigente.
>
> La retención extendida de logs y las demás funciones exclusivas de Enterprise se activan cuando la migración finaliza. Si el cliente pide cambiar de región, el cambio se hace durante la migración asistida, con una ventana de mantenimiento de hasta 2 horas.

**[S3]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.
>
> El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

**[S4]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede hacer hasta 60 requests por minuto.
>
> Una cuenta Pro puede hacer hasta 300 requests por minuto.
>
> Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.
>
> Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Además del límite por minuto, existe una cuota diaria. El plan Starter tiene una cuota de 10.000 llamadas por día, el plan Pro de 100.000 llamadas por día y el plan Pro Plus de 250.000 llamadas por día. El plan Enterprise no tiene cuota diaria.

---

## Grupo 13 — e02 (answer_id `f961001abcb0f5ea`)

**Pregunta:** ¿Cuál es el límite de requests por minuto de la API para una cuenta Pro?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El límite de requests por minuto para una cuenta Pro es de 300 requests por minuto.

**Citó:** S1, S2

**Afirmaciones a etiquetar:**

- `e02-c1` — Una cuenta Pro tiene un límite de 300 requests por minuto en la API.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10) — **CITADO**

> Una cuenta Starter puede hacer hasta 60 requests por minuto.
>
> Una cuenta Pro puede hacer hasta 300 requests por minuto.
>
> Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.
>
> Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

**[S2]** `novedades-2026` v2026-09 — VIGENTE (desde 2026-09-05) — **CITADO**

> El límite de la API del plan Pro aumenta de 200 a 300 requests por minuto.

**[S3]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.
>
> El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

**[S4]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Cuando una cuenta supera el límite, la API responde con el código HTTP 429 (Too Many Requests) e incluye el encabezado Retry-After, que indica cuántos segundos esperar antes de reintentar. Las llamadas rechazadas con 429 no se descuentan de la cuota diaria.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Además del límite por minuto, existe una cuota diaria. El plan Starter tiene una cuota de 10.000 llamadas por día, el plan Pro de 100.000 llamadas por día y el plan Pro Plus de 250.000 llamadas por día. El plan Enterprise no tiene cuota diaria.

---

## Grupo 14 — e28 (answer_id `9c4924fc8fce66ee`)

**Pregunta:** Una cuenta Starter llegó a su límite de facturas del mes. ¿Qué opciones tiene para seguir emitiendo y cuándo se aplicaría un cambio de plan?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Cuando una cuenta Starter alcanza su límite de 500 facturas, la emisión de nuevas facturas queda bloqueada hasta el inicio del próximo ciclo de facturación o hasta que la cuenta cambie a un plan superior; el cambio a un plan superior (por ejemplo, a Pro) se aplica de inmediato, permitiendo seguir facturando.

**Citó:** S1, S3

**Afirmaciones a etiquetar:**

- `e28-c1` — El cambio de una cuenta Starter a un plan superior (por ejemplo, Pro) se aplica de inmediato.
- `e28-c2` — Cambiar a un plan superior permite a la cuenta Starter seguir emitiendo facturas en el mismo ciclo.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> El plan Starter cuesta USD 29 por mes. Permite emitir hasta 500 facturas por mes e incluye 2 usuarios. El soporte es solo por email, con un tiempo de primera respuesta de 48 horas hábiles.
>
> En el plan Starter no se pueden agregar usuarios adicionales. Si una cuenta Starter alcanza el límite de 500 facturas, la emisión de nuevas facturas queda bloqueada hasta el inicio del próximo ciclo de facturación o hasta que la cuenta pase a un plan superior.

**[S2]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

**[S3]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> Un cambio de Starter a Pro, o de Pro a Pro Plus, se aplica de inmediato. Las facturas históricas y la configuración de la cuenta se conservan.
>
> Al pasar de Pro a Pro Plus se habilita el inicio de sesión único (SSO). Para usarlo, el Propietario o un Administrador debe configurar el proveedor de identidad en Configuración > Seguridad > SSO.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro cuesta USD 99 por mes. Permite emitir hasta 5.000 facturas por mes e incluye 10 usuarios. El soporte es por email y chat, con un tiempo de primera respuesta de 24 horas hábiles.
>
> El plan Pro incluye facturación recurrente y emisión de facturas en hasta 5 monedas distintas. Cada factura que supere el límite mensual se cobra como excedente a USD 0,02 por factura.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Además del límite por minuto, existe una cuota diaria. El plan Starter tiene una cuota de 10.000 llamadas por día, el plan Pro de 100.000 llamadas por día y el plan Pro Plus de 250.000 llamadas por día. El plan Enterprise no tiene cuota diaria.

---

## Grupo 15 — e29 (answer_id `da01ee845318e553`)

**Pregunta:** ¿Qué crédito corresponde a una cuenta Enterprise si su disponibilidad mensual fue de 99,2%?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El crédito es del 25 % de la cuota mensual.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e29-c1` — Una cuenta Enterprise con disponibilidad mensual de 99,2% recibe un crédito del 25 % de la cuota mensual.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `sla` v2026-01 — VIGENTE (desde 2026-01-01) — **CITADO**

> Si la disponibilidad mensual de una cuenta Enterprise es menor a 99,95% pero igual o mayor a 99,5%, el crédito es del 10% de la cuota mensual. Si es menor a 99,5% pero igual o mayor a 99,0%, el crédito es del 25%. Si es menor a 99,0%, el crédito es del 50%.

**[S2]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> El plan Pro Plus tiene un SLA de 99,9% de disponibilidad mensual. El plan Enterprise tiene un SLA de 99,95% de disponibilidad mensual.
>
> Los planes Starter y Pro no tienen SLA contractual. Para esos planes Kestrel mantiene un objetivo interno de 99,5% de disponibilidad, pero su incumplimiento no genera créditos.

**[S3]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> Si la disponibilidad mensual de una cuenta Pro Plus es menor a 99,9% pero igual o mayor a 99,0%, el crédito es del 10% de la cuota mensual. Si es menor a 99,0% pero igual o mayor a 95,0%, el crédito es del 25%. Si es menor a 95,0%, el crédito es del 50%.

**[S4]** `facturacion-faq` v2026-05 — VIGENTE (desde 2026-05-01)

> El ciclo de facturación comienza el día de alta de la cuenta y el cobro se realiza automáticamente con la tarjeta registrada. Los clientes Enterprise pueden pagar por transferencia bancaria con vencimiento a 30 días.

**[S5]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.
>
> El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

---

## Grupo 16 — e32 (answer_id `b9e9fb7bfe25249b`)

**Pregunta:** ¿Cuántos endpoints de webhook y cuántas requests por minuto permite una cuenta Pro Plus?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Una cuenta Pro Plus permite registrar hasta 20 endpoints de webhook y realizar hasta 600 requests por minuto.

**Citó:** S1, S2

**Afirmaciones a etiquetar:**

- `e32-c1` — Una cuenta Pro Plus puede registrar hasta 20 endpoints de webhook.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `integraciones-webhooks` v2026-09 — VIGENTE (desde 2026-09-05) — **CITADO**

> Una cuenta Starter puede registrar 1 endpoint de webhook, una cuenta Pro hasta 5 endpoints, una cuenta Pro Plus hasta 20 endpoints y una cuenta Enterprise hasta 50 endpoints.

**[S2]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10) — **CITADO**

> Una cuenta Starter puede hacer hasta 60 requests por minuto.
>
> Una cuenta Pro puede hacer hasta 300 requests por minuto.
>
> Una cuenta Pro Plus puede hacer hasta 600 requests por minuto.
>
> Una cuenta Enterprise puede hacer hasta 1.500 requests por minuto, ampliables por contrato.

**[S3]** `novedades-2026` v2026-09 — VIGENTE (desde 2026-09-05)

> El límite de la API del plan Pro aumenta de 200 a 300 requests por minuto.

**[S4]** `limites-api` v2026-04 — VIGENTE (desde 2026-04-10)

> Una cuenta Starter puede tener 1 API key activa, una cuenta Pro hasta 5 API keys y una cuenta Pro Plus hasta 20 API keys. En Enterprise el número de API keys se acuerda por contrato.
>
> El entorno sandbox tiene un límite fijo de 30 requests por minuto para todos los planes y sus datos se borran cada 30 días.

**[S5]** `guia-migracion-planes` v2026-06 — VIGENTE (desde 2026-06-01)

> Los cambios a un plan inferior se aplican al final del ciclo de facturación.
>
> Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.
>
> Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.

---

## Grupo 17 — e23 (answer_id `52e06fb2dd238384`)

**Pregunta:** ¿Cuánto dura el período de prueba gratuito y qué plan incluye?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El período de prueba gratuito dura 14 días y está disponible para el plan Pro.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e23-c1` — El período de prueba gratuito dura 14 días.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01) — **CITADO**

> Quien elige el pago anual paga 10 meses y recibe 12, es decir, obtiene dos meses sin cargo. Las cuentas nuevas pueden probar el plan Pro durante 14 días sin ingresar una tarjeta de crédito.

**[S2]** `novedades-2026` v2026-09 — VIGENTE (desde 2026-09-05)

> El límite de la API del plan Pro aumenta de 200 a 300 requests por minuto.

**[S3]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro Plus cuesta USD 199 por mes. Permite emitir hasta 20.000 facturas por mes e incluye 25 usuarios. El soporte es prioritario, con un tiempo de primera respuesta de 8 horas hábiles.
>
> El plan Pro Plus incluye todo lo del plan Pro, emisión en monedas ilimitadas e inicio de sesión único (SSO) mediante SAML. Cada factura que supere el límite mensual se cobra como excedente a USD 0,015 por factura.

**[S4]** `planes-y-precios` v2026-03 — VIGENTE (desde 2026-03-01)

> El plan Pro cuesta USD 99 por mes. Permite emitir hasta 5.000 facturas por mes e incluye 10 usuarios. El soporte es por email y chat, con un tiempo de primera respuesta de 24 horas hábiles.
>
> El plan Pro incluye facturación recurrente y emisión de facturas en hasta 5 monedas distintas. Cada factura que supere el límite mensual se cobra como excedente a USD 0,02 por factura.

**[S5]** `sla` v2026-01 — VIGENTE (desde 2026-01-01)

> El plan Pro Plus tiene un SLA de 99,9% de disponibilidad mensual. El plan Enterprise tiene un SLA de 99,95% de disponibilidad mensual.
>
> Los planes Starter y Pro no tienen SLA contractual. Para esos planes Kestrel mantiene un objetivo interno de 99,5% de disponibilidad, pero su incumplimiento no genera créditos.

---

## Grupo 18 — e39 (answer_id `f2f5c2113056ea44`)

**Pregunta:** ¿Cuántos días hábiles tarda en acreditarse un reembolso ya aprobado?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de 5 a 10 días hábiles.

**Citó:** S1

**Afirmaciones a etiquetar:**

- `e39-c1` — Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de 5 a 10 días hábiles.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01) — **CITADO**

> El cliente puede solicitarlo desde Configuración > Facturación > Solicitar reembolso, o mediante un ticket a soporte. El equipo de Finanzas aprueba o rechaza la solicitud en un plazo de hasta 5 días hábiles. Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de 5 a 10 días hábiles.

**[S2]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> El cliente debe enviar un ticket a soporte. El equipo de Finanzas aprueba o rechaza la solicitud en un plazo de hasta 10 días hábiles. Una vez aprobado, el reembolso se acredita en el medio de pago original en un plazo de hasta 15 días hábiles.

**[S3]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Si un cliente con pago anual cancela dentro de los primeros 60 días desde el cobro, recibe un reembolso prorrateado por los meses completos no utilizados. Pasados esos 60 días, el pago anual no es reembolsable.

**[S4]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 30 días corridos posteriores al primer cobro. Las renovaciones mensuales posteriores al primer cobro no son reembolsables.

**[S5]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Si un cliente con pago anual cancela dentro de los primeros 30 días desde el cobro, recibe un reembolso prorrateado por los meses completos no utilizados. Pasados esos 30 días, el pago anual no es reembolsable.

---

## Grupo 19 — e10 (answer_id `f82fbbdcf6856814`)

**Pregunta:** ¿Cuál era el plazo para pedir el reembolso de un plan mensual antes de marzo de 2026?

**Alcance temporal (regla de la Etapa 2):** `historical_anchored`

**Respuesta:** El plazo para solicitar el reembolso de una suscripción mensual nueva era de 14 días corridos después del primer cobro.

**Citó:** S5

**Afirmaciones a etiquetar:**

- `e10-c1` — El plazo para solicitar el reembolso de una suscripción mensual nueva era de 14 días corridos después del primer cobro.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Esta política rige para todas las solicitudes de reembolso recibidas desde el 1 de marzo de 2026.

**[S2]** `novedades-2026` v2026-09 — VIGENTE (desde 2026-09-05)

> Entra en vigencia la versión 3 de la política de reembolsos, que reemplaza a la versión 2.

**[S3]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Documento histórico. Esta versión estuvo vigente desde el 1 de julio de 2024 hasta el 28 de febrero de 2026 y fue reemplazada por la versión 3.

**[S4]** `politica-reembolsos-v3` v3 — VIGENTE (desde 2026-03-01)

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 30 días corridos posteriores al primer cobro. Las renovaciones mensuales posteriores al primer cobro no son reembolsables.

**[S5]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3) — **CITADO**

> Una suscripción mensual nueva puede recibir un reembolso total si el cliente lo solicita dentro de los 14 días corridos posteriores al primer cobro. Las renovaciones mensuales no son reembolsables.

---

## Grupo 20 — e14 (answer_id `6f2570ca10e84a62`)

**Pregunta:** Si un cliente cancela su cuenta, ¿durante cuánto tiempo puede exportar sus datos y en qué formatos?

**Alcance temporal (regla de la Etapa 2):** `current`

**Respuesta:** El cliente puede exportar sus datos durante los 30 días de modo solo lectura y los formatos disponibles son CSV y JSON.

**Citó:** S1, S2

**Afirmaciones a etiquetar:**

- `e14-c1` — Tras cancelar la cuenta, el cliente puede exportar sus datos durante los 30 días de modo solo lectura.
- `e14-c2` — Los datos pueden exportarse en formato CSV y JSON.

**Fragmentos del contexto (en el orden entregado al generador):**

**[S1]** `retencion-de-datos` v2026-06 — VIGENTE (desde 2026-06-01) — **CITADO**

> Cuando una cuenta se cancela, pasa a modo de solo lectura durante 30 días. Durante ese período el cliente puede consultar y exportar sus datos, pero no puede emitir facturas.
>
> Al terminar el período de solo lectura, los datos de clientes y productos se eliminan en un plazo de 60 días. Las facturas emitidas se conservan según el plazo de su región. Las copias de seguridad que contienen datos eliminados se purgan a los 35 días.

**[S2]** `integraciones-webhooks` v2026-09 — VIGENTE (desde 2026-09-05) — **CITADO**

> Los datos de facturas, clientes y pagos pueden exportarse en formato CSV o JSON desde el panel en todos los planes. Las exportaciones programadas, diarias o semanales, están disponibles en los planes Pro Plus y Enterprise.

**[S3]** `retencion-de-datos` v2026-06 — VIGENTE (desde 2026-06-01)

> Los logs de llamadas a la API se conservan durante 90 días en todas las regiones. Las cuentas Enterprise pueden extender la retención de logs hasta 365 días.

**[S4]** `procedimiento-incidentes` v2026-02 — VIGENTE (desde 2026-02-01)

> SEV1: el servicio está caído o la emisión de facturas está bloqueada para múltiples clientes. El tiempo de respuesta objetivo es de 15 minutos.
>
> SEV2: una funcionalidad está degradada pero existe una alternativa temporal. El tiempo de respuesta objetivo es de 1 hora.
>
> SEV3: un problema menor que afecta a un solo cliente. El tiempo de respuesta objetivo es de 1 día hábil.

**[S5]** `politica-reembolsos-v2` v2 — HISTÓRICO / deprecated (vigente del 2024-07-01 al 2026-02-28; reemplazado por politica-reembolsos-v3)

> Si un cliente con pago anual cancela dentro de los primeros 30 días desde el cobro, recibe un reembolso prorrateado por los meses completos no utilizados. Pasados esos 30 días, el pago anual no es reembolsable.

---
