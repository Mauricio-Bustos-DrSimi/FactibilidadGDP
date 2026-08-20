# Cutover futuro de 8003 a 8002

No ejecutar todavía.

1. Anunciar una ventana breve sin escrituras en el Gestor antiguo.
2. Bloquear nuevas escrituras en 8002 sin detener aún sus lecturas.
3. Esperar `lag_seconds=0`, inbox vacío y ningún evento en reintento/fallido.
4. Ejecutar reconciliación final y exigir cero diferencias aceptadas.
5. Respaldar y verificar restauración de ambas bases y documentos.
6. Detener el consumidor CDC conservando su último LSN documentado.
7. Detener el servicio antiguo, sin borrar su unidad, código, base ni archivos.
8. Cambiar `APP_PORT` del servicio FactibilidadGDP a 8002.
9. Mantener `SESSION_COOKIE_NAME=factibilidad_session` para no colisionar con cookies antiguas.
10. Desactivar `SHADOW_MODE` únicamente para funcionalidades autorizadas.
11. Habilitar correos solo después de una prueba controlada de destinatarios y deduplicación.
12. Verificar `/health`, base, autenticación, documentos, Factibilidad y correo.

Rollback: detener el servicio nuevo, restaurar su puerto 8003, reactivar el servicio anterior y
reanudar escrituras en 8002. No se revierte ni mezcla información de `factibilidad.*` con la base
anterior durante el rollback.
