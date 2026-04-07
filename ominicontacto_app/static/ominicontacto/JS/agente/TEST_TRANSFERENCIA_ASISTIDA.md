# Prueba: Transferencia Asistida - Verificación de Aceptación de Nuevas Llamadas

## Objetivo

Verificar que después de completar una transferencia asistida, el componente PhoneJS queda en un estado correcto que permite aceptar nuevas llamadas entrantes sin rechazarlas con error 480 Temporarily Unavailable.

## Contexto del Problema

**Problema Original:**
- Después de completar una transferencia asistida, `currentSession` y `session_data` no se limpiaban inmediatamente
- El backend colgaba el canal del agente A, pero el evento `ended` podía tardar en llegar
- Durante este tiempo, nuevos INVITE entrantes eran rechazados porque `currentSession !== undefined`
- Esto causaba que nuevas llamadas fueran rechazadas con 480 Temporarily Unavailable

**Solución Implementada:**
- Limpiar inmediatamente `currentSession` y `session_data` después de `transferAccepted()` en `completeConsultativeTransfer()`
- No esperar al evento `ended` para limpiar la sesión en este caso específico
- Agregar verificación de `session_data` en el handler `ended` para evitar errores si ya fue limpiado

## Prerequisitos

1. **Entorno de Prueba:**
   - Sistema OML desplegado y funcionando
   - Asterisk configurado y corriendo
   - Redis funcionando
   - Al menos 2 agentes configurados y logueados
   - Campaña activa con cola de llamadas

2. **Herramientas:**
   - Navegador con consola de desarrollador abierta (F12)
   - Acceso a logs de Asterisk
   - Acceso a logs del backend ACD (opcional pero recomendado)

3. **Configuración:**
   - Agente A: Agente que inicia la transferencia
   - Agente B: Agente destino de la transferencia
   - Cliente: Llamada entrante que será transferida

## Pasos de Prueba

### Paso 1: Preparación del Entorno

1. **Abrir consola del navegador:**
   - Abrir DevTools (F12)
   - Ir a la pestaña "Console"
   - Filtrar por "phone_logger" para ver solo logs relevantes

2. **Verificar estado inicial:**
   - Agente A debe estar logueado y en estado "Ready" o "Paused"
   - Agente B debe estar logueado y disponible
   - Verificar que no hay llamadas activas

### Paso 2: Iniciar Llamada y Transferencia Asistida

1. **Recibir llamada entrante:**
   - Generar una llamada entrante hacia Agente A
   - Verificar que Agente A acepta la llamada
   - Estado debe cambiar a "OnCall"

2. **Iniciar transferencia asistida:**
   - Desde la interfaz de Agente A, seleccionar "Transferencia Asistida"
   - Seleccionar Agente B como destino
   - Confirmar inicio de transferencia
   - Verificar en logs: `phone_logger.log('Transferencia consultativa iniciada')`
   - Estado debe cambiar a "Transfering"
   - Debe aparecer el botón "Completar Transferencia"

3. **Verificar estado de consulta:**
   - Agente A y Agente B deben poder hablar entre sí
   - Cliente debe estar en espera (MOH activo)
   - Verificar en consola que `self.phone.currentSession !== undefined`
   - Verificar que `self.phone.session_data` está definido

### Paso 3: Completar Transferencia Asistida

1. **Completar la transferencia:**
   - Desde la interfaz de Agente A, presionar "Completar Transferencia"
   - Verificar en logs del navegador:
     ```
     phone_logger.log('Transferencia consultativa completada exitosamente')
     ```
   - Verificar que el botón "Completar Transferencia" se oculta
   - Estado debe cambiar de "Transfering" a "Ready"

2. **Verificar limpieza inmediata de sesión:**
   - **CRÍTICO:** Inmediatamente después de presionar "Completar Transferencia", verificar en consola:
     ```javascript
     // En la consola del navegador, ejecutar:
     phoneJsController.phone.currentSession
     // Debe retornar: undefined
     
     phoneJsController.phone.session_data
     // Debe retornar: undefined
     ```
   - Si estos valores son `undefined`, la limpieza funcionó correctamente
   - Si aún tienen valores, hay un problema con la implementación

3. **Verificar pausa ACW:**
   - Después de completar la transferencia, debe activarse automáticamente la pausa ACW
   - Estado debe ser "Paused" con pausa ACW

### Paso 4: Verificar Aceptación de Nueva Llamada (Prueba Principal)

1. **Generar nueva llamada entrante:**
   - **IMPORTANTE:** Generar la nueva llamada lo más rápido posible después de completar la transferencia (dentro de 1-2 segundos)
   - Esto prueba que la limpieza inmediata funciona y no hay race condition

2. **Verificar aceptación:**
   - La nueva llamada debe ser aceptada correctamente
   - NO debe ser rechazada con 480 Temporarily Unavailable
   - Verificar en logs del navegador:
     ```
     phone_logger.log('newRTCSession')
     // NO debe aparecer:
     // e.session.terminate() siendo llamado
     ```
   - Verificar en consola que `currentSession` ahora tiene la nueva sesión:
     ```javascript
     phoneJsController.phone.currentSession
     // Debe retornar un objeto Session (no undefined)
     ```

3. **Verificar flujo completo:**
   - La nueva llamada debe poder ser contestada normalmente
   - Estado debe cambiar a "ReceivingCall" y luego a "OnCall" al aceptar

### Paso 5: Verificar Manejo del Evento 'ended' Tardío

1. **Esperar evento 'ended':**
   - Después de completar la transferencia, el backend cuelga el canal del Agente A
   - El evento `ended` puede llegar después de que ya limpiamos la sesión
   - Verificar en logs que no hay errores cuando llega el evento `ended`:
     ```
     phone_logger.log('session: ended')
     // NO debe aparecer error de "Cannot read property 'is_call' of undefined"
     ```

2. **Verificar handler onCallEnded:**
   - El handler `onCallEnded` debe manejar correctamente el caso cuando `session_data` es `undefined`
   - No debe causar errores en la consola
   - Verificar que el estado sigue siendo correcto después del evento

## Verificaciones Adicionales

### Verificación de Logs del Navegador

Buscar en la consola del navegador los siguientes mensajes en orden:

1. **Al completar transferencia:**
   ```
   Transferencia consultativa completada exitosamente
   FSM: onReady (o similar, dependiendo del estado)
   ```

2. **Al recibir nueva llamada:**
   ```
   newRTCSession
   session: progress
   session: accepted
   ```

3. **NO debe aparecer:**
   ```
   e.session.terminate()  // Esto indicaría que la llamada fue rechazada
   Cannot read property 'is_call' of undefined  // Error si session_data es undefined
   ```

### Verificación de Estado del FSM

Verificar que el estado de la máquina de estados (FSM) es correcto en cada paso:

1. **Antes de transferencia:** `OnCall`
2. **Durante consulta:** `Transfering`
3. **Después de completar:** `Ready` o `Paused` (con ACW)
4. **Al recibir nueva llamada:** `ReceivingCall`
5. **Al aceptar nueva llamada:** `OnCall`

### Verificación de Código (Inspección Manual)

Si es posible, agregar logs temporales para verificar el flujo:

```javascript
// En completeConsultativeTransfer(), después de cleanLastCallData():
console.log('DEBUG: currentSession después de limpieza:', self.phone.currentSession);
console.log('DEBUG: session_data después de limpieza:', self.phone.session_data);

// En phoneJsSip.js, en el handler 'ended':
console.log('DEBUG: session_data en ended:', self.session_data);
```

## Casos Edge a Considerar

1. **Llamada muy rápida:**
   - Generar nueva llamada inmediatamente después de completar transferencia (< 500ms)
   - Verificar que aún funciona correctamente

2. **Múltiples llamadas:**
   - Completar transferencia
   - Generar 2-3 llamadas entrantes rápidamente
   - Verificar que solo la primera es aceptada y las demás son rechazadas correctamente (comportamiento esperado)

3. **Cancelar transferencia:**
   - Iniciar transferencia asistida
   - Cancelar en lugar de completar
   - Verificar que nuevas llamadas se aceptan correctamente

4. **Error en completar transferencia:**
   - Simular error al completar transferencia (ej: desconectar backend)
   - Verificar que el estado se maneja correctamente

## Resultado Esperado

✅ **Prueba Exitosa:**
- Después de completar transferencia asistida, `currentSession` y `session_data` son `undefined` inmediatamente
- Nueva llamada entrante es aceptada correctamente sin rechazo 480
- No hay errores en la consola del navegador
- El evento `ended` tardío no causa errores
- El estado FSM es correcto en todos los pasos

❌ **Prueba Fallida:**
- `currentSession` o `session_data` no se limpian inmediatamente
- Nueva llamada es rechazada con 480 Temporarily Unavailable
- Aparecen errores en la consola relacionados con `session_data` undefined
- El estado FSM no es correcto

## Notas de Depuración

Si la prueba falla:

1. **Verificar implementación:**
   - Revisar que `cleanLastCallData()` se llama después de `transferAccepted()` en `completeConsultativeTransfer()`
   - Verificar que el handler `ended` verifica `session_data` antes de acceder a propiedades

2. **Verificar timing:**
   - El problema original era un race condition
   - Si aún ocurre, puede ser que la limpieza no sea lo suficientemente rápida
   - Considerar agregar un pequeño delay antes de verificar o generar nueva llamada

3. **Verificar logs del backend:**
   - Revisar logs de ACD para ver si hay errores en el proceso de transferencia
   - Verificar que el backend efectivamente cuelga el canal del Agente A

4. **Verificar estado de Redis:**
   - El estado de la transferencia se guarda en Redis
   - Verificar que el estado se actualiza correctamente después de completar

## Referencias

- Plan de implementación: `/Users/fpignataro/.cursor/plans/fix_transferencia_asistida_bloquea_nuevas_llamadas_15720919.plan.md`
- Código modificado:
  - `phoneJsController.js`: Función `completeConsultativeTransfer()` (línea ~1710)
  - `phoneJsSip.js`: Handler `ended` (línea ~227)
  - `phoneJsSip.js`: Función `cleanLastCallData()` (línea ~653)
