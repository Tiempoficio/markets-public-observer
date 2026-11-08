# Tiempoficio: recibos de precios publicos

Recolector independiente, sin dependencias externas, sin estrategia privada, IA, cuentas de exchange, claves ni ordenes. Solo consulta hora y cuatro velas cerradas de BTCUSDT y ETHUSDT (1d y 4h) en el dominio publico de datos de Binance. Las cinco solicitudes tienen limites de tiempo y tamano; no se siguen redirecciones ni se utilizan proxies o credenciales del entorno.

**Estado del 8 de noviembre de 2026: primera ejecucion externa verificada.** Repositorio publico dedicado: [Tiempoficio/markets-public-observer](https://github.com/Tiempoficio/markets-public-observer). La recogida puede ejecutarse sin el PC local. La programacion esta configurada cada 15 minutos, pero una ejecucion manual correcta NO demuestra continuidad futura ni puntualidad garantizada.

Primera prueba externa: [ejecucion 42480649835](https://github.com/Tiempoficio/markets-public-observer/actions/runs/42480649835), completada correctamente a las 12:31:37 UTC. Diez pruebas aprobadas y cinco solicitudes publicas; cuatro velas guardadas en [el recibo original](https://github.com/Tiempoficio/markets-public-observer/blob/19bfa1c1169352f40cf6f1222c2c678c34ca1441/data/2026-11-08/42480649835-1.json). El commit de datos solo anade ese archivo y desciende del codigo ejecutado `556c6332d9749bebd902bdf91b9c9b6c128eccec`.

Esta captura inicial recibio las velas de 4h unos 31 minutos despues de su cierre. No cuenta como captura puntual bajo el limite de 30 minutos de H6 y NO se importa como evidencia prospectiva: es una prueba tecnica de recogida y persistencia. No se rellenan huecos anteriores con fechas retroactivas.

## Que publica y que no

Cada ejecucion guarda un JSON nuevo con OHLCV validado, hora real de solicitud y recepcion, huella de respuesta, retraso respecto al cierre y procedencia. En Actions incluye la ejecucion, intento y commit del codigo. Nunca sustituye recibos existentes. Los fallos terminan con codigo de error visible en Actions y no generan un recibo de exito. No hay reintentos ocultos ni fechas retroactivas.

Los recibos acreditan que se recibieron precios, NO que una estrategia se ejecuto en ese momento, NO que H6 sea rentable y NO que se puedan invertir 100 EUR. La evaluacion H6 sigue siendo local: apagar el PC tambien pausa sus decisiones. Todavia no existe importacion de estos recibos al diario privado; habra que verificar su procedencia y tiempos sin reescribir el pasado.

## Comprobacion local

```powershell
python -m unittest -v
python collector.py --output data-local
```

No subir la carpeta `data-local`: las pruebas locales no son ejecuciones externas. El programa usa un identificador local distinto. No copiar codigo, bases de datos, `.env`, registros privados ni carpetas del proyecto Markets a este repositorio.

## Publicacion aislada

Mantener este repositorio PUBLICO exclusivo bajo Tiempoficio. El codigo publicado se limita a esta lista; `data/` contendra solamente los recibos publicos generados por Actions:

- `collector.py`
- `test_collector.py`
- `.github/workflows/observe.yml`
- `.gitignore`
- `README.md`

El workflow solo permite el repositorio publico y su rama predeterminada, usa un runner estandar `ubuntu-24.04` y no usa artefactos, caches, Packages, modelos ni proveedores de pago. Emplea el permiso temporal `contents: write` del workflow para guardar SOLO los recibos en Git; no requiere un token personal nuevo. La accion oficial checkout queda fijada a un commit verificado.

Segun [facturacion oficial de GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions), los runners estandar de repositorios publicos son gratuitos. Los runners grandes y el almacenamiento de artefactos/cache tienen reglas distintas: no se usan aqui. Si cambian las condiciones, el tipo de runner o la visibilidad, detener y revisar antes de activar. No se ha contratado nada ni modificado una cuenta de facturacion.

Para comprobar cambios posteriores: ejecutar manualmente `Observe public prices` y verificar exito, commit nuevo, archivo JSON, SHA del codigo, tiempos de recepcion reales y cero secretos. Confirmar permisos de escritura del workflow si el push es rechazado; no crear un token de amplio acceso para sortearlo.

## Limites operativos y revision critica

El horario propuesto es cada 15 minutos fuera del minuto cero. [GitHub puede retrasar u omitir ejecuciones programadas](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), y puede desactivar programaciones de repositorios publicos sin actividad. No es infraestructura de ejecucion de trading ni tiene continuidad garantizada. No se imputan capturas omitidas. Revisar actividad y espacio del repositorio antes de ampliar la frecuencia o las series.

Se mantienen deliberadamente separados transporte publico y estrategia privada. La siguiente mejora util sera un importador con verificacion de commits y recibos, no operar dinero ni trasladar claves a Actions. Los hashes detectan cambios accidentales; no constituyen un sellado notarial ni impiden a un administrador reescribir Git.

La primera ejecucion aprobo las pruebas y el push, pero aviso de la retirada de Node 20 en checkout v4. Se actualiza exclusivamente la accion oficial a v7.0.1, fijada al commit `3d3c42e5aac5ba805825da76410c181273ba90b1`, tras revisar su version publicada, runtime Node 24 y compatibilidad con `git push`. No se modifica el recolector ni se reescribe el primer recibo. Los registros se conservan con el commit que realmente los produjo.

Fuente de la API: [Binance Market Data Only](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only). No se utiliza una cuenta ni autenticacion.
