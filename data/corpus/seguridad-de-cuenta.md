+++
doc_id = "seguridad-de-cuenta"
title = "Seguridad de la cuenta y control de acceso"
version = "2026-01"
effective_date = "2026-01-15"
status = "active"
+++
# Seguridad de la cuenta y control de acceso

## Autenticación en dos pasos (2FA)

Desde el 15 de enero de 2026, la autenticación en dos pasos es obligatoria para los usuarios con rol Propietario en todos los planes. Los métodos aceptados son aplicaciones TOTP y llaves de seguridad FIDO2. Kestrel no admite códigos por SMS.

Si un usuario pierde acceso a su segundo factor, soporte debe verificar su identidad antes de restablecerlo. El restablecimiento se completa en un plazo de 2 días hábiles.

## Inicio de sesión único (SSO) y SCIM

El inicio de sesión único mediante SAML está disponible en los planes Pro Plus y Enterprise. El aprovisionamiento automático de usuarios mediante SCIM está disponible solo en el plan Enterprise.

## Roles de usuario

Kestrel tiene cuatro roles. El Propietario controla la suscripción y todos los permisos. El Administrador gestiona usuarios y configuración, pero no la suscripción. El Contador puede emitir facturas y ver reportes, pero no cambiar la configuración. El rol Solo lectura puede consultar datos sin modificarlos.

## Sesiones y bloqueos

Las sesiones expiran tras 12 horas de inactividad. En el plan Enterprise ese plazo es configurable entre 1 y 24 horas.

Después de 5 intentos fallidos de inicio de sesión, la cuenta del usuario se bloquea durante 15 minutos.

## Restricción por IP

La lista de direcciones IP permitidas (IP allowlist) está disponible solo en el plan Enterprise.
