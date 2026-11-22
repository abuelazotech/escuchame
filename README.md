# Escúchame

![Escúchame](assets/escuchame-512.png)

Aplicación para Linux Mint Cinnamon que permite controlar el escritorio por voz y usar dictado, con indicador permanente en la bandeja del panel.

Repositorio: https://github.com/abuelazotech/escuchame

## Estados

- **Apagado**: no ejecuta comandos ni dictado.
- **Control activo**: escucha frases y ejecuta comandos configurados.
- **Dictado activo**: escribe el texto reconocido en la aplicación activa.

El cambio de estado se hace desde el icono del panel o con la tecla rápida configurable (por defecto `Super+Alt+V`).

## Indicador de panel

- Ubicación: bandeja del sistema del panel de Cinnamon (normalmente abajo a la derecha).
- Visible mientras la aplicación está en ejecución.
- Menú: Activar control, Activar dictado, Apagar, Configuración, Salir.

## Requisitos

- Linux Mint Cinnamon (X11)
- Python 3, GTK3, XApp
- `vosk`, `parec`/PulseAudio, `xdotool`
- Modelo Vosk en `~/.local/share/control-voz/modelos/...` o ruta configurada

## Uso

```bash
control-voz
```

## Configuración

La GUI permite:
- Añadir/editar comandos de voz (frase, acción, valor).
- Añadir palabras/frases al diccionario de reconocimiento.
- Cambiar modelo Vosk, hotkey y micrófono.

Archivo de configuración: `~/.config/control-voz/config.json`.

## Empaquetado

```bash
./build.sh
```

## Nota

El reconocimiento offline depende del modelo Vosk y del micrófono. El dictado se escribe en la ventana activa; evita usar dictado en campos sensibles.