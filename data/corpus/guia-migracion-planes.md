+++
doc_id = "guia-migracion-planes"
title = "Guía de cambios y migración entre planes"
version = "2026-06"
effective_date = "2026-06-01"
status = "active"
+++
# Guía de cambios y migración entre planes

## Pasar a un plan superior

Un cambio de Starter a Pro, o de Pro a Pro Plus, se aplica de inmediato. Las facturas históricas y la configuración de la cuenta se conservan.

Al pasar de Pro a Pro Plus se habilita el inicio de sesión único (SSO). Para usarlo, el Propietario o un Administrador debe configurar el proveedor de identidad en Configuración > Seguridad > SSO.

## Migración a Enterprise

La migración a Enterprise requiere un contrato firmado. El gerente de cuenta coordina la transición en un plazo de hasta 10 días hábiles y, mientras tanto, el plan anterior sigue vigente.

La retención extendida de logs y las demás funciones exclusivas de Enterprise se activan cuando la migración finaliza. Si el cliente pide cambiar de región, el cambio se hace durante la migración asistida, con una ventana de mantenimiento de hasta 2 horas.

## Pasar a un plan inferior

Los cambios a un plan inferior se aplican al final del ciclo de facturación.

Al pasar de Pro Plus a Pro, el SSO se desactiva y los usuarios vuelven a iniciar sesión con contraseña y segundo factor. Si la cuenta tiene más usuarios que los incluidos en el plan Pro, los usuarios excedentes se mantienen activos y se cobran como usuarios adicionales.

Al pasar a Starter, la cuenta no puede tener más de 2 usuarios activos y el Propietario debe desactivar el resto antes del cambio. También quedan deshabilitados todos los endpoints de webhook excepto el creado más recientemente.
