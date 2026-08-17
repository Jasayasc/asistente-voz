# SDD ledger — plan: docs/superpowers/plans/2026-08-16-hito1-version-windows.md

Rama: hito-1 (base: c2a13aa en main)
Entorno: Python 3.13.7, venv en .venv/, todas las dependencias resuelven.
Modo: verificaciones manuales (visuales, auditivas, claves de API) diferidas al final.

Defecto del plan detectado en revisión previa: ninguna tarea crea el entorno
virtual ni instala dependencias. Hecho por el controlador antes de la Tarea 1.

Task 1: complete (commits c2a13aa..8a6f216, review clean)
Task 1: minor (deferred): import os sin usar en tests/test_config.py (venía del código verbatim del plan)
Task 1: minor (deferred): README.md placeholder — resuelto por el controlador, la Tarea 18 lo reescribe entero
Task 2: review 1 — spec ❌ (1 Important): decodificar lanza TypeError en rms:null, contrato promete ValueError; riesgo directo sobre "cara nunca muere"
Task 2: adjudicado por el controlador — el contrato del plan gobierna sobre su código de ejemplo; se manda arreglar
Task 2: fix round 1/5 en curso (implementador a0e31d9f2ac920160 reanudado)
Task 2: fix round 1/5 (1 addressed, 0 open; commits 876d277..74855ed)
Task 2: complete (commits 8a6f216..74855ed, review clean, 12/12 tests)
Task 3: complete (commits 74855ed..e2a421d, review clean, 18/18 tests)
Task 3: minor (deferred): constante CAMPOS muerta en src/cara/parametros.py (venía del código del plan); confirmado por el controlador que ningún módulo posterior la importa
Task 4: complete (commits e2a421d..340eb61, review clean, 27/27 tests)
Task 4: minor (deferred): umbral 0.1 del test de parpadeo acoplado a DURACION_PARPADEO y al dt=1/60 del test; fragilidad latente, no defecto actual
Task 4: minor (deferred): INTERVALO_PARPADEO_LENTO (PENSANDO) sin test cuantitativo propio
Task 5: complete (commits 340eb61..21e9ba1, review clean, 33/33 tests)
Task 5: minor (deferred): docstring dice "tres pasos" y enumera dos (texto del plan)
Task 5: minor (deferred): rms infinito envenenaría el máximo móvil permanentemente; imposible desde audio real, sin test
Task 5: minor (deferred): el máximo móvil no decae durante reposar(), solo en procesar()
Task 6: defecto del plan detectado por el controlador antes de despachar — el fixture pygame_headless declara el parámetro inexistente monkeypatch_session; se instruye eliminarlo
Task 6: complete (commits 21e9ba1..c5c47fe, review clean, 40/40 tests)
Task 6: minor (deferred): topes max(1,..)/max(2,..) en píxeles crudos, no fracciones de lado
Task 6: minor (deferred): literales 0.02/0.05 de la sonrisa sin constante nombrada (del plan)
Task 6: minor (deferred): test_el_lienzo_esta_centrado no cubre origen_y en orientación vertical
Task 7: review 1 — spec ✅, calidad ❌ (3 Important, todos del código del plan, todos contra "cara nunca muere"):
  1. except OSError: return en _bucle no distingue apagado de error recuperable (ECONNABORTED/EMFILE en ARM) -> proceso vivo pero sordo, sin log
  2. sin red de seguridad: RecursionError de json.loads anidado escapa del except ValueError y mata el hilo
  3. buffer `pendiente` sin tope: reescaneo cuadratico + OOM en la Pi de 1 GB con un par que no manda \n
Task 7: fix round 1/5 en curso (implementador a7d31e653880943f7 reanudado)
Task 7: minor (deferred): import time sin usar en src/cara/__main__.py
Task 7: minor (deferred): SO_REUSEADDR permite en Windows una segunda instancia viva sobre el mismo puerto sin EADDRINUSE
Task 7: minor (deferred): los 6 tests de socket pasarian igual sin el lock; no cubren acumulacion de buffer entre recv ni que el hilo muera tras detener()
Task 7: minor (deferred): 'main' en ingles, contra la norma de nombres en espanol (mandado por el plan, idiomatico)

RIESGO PARA EL HITO 2 (Raspberry Pi) — detectado en la revision de la Tarea 7, no es defecto de esta tarea:
  El suavizado es por frame, no por segundo. interpolar() usa SUAVIZADO fijo y Lipsync usa ATAQUE/LIBERACION fijos,
  ignorando dt. A 60 fps una transicion dura ~200 ms; en una Pi 3B a 20 fps durara ~600 ms y el lipsync ira
  visiblemente retrasado respecto al audio. Origen: diseno de las Tareas 3 y 5. Debe corregirse antes del
  portado a la Pi, escalando los factores por dt.
Task 7: fix round 1/5 (3 addressed, 0 open; commits e734482..d9d49a8; 49/49 tests, 23 repeticiones sin inestabilidad)
Task 7: complete (commits c5c47fe..d9d49a8, review clean)
Task 7: minor (deferred): el reintento de accept() tras error recuperable no tiene backoff; un EMFILE sostenido
  produciria un bucle cerrado de accept+log quemando CPU en la Pi. Probabilidad baja (exige fuga de descriptores),
  arreglo trivial (un sleep corto). PARA TRIAJE EN LA REVISION FINAL.
Task 7: PENDIENTE MANUAL: verificacion visual de la cara (Step 7 del brief), diferida al bloque final
Task 8: review 1 — codigo de produccion ✅ (nunca lanza, backoff correcto, sin fugas de fd); 1 Important en el test:
  el revisor MIDIO que conectar a 127.0.0.1:1 en Windows agota el timeout de 1s en vez de fallar rapido.
  Coste real del test = 1s timeout + 1s backoff = 2s contra presupuesto de 3s. Margen 1/3, no el "amplio"
  que afirmaba el informe. Flake latente en la Pi 3B.
Task 8: adjudicado — el hallazgo es correcto; se arregla el test usando un puerto efimero cerrado (rechazo
  inmediato) en vez del puerto 1, dejando margen 3x. Sin tocar la interfaz publica.
Task 8: tambien se pide cubrir "conexion cortada a mitad de envio", nombrado en el requisito rector y sin test
Task 8: fix round 1/5 en curso (implementador a29f60d5a55619538 reanudado)
Task 8: fix round 1/5 (0 addressed, 1 open; commit 8824cc2) — el implementador MIDIO que el arreglo propuesto
  por el controlador (puerto efimero cerrado) no cierra el margen en Windows: el timeout de 1s del cliente
  se dispara igual. Reporto correcto del implementador, adjudicacion del controlador equivocada.
  Ganancia real de la ronda: nuevo test de corte a mitad de envio (margen 3x).
Task 8: fix round 2/5 en curso — atacar el backoff en vez del puerto: ESPERA_RECONEXION inyectable por
  constructor con la constante como predeterminado (costura legitima, ningun llamador cambia).
Task 8: fix round 2/5 (2 addressed, 0 open; commits f1aa518..d9e006d)
  Margen del test de reconexion: 1.36x -> 2.8x medido en 8 ejecuciones. El revisor argumento que el segundo
  restante es un plazo de reloj del SO dentro de create_connection, no trabajo de CPU, asi que una Pi mas
  lenta no lo multiplica: el margen es real.
Task 8: complete (commits d9d49a8..d9e006d, review clean, 54/54 tests)
Task 8: minor (deferred): _puerto_cerrado tiene una ventana TOCTOU teorica entre close() y el connect del test
LECCION: la adjudicacion del controlador en la ronda 1 fue incorrecta y la medicion del implementador la
  corrigio. Pedir numeros en vez de impresiones es lo que lo hizo visible.
Task 9: review 1 — spec ✅ (constantes, API, callback sin bloqueo, test de descarte demuestra CUALES bloques
  sobreviven y en que orden). 1 Important + 2 Minor, todos en captura.py:
  1. (Important) fuga del stream si start() falla: __enter__ lanza -> Python no llama a __exit__ -> descriptor
     de audio perdido sin forma de cerrarlo. Fallo esperable en la Pi con micro I2S.
  2. (Minor) iniciar() dos veces deja el primer stream huerfano
  3. (Minor) carrera get_nowait/put_nowait descarta el bloque nuevo aunque acabe de quedar sitio
Task 9: fix round 1/5 en curso (implementador abee516829a153cb4 reanudado, los tres hallazgos)
Task 9: PENDIENTE MANUAL: grabar y escuchar prueba.wav (Step 4 del brief), diferido al bloque final
Task 9: fix round 1/5 (3 addressed, 0 open; commits bd8f524..c2d526f, 61/61 tests)
Task 9: complete (commits d9e006d..c2d526f, review clean)
Task 9: minor (deferred): datos[:,0].copy() en _callback queda fuera de todo try/except; un MemoryError
  escaparia del callback de PortAudio. Riesgo preexistente del plan, no introducido por el arreglo.
  PARA TRIAJE EN LA REVISION FINAL: es la unica via por la que una excepcion puede escapar del callback.
Task 9: minor (deferred): si stream.close() lanza dentro del manejo de fallo de iniciar(), sustituye la
  excepcion original de start() en vez de encadenarla explicitamente
Task 10: review 1 — spec ✅ (los tres comportamientos clave correctos, reiniciar() limpia todo, aritmetica sana).
  1 Important (plan-mandated): int() trunca en vez de redondear -> segundos_silencio=1.0 entrega 0.96s.
  Sesgo unidireccional, acotado a <80ms. Adjudicado por el controlador: se arregla, es de una linea.
  1 Minor promovido a la misma ronda: ningun test se acerca al umbral (RMS de prueba 12x por encima),
  una regresion >= a > pasaria desapercibida.
Task 10: fix round 1/5 en curso (implementador a341f8906f33bf435 reanudado)
Task 10: fix round 1/5 (1 addressed, 1 open; commit b9303cf)
  Redondeo ADDRESSED. Buen criterio del implementador: int(x+0.5) en vez de round(), porque round(12.5)=12
  en Python (redondeo bancario) y habria fallado el requisito.
  Tests de frontera NOT ADDRESSED: con amplitudes int16 es imposible caer en RMS 0.02 exacto (haria falta
  amplitud 655.36). Los tres tests rodean el umbral pero ninguno lo iguala, asi que la regresion >= a >
  seguiria pasando.
Task 10: fix round 2/5 en curso — invertir la dependencia: elegir el umbral a partir de una amplitud entera
  en vez de buscar la amplitud que encaje con el umbral. Se exige demostrar que el test falla al cambiar
  >= por > y vuelve a pasar al deshacerlo.
Task 10: fix round 2/5 (1 addressed, 0 open; commit 1709c86, 74/74 tests)
  El test nuevo usa amplitud 512 -> 512/32768 = 0.015625, una fraccion binaria exacta (2^-6), asi que
  energia y umbral coinciden bit a bit sin error de coma flotante. Demostrado con las tres ejecuciones:
  pasa con >=, FALLA con >, vuelve a pasar al deshacer.
Task 10: complete (commits c2d526f..1709c86, review clean)
Task 10: minor (deferred): los mensajes de commit de las dos rondas de arreglo estan en INGLES
  ("Fix: rounding bias...", "Fix: add regression-proof...") contra la restriccion global de mensajes en
  espanol. Historial ya escrito; no se reescribe. Vigilar en tareas restantes.
Task 10: el implementador dejo un test_output.txt suelto en la raiz; eliminado por el controlador.
Task 11: complete (commits 1709c86..0b21e5b, review clean, 80/80 tests)
  Sonda de API confirmo que la clave del modelo es 'hey_jarvis', coincide con lo que asumia el plan.
  Tests con modelo falso inyectado por monkeypatch: sin descargas, sin ONNX, sin audio.
  El test de frontera usa 0.5 == 0.5 (exactamente representable) y falla si >= pasa a >.
  El test de float usa np.float32, que NO es subclase de float, asi que detecta si se quita la conversion.
Task 11: PARKED — (Important, plan-mandated) acceso directo puntuaciones[self._clave] sin fallback; un
  KeyError escaparia en el bucle principal. DICTAMEN DEL CONTROLADOR: el codigo se queda como esta.
  Blindarlo con .get(clave, 0.0) convertiria un fallo ruidoso en uno silencioso, y para un detector de
  palabra clave "nunca despierta y no dice por que" es peor modo de fallo que una traza. La condicion
  ademas exige que openWakeWord cambie de comportamiento. Riesgo aceptado deliberadamente.
Task 11: minor (deferred): la construccion del modelo (carga ONNX de disco) no maneja errores; un fichero
  ausente o corrupto sale como la excepcion cruda de la libreria
Task 11: PENDIENTE MANUAL: calibrar el umbral del wake word con microfono real (Step 5), diferido
Task 12: review 1 — spec ✅ (superficie, import de TASA_MUESTREO, cancelacion en ambos niveles, RMS del
  trozo final, cero al terminar). 3 Important, todos plan-mandated:
  1. finally: al_rms(0.0) antes de stream.stop()/close() -> si el callback lanza, el stream se filtra.
     Relevante aqui: ese callback llama al cliente de la cara, que es un proceso que puede haberse caido.
  2. stream.start() fuera del try -> mismo patron de fuga ya corregido en captura.py
  3. los tests NO detectarian un error de escala del doble: el revisor sustituyo MAXIMO_INT16 por 16384.0
     y los cinco tests siguieron pasando, porque min(1.0,...) recorta y ninguna asercion fija un valor
     exacto. Un fallo de sobre-escala (boca saturada abierta) pasaria entero.
Task 12: adjudicado — se arreglan los tres ahora, porque la Tarea 13 modifica este mismo archivo.
Task 12: fix round 1/5 en curso (implementador a4629a7695014cde9 reanudado)
Task 12: fix round 1/5 (3 addressed, 0 open; commits 3280b76..bcf228f, 86/86 tests)
  El re-revisor trazo las 6 vias de salida de reproducir() (fin normal, cancelacion, iterador que lanza,
  al_rms que lanza a mitad, al_rms que lanza en el cero final, start() que lanza) y confirmo que el stream
  se cierra en todas y que la excepcion original nunca queda enmascarada.
  Test de escala: amplitud 16384 -> RMS exacto 0.5, por debajo del recorte. Demostrado que FALLA con la
  constante erronea (da 1.0 por recorte) y pasa con la correcta.
Task 12: complete (commits 0b21e5b..bcf228f, review clean)
Task 12: minor (deferred): el fallo del al_rms(0.0) terminal se traga con except Exception: pass sin log;
  si la cara esta caida el desarrollador no recibe ninguna senal
Task 12: minor (deferred): MUESTRAS_POR_TROZO=320 esta fijado a mano en vez de derivarse de TASA_MUESTREO
Task 12: minor (deferred): el troceado reinicia la ventana de 320 en cada chunk entrante; con chunks no
  alineados el ritmo de actualizacion del RMS sera irregular. Revisar cuando la Tarea 13 conecte el TTS real.
Task 13: complete (commits bcf228f..d97c00c, review clean, 93/93 tests)
  HALLAZGO IMPORTANTE DEL IMPLEMENTADOR: piper-tts 1.7.0 NO tiene synthesize_stream_raw, el metodo que
  asumia el plan. API real: voice.synthesize(texto) -> Iterable[AudioChunk] con chunk.audio_int16_bytes.
  El revisor lo verifico entrando en piper/voice.py:92-98 y confirmo que audio_int16_bytes devuelve
  tobytes(), es decir bytes reales -> el contrato Iterator[bytes] que necesitan las Tareas 12 y 17 se
  preserva. Los dobles de test imitan la API REAL, no la del plan.
  Tasa medida: 22050 Hz (no 16000) -> rama condicional del Paso 6 obligatoria, implementada con
  tasa: int = TASA_MUESTREO por defecto, asi que los llamadores de la Tarea 12 no cambian.
Task 13: minor (deferred): PiperVoice.load sin manejo de errores; un modelo ausente sale como excepcion
  cruda del runtime ONNX (defendible: fallar ruidosamente al arrancar)
Task 13: minor (deferred): _VozFalsa.load es classmethod y la real es staticmethod
Task 13: PENDIENTE MANUAL: escuchar scripts/probar_voz.py y juzgar inteligibilidad (Step 7), diferido
Task 14: review 1 — propiedad del cliente ✅ y forma del esquema ✅ (las dos que necesita la Tarea 15).
  2 Important:
  1. (plan-mandated) el contrato "nunca lanza" NO se cumple: la interpretacion de la respuesta (tabla WMO
     + interpolacion de campos) queda FUERA del try/except. Una respuesta 200 malformada lanza KeyError,
     TypeError, ValueError o AttributeError. Ademas el except de ejecutar() atrapa algunas por casualidad
     y devuelve el mensaje equivocado (culpa a las coordenadas), y deja escapar AttributeError.
     Critico porque el resto del proyecto NO tiene manejo de errores de herramientas: rompe la Tarea 17.
  2. hueco de tests que lo dejo pasar: ningun test con 200 + cuerpo malformado. Por eso la auto-revision
     del implementador afirmo "nunca lanza" siendo falso.
  + Minor incluido en la ronda: faltan codigos WMO 56,57,66,67,77,85,86 y el caso por defecto produce
    "cielo sin datos del cielo", que suena mal sintetizado en voz.
Task 14: fix round 1/5 en curso (implementador af2eca6b83e2dbc95 reanudado)
Task 14: fix round 1/5 (3 addressed, 0 open; commits a73f628..72ff797, 106/106 tests)
  El re-revisor rehizo la auditoria de fugas desde cero y confirmo que la interpretacion de la respuesta
  ya esta dentro del try, que la tupla de excepciones cubre TypeError y AttributeError, y que el mensaje
  de ejecutar() ya no culpa a las coordenadas cuando el fallo fue de la API.
Task 14: complete (commits d97c00c..72ff797, review clean)
Task 14: minor (deferred): weather_code con valor Infinity (json de Python lo acepta) lanzaria OverflowError,
  no cubierto por ninguna tupla. Inalcanzable con respuestas reales de Open-Meteo.
Task 14: minor (deferred): la tupla ampliada convierte tambien un error de programacion (typo, atributo
  inexistente) en la frase generica, sin log. Coste de depuracion inherente al contrato "nunca lanza".
  PARA TRIAJE EN LA REVISION FINAL: un log dentro del except recuperaria visibilidad sin romper el contrato.
Task 14: minor (deferred): el texto por defecto "cielo estado desconocido" sigue sin leerse con naturalidad
Task 15: complete (commits 72ff797..8e3402a, review clean, 126/126 tests)
  Las 3 correcciones de la auditoria implementadas y VERIFICADAS de forma independiente por el revisor
  contra el SDK instalado: errors.py:46 APIError(Exception), errors.py:319 UnknownApiResponseError(ValueError),
  _api_client.py:562-591 con reraise=True en tenacity, y comprobacion en vivo de que httpx.HTTPError no
  hereda de OSError. La tupla final es (APIError, httpx.HTTPError, ValueError).
  El revisor construyo su PROPIO control negativo aislado para la correccion 2: copio gemini.py, revirtio
  solo la colocacion del bloque, lo cargo con importlib y confirmo que escapa un pydantic.ValidationError.
Task 15: CONTRATO DE INTEGRACION PARA LA TAREA 17 — conversar() es un generador, asi que las excepciones
  solo afloran al ITERARLO, no al llamarlo. El orquestador debe envolver la iteracion, no la llamada.
  El codigo del plan lo hace bien (el for esta dentro del try de _responder), pero hay que confirmarlo.
Task 15: minor (deferred): types.Content/Part construidos fuera del try en dos sitios (linea del turno de
  usuario y en _recordar); sin modo de fallo realista, solo asimetria defensiva
Task 15: minor (deferred): los tests acceden a _historial (atributo privado) para verificar el recorte
Task 15: PENDIENTE MANUAL: Step 7 (probar_llm.py con clave real) y verificar que gemini-2.5-flash sigue
  siendo un modelo vigente con models.list()
Task 16: complete (commits 8e3402a..6f0542f, review clean, 140/140 tests)
  Las 2 correcciones de la auditoria implementadas. El revisor trazo las 8 vias de excepcion de transcribir()
  y confirmo que ninguna escapa sin traducirse a ErrorDeRed. La costura de inyeccion del cliente replica
  linea a linea la disciplina de propiedad ya establecida en herramientas.py.
Task 16: DECISION PENDIENTE PARA EL USUARIO: nova-2 sigue vigente, pero nova-3 ya soporta espanol
  monolingue con WER notablemente mejor. Cambio de una linea. Decidir cuando haya clave para comparar.
Task 16: minor (deferred): ningun test ejercita la rama propio=True (cliente creado internamente); solo
  se cubre la mitad "nunca cierra el inyectado"
Task 16: minor (deferred): el informe dice "no se hizo commit todavia" pero el commit existe; texto obsoleto
Task 16: PENDIENTE MANUAL: Step 6 (probar_stt.py con microfono y clave), diferido
Task 17: review 1 (opus) — spec ✅. Maquina de estados fiel, red de seguridad exactamente como se pidio,
  propagacion de KeyboardInterrupt trazada, los dos tests obligatorios ejercitan lo que dicen.
  El revisor verifico ademas que la red de seguridad no puede autodestruirse: el set_estado(REPOSO) del
  manejador llama a CaraCliente, que se traga OSError, asi que no puede lanzar dentro del except.
  1 Important + 3 Minor:
  1. (Important) sin backoff: el caso "microfono muerto" NO gira (leer_bloque tiene timeout de 1s y devuelve
     None), pero un colaborador que lance en cada bloque entregado (p.ej. Detector.procesar con ONNX malo
     en ARM) produce ~30 trazas/s. En una Pi desatendida eso llena la SD.
  2. (Minor, se arregla) la cola de audio no se vacia tras un ciclo fallido -> conserva la propia voz
     sintetizada del asistente y puede auto-despertarlo en el ciclo siguiente
  3. (Minor, se arregla) la asercion de que la cara vuelve a REPOSO es vacua: pasaria igual borrando la
     linea del manejador, porque ejecutar() ya pone REPOSO al arrancar y CaraFalsa colapsa duplicados
  4. (Minor, diferido) VadFalso fija hubo_voz en el constructor y su reiniciar() esta vacio, asi que no
     podria detectar un bug de orden; el revisor confirmo por inspeccion que el orden real es correcto
Task 17: fix round 1/5 en curso (implementador ab76d9922644c5b8d reanudado)
Task 17: fix round 1/5 (3 addressed, 0 open; commits 7e53623..657b190, 156/156 tests)
  Backoff exponencial con tope de 30s, contador que se reinicia via clausula else (solo en ciclo correcto),
  dedup por firma (tipo, str(exc)) con traza completa en la primera aparicion y aviso corto en repeticiones.
  El re-revisor comprobo especificamente que un error DISTINTO llegando durante una ventana de supresion
  SI se registra completo y reinicia el contador de dedup: no se traga.
  Vaciado de cola anadido al manejador. Asercion vacua convertida en real y demostrada fallando/pasando.
Task 17: complete (commits 6f0542f..657b190, review clean)
Task 17: minor (deferred): vaciar() se llama sin guarda dentro del except; hoy no puede lanzar (solo captura
  queue.Empty) pero si algun dia lo hiciera mataria el bucle que esta tarea existe para proteger
Task 17: minor (deferred): la firma (tipo, str(exc)) confunde dos bugs distintos con misma clase y mensaje
Task 18: complete (commits 657b190..6aedf6e, review clean, 157/157 tests)
  Las 3 correcciones de la auditoria aplicadas. El revisor auditó las 9 llamadas de constructor una por una
  contra las firmas reales bajo src/ (era el unico modo de detectar un fallo de primer arranque, porque este
  modulo no tiene tests) y todas coinciden. La comprobacion del modelo de wake word resulto ser MAS estricta
  que la de la propia libreria: openwakeword solo compara patrones de ruta, esta ademas verifica que el
  fichero exista en disco.
Task 18: minor (deferred): _wakeword_disponible depende de openwakeword.get_pretrained_model_paths, un helper
  no formalmente estable; si desaparece en una version futura, el AttributeError saldria como traza cruda,
  que es justo el fallo que la correccion 3 existia para evitar. Un try/except lo degradaria con gracia.
Task 18: minor (deferred): el mensaje de wake word siempre sugiere download_models(), consejo erroneo si el
  usuario apunta MODELO_WAKEWORD a un modelo propio entrenado
Task 18: minor (deferred): _wakeword_disponible es testeable y no tiene tests
Task 18: PENDIENTE MANUAL: Step 5, los 8 criterios de aceptacion del Hito 1, diferido al bloque final

=== LAS 18 TAREAS COMPLETAS. 157 tests. Pendiente: revision final de rama. ===

=== VEREDICTO FINAL: LISTO PARA FUSIONAR ===
165 tests. Los 3 bloqueantes de la revision final verificados de forma independiente por el re-revisor
(recalculo de la aritmetica y trazado del SDK instalado, no confianza en el informe del implementador).

PARA EL BLOQUE DE VERIFICACION MANUAL:
  - S4 + timeout: gemini-2.5-flash trae "thinking" activo por defecto. El timeout de 15s es de hueco de
    lectura (se reinicia con cada chunk), asi que acota el silencio, no la duracion total. Pero una fase
    de pensamiento que no emita bytes durante mas de 15s produciria MENSAJE_SIN_RED con la red perfecta.
    MEDIRLO con clave real antes de dar por bueno el comportamiento offline.
  - nova-2 vs nova-3 en Deepgram (nova-3 transcribe espanol mejor; cambio de una linea)
  - confirmar que gemini-2.5-flash sigue vigente con models.list()

MEJORA BARATA SUGERIDA POR EL RE-REVISOR (no bloqueante):
  test_cliente_gemini_configura_un_timeout_explicito compara el valor contra la propia constante, asi que
  pasaria igual con TIMEOUT_MS = 15 (15 ms, dispararia al instante). Aserta el valor en SEGUNDOS para que
  pueda fallar ante un error de unidad.

PARA EL HITO 2 (Raspberry Pi), documentado ya como comentarios en el codigo:
  - suavizado por frame en vez de por segundo (parametros.py, lipsync.py)
  - el lipsync ademas submuestrea: 69 mensajes RMS/s consumidos uno por frame; a 20 fps se pierden picos
  - al_rms se emite ANTES de escribir el audio, asi que la boca ADELANTA; eso enmascara parte del retraso
    actual y quedara al descubierto al corregir el suavizado
  - comentario "~20 ms" en lipsync.py: a 22050 Hz son 14.5 ms
  - los umbrales del VAD no estan expuestos en Config
