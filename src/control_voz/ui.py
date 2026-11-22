from __future__ import annotations

import shlex

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("XApp", "1.0")
try:
    gi.require_version("Keybinder", "3.0")
    from gi.repository import Keybinder  # type: ignore
except Exception:
    Keybinder = None

from gi.repository import Gio, GLib, Gtk, XApp  # type: ignore

from .config import APP_NAME, DEFAULT_MODEL, ensure_config, save_config
from .corrections import load_corrections, normalize_text, save_corrections
from .engine import EngineEvent, VoiceEngine


STATE_LABELS = {
    "off": "Apagado",
    "command": "Control activo",
    "dictation": "Dictado activo",
}

STATE_ICONS = {
    "off": "control-voz-off",
    "command": "control-voz-command",
    "dictation": "control-voz-dictation",
}


class ListeningPopup(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME, type=Gtk.WindowType.POPUP)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(260, 80)
        self.set_opacity(0.94)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, border_width=16)
        self.label = Gtk.Label()
        box.pack_start(self.label, True, True, 0)
        self.add(box)
        self._timeout = None

    def show_message(self, text: str, seconds: int) -> None:
        self.label.set_markup(f"<b><big>{text}</big></b>")
        self.show_all()
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None
        self._timeout = GLib.timeout_add_seconds(seconds, self._hide)

    def _hide(self) -> bool:
        self.hide()
        self._timeout = None
        return False


class ControlVozApp:
    def __init__(self):
        self.config = ensure_config()
        start_off = bool(self.config.get("start_off", True))
        if start_off:
            self.config["state"] = "off"
        self.engine = VoiceEngine(self.config, self._on_engine_event)
        self.popup = ListeningPopup()
        self.indicator = XApp.StatusIcon()
        self.indicator.set_name("control-voz")
        self.indicator.set_tooltip_text(APP_NAME)
        self._build_menu()
        self._apply_state(self.config.get("state", "off"), save=start_off)
        self.engine.start()
        self._bind_hotkey()
        GLib.timeout_add(500, self._refresh_tooltip)

    def _build_menu(self):
        menu = Gtk.Menu()

        self.item_status = Gtk.MenuItem(label=f"Estado: {STATE_LABELS[self.config.get('state','off')]}")
        self.item_status.set_sensitive(False)
        menu.append(self.item_status)

        menu.append(Gtk.SeparatorMenuItem())
        self.item_command = self._item("Activar control", lambda *_: self.set_state("command"))
        self.item_dictation = self._item("Activar dictado", lambda *_: self.set_state("dictation"))
        self.item_off = self._item("Apagar", lambda *_: self.set_state("off"))
        menu.append(self.item_command)
        menu.append(self.item_dictation)
        menu.append(self.item_off)
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(self._item("Configuración...", lambda *_: self.open_settings()))
        menu.append(self._item("Salir", lambda *_: self.quit()))
        menu.show_all()
        self.indicator.set_secondary_menu(menu)
        self.indicator.set_primary_menu(menu)

    def _item(self, label, cb):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", cb)
        return item

    def _bind_hotkey(self):
        if not Keybinder:
            return
        try:
            Keybinder.init()
            hotkey = self.config.get("hotkey", "<Super><Alt>v")
            Keybinder.bind(hotkey, lambda *_: GLib.idle_add(self.toggle_state))
        except Exception:
            pass

    def toggle_state(self):
        order = ["off", "command", "dictation"]
        current = self.config.get("state", "off")
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else "command"
        self.set_state(nxt)
        return False

    def set_state(self, state: str):
        self._apply_state(state, save=True)
        self.engine.set_state(state)

    def _apply_state(self, state: str, save: bool):
        self.config["state"] = state
        self.item_status.set_label(f"Estado: {STATE_LABELS.get(state, state)}")
        icon = STATE_ICONS.get(state, STATE_ICONS["off"])
        self.indicator.set_icon_name(icon)
        self.indicator.set_tooltip_text(f"{APP_NAME}: {STATE_LABELS.get(state, state)}")
        if hasattr(self, "item_command"):
            self.item_command.set_sensitive(state != "command")
            self.item_dictation.set_sensitive(state != "dictation")
            self.item_off.set_sensitive(state != "off")
        if save:
            save_config(self.config)

    def _on_engine_event(self, event: EngineEvent):
        if event.kind == "state":
            GLib.idle_add(self._apply_state, event.text, True)
        elif event.kind == "error":
            GLib.idle_add(self.indicator.set_tooltip_text, f"{APP_NAME}: {event.text}")
        elif event.kind == "wake":
            GLib.idle_add(self.popup.show_message, "Escuchando...", 3)
        elif event.kind == "sleep":
            GLib.idle_add(self.popup.show_message, "En silencio...", 2)

    def _refresh_tooltip(self):
        state = self.config.get("state", "off")
        self.indicator.set_tooltip_text(f"{APP_NAME}: {STATE_LABELS.get(state, state)}")
        return True

    def open_settings(self):
        win = SettingsWindow(self.config, self._on_config_changed)
        win.show_all()

    def _on_config_changed(self, cfg):
        self.config = cfg
        save_config(self.config)
        self.engine.config = self.config
        self.engine.stop()
        self.engine.start()
        self.engine.set_state(self.config.get("state", "off"))

    def quit(self):
        try:
            self.popup.hide()
            self.engine.stop()
        finally:
            Gtk.main_quit()


class SettingsWindow(Gtk.Window):
    def __init__(self, config: dict, on_save):
        super().__init__(title=f"{APP_NAME} - Configuración")
        self.set_default_size(760, 520)
        self.config = json_clone(config)
        self.on_save = on_save

        nb = Gtk.Notebook()
        self.add(nb)
        nb.append_page(self._help_commands_page(), Gtk.Label(label="Ayuda: comandos"))
        nb.append_page(self._help_dictionary_page(), Gtk.Label(label="Ayuda: diccionario"))
        nb.append_page(self._commands_page(), Gtk.Label(label="Comandos"))
        nb.append_page(self._dict_page(), Gtk.Label(label="Diccionario"))
        nb.append_page(self._corrections_page(), Gtk.Label(label="Correcciones"))
        nb.append_page(self._general_page(), Gtk.Label(label="General"))

    def _help_text_page(self, text: str):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=14)
        label = Gtk.Label()
        label.set_markup(text)
        label.set_line_wrap(True)
        label.set_xalign(0)
        label.set_yalign(0)
        label.set_selectable(True)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(label)
        box.pack_start(sw, True, True, 0)
        return box

    def _help_commands_page(self):
        return self._help_text_page("""<b>Ayuda: comandos</b>

<b>1. Añadir un comando de voz</b>
1. Haz clic en el icono del panel y elige <b>Configuración...</b>.
2. Abre la pestaña <b>Comandos</b> y pulsa <b>Añadir</b>.
3. En <b>Frase</b> escribe lo que vas a decir, por ejemplo: <i>abrir OBS</i>.
4. En <b>Acción</b> deja <i>run</i> para abrir programas o ejecutar comandos.
5. En <b>Valor</b> escribe el comando, por ejemplo: <i>obs</i>.
6. Deja marcado <b>Activo</b> y pulsa <b>Guardar</b>.
7. Para cambiar un comando, selecciónalo y pulsa <b>Editar</b> (o haz doble clic).
8. Activa <b>Control activo</b> desde el icono y di la frase.

<b>2. Crear un comando sin conocer el comando del programa</b>
1. En la pestaña <b>Comandos</b>, mira el recuadro <b>Asistente: añadir una aplicación</b>.
2. Escribe el nombre de la aplicación, por ejemplo <i>OBS</i>, y elige una sugerencia.
   También puedes pulsar <b>Elegir...</b> para ver todas las aplicaciones instaladas.
3. El campo <b>Comando generado</b> se rellena solo, y puedes cambiarlo si quieres.
4. En <b>Frase para activarla</b> escribe lo que dirás, por ejemplo <i>abrir OBS</i>.
5. Pulsa <b>Añadir a la lista</b> y, al terminar, <b>Guardar</b>.

<b>3. Activar, desactivar y dictar</b>
1. Escúchame arranca siempre desactivado (gris).
2. Di <i>escúchame</i>: se activa el modo comando y aparece «Escuchando...» durante 3 segundos.
3. Di <i>ensordece</i> para volver a apagarlo, tanto desde comando como desde dictado; aparece «En silencio...».
4. Desde el modo comando di <i>modo dictado</i> para escribir lo que digas, y <i>modo comando</i> para volver.
5. También puedes usar el icono del panel, la tecla <b>Super+Alt+V</b> o la frase <i>apagar control</i>.
6. En <b>General</b> puedes desactivar el escucha-permanente y el arranque desactivado.

<b>Consejos</b>
- Usa frases cortas y diferentes entre sí.
- Escribe las palabras como las pronuncias, en minúsculas.
- Si un comando no salta, revisa la frase en la pestaña <b>Comandos</b> o corrígela desde <b>Ayuda: diccionario</b>.
- Si cuesta entenderte, revisa el modelo Vosk y el micrófono en <b>General</b>.
- Los cambios solo se aplican después de pulsar <b>Guardar</b>.
""")

    def _help_dictionary_page(self):
        return self._help_text_page("""<b>Ayuda: diccionario y correcciones</b>

<b>1. Añadir una palabra al diccionario</b>
1. Abre la pestaña <b>Diccionario</b> y pulsa <b>Añadir</b>.
2. Escribe la palabra o frase tal como suena, por ejemplo <i>Diario del Abuelazo</i>.
3. Pulsa <b>Guardar</b>. Así el reconocimiento la entenderá mejor.

<b>2. Corregir una frase que Vosk entiende mal</b>
1. Activa <b>Control activo</b> desde el icono del panel (o di <i>modo comando</i>).
2. Mira <i>~/.config/control-voz/no-reconocido.txt</i>: ahí se acumulan las frases que no encajaron con ningún comando.
3. Di <i>corregir</i>, la frase tal como la oyó Vosk, la palabra <i>es</i> y al final la frase correcta.
   Ejemplo: si entiende <i>abrir cadenlai</i> y tú quieres <i>abrir kdenlive</i>, di:
   <i>corregir abrir cadenlai es abrir kdenlive</i>.
4. También funcionan <i>corrige abrir cadenlai con abrir kdenlive</i> y <i>corrige abrir cadenlai por abrir kdenlive</i>.
5. La corrección se guarda en <i>~/.config/control-voz/correcciones.txt</i> y se aplica enseguida: no hace falta reiniciar ni volver a pulsar <b>Guardar</b>.
6. Di otra vez la frase original: ahora debe reconocerse como la corregida.
7. Si te equivocaste, di otra corrección con el mismo texto mal; la nueva reemplaza a la anterior.
8. También puedes abrir <b>Configuración → Correcciones</b>, escribir las dos frases y pulsar
   <b>Añadir corrección</b> y luego <b>Guardar correcciones</b>. Reinicia Escúchame para aplicarlas.
9. Otra opción es editar el archivo a mano, una corrección por línea, con el formato
   <i>lo que oyó => lo correcto</i>. Esos cambios se cargan al reiniciar Escúchame.

<b>3. Corregir el dictado</b>
- Las correcciones también se aplican a lo que se escribe al dictar.
- Solo se cambia la parte corregida: se conservan mayúsculas, tildes y signos del resto del texto.
- La palabra corregida se escribe tal como la dijiste en el paso 3.

<b>Consejos</b>
- Corrige lo mínimo, por ejemplo <i>cadenlai</i>, en vez de frases largas.
- Para nombres de aplicaciones, a veces basta con añadir la frase mal dicha en la pestaña <b>Comandos</b>.
- «escúchame» y «ensordece» se reconocen también al dictar y no se escriben en el texto.
- Si cuesta entenderte, revisa el modelo Vosk y el micrófono en <b>General</b>.
""")

    def _commands_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=10)

        frame = Gtk.Frame(label="Asistente: añadir una aplicación")
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, border_width=8)
        frame.add(grid)
        box.pack_start(frame, False, False, 0)

        self.app_store = Gtk.ListStore(str)
        self.app_commands = {}
        for name, cmd in self._system_apps():
            self.app_store.append([name])
            self.app_commands[name.lower()] = cmd

        completion = Gtk.EntryCompletion()
        completion.set_model(self.app_store)
        completion.set_text_column(0)
        completion.connect("match-selected", self._app_selected)

        grid.attach(Gtk.Label(label="Nombre de la aplicación:", xalign=0), 0, 0, 1, 1)
        self.app_entry = Gtk.Entry()
        self.app_entry.set_hexpand(True)
        self.app_entry.set_completion(completion)
        grid.attach(self.app_entry, 1, 0, 1, 1)
        pick = Gtk.Button(label="Elegir...")
        pick.connect("clicked", self._pick_app)
        grid.attach(pick, 2, 0, 1, 1)

        grid.attach(Gtk.Label(label="Comando generado:", xalign=0), 0, 1, 1, 1)
        self.app_command_entry = Gtk.Entry()
        self.app_command_entry.set_hexpand(True)
        grid.attach(self.app_command_entry, 1, 1, 2, 1)

        grid.attach(Gtk.Label(label="Frase para activarla:", xalign=0), 0, 2, 1, 1)
        self.app_phrase_entry = Gtk.Entry()
        self.app_phrase_entry.set_hexpand(True)
        grid.attach(self.app_phrase_entry, 1, 2, 2, 1)

        add_app = Gtk.Button(label="Añadir a la lista")
        add_app.connect("clicked", self._add_app_command)
        grid.attach(add_app, 1, 3, 1, 1)
        grid.attach(Gtk.Label(label="Después pulsa Guardar para aplicar los cambios.", xalign=0), 2, 3, 1, 1)

        self.cmd_store = Gtk.ListStore(str, str, str, bool)
        for c in self.config.get("commands", []):
            self.cmd_store.append([c.get("phrase", ""), c.get("action", "run"), c.get("value", ""), bool(c.get("enabled", True))])

        self.cmd_tree = tree = Gtk.TreeView(model=self.cmd_store)
        for i, title in enumerate(["Frase", "Acción", "Valor", "Activo"]):
            if i == 3:
                rend = Gtk.CellRendererToggle()
                rend.connect("toggled", self._toggle_cmd, i)
                col = Gtk.TreeViewColumn(title, rend, active=i)
            else:
                rend = Gtk.CellRendererText(editable=True)
                rend.connect("edited", self._edited_cmd, i)
                col = Gtk.TreeViewColumn(title, rend, text=i)
            tree.append_column(col)
        tree.connect("row-activated", self._edit_cmd_from_activation)
        sw = Gtk.ScrolledWindow()
        sw.add(tree)
        box.pack_start(sw, True, True, 0)

        btns = Gtk.Box(spacing=6)
        for label, cb in [
            ("Añadir", self._add_cmd),
            ("Editar", self._edit_cmd),
            ("Eliminar", lambda *_: self._del_row(tree, self.cmd_store)),
            ("Guardar", self._save),
        ]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            btns.pack_start(b, False, False, 0)
        box.pack_start(btns, False, False, 0)
        return box

    def _dict_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=10)
        self.dict_store = Gtk.ListStore(str)
        for w in self.config.get("dictionary", []):
            self.dict_store.append([w])
        tree = Gtk.TreeView(model=self.dict_store)
        rend = Gtk.CellRendererText(editable=True)
        rend.connect("edited", self._edited_dict)
        tree.append_column(Gtk.TreeViewColumn("Palabra/frase", rend, text=0))
        sw = Gtk.ScrolledWindow(); sw.add(tree)
        box.pack_start(sw, True, True, 0)
        btns = Gtk.Box(spacing=6)
        for label, cb in [("Añadir", self._add_dict), ("Eliminar", lambda *_: self._del_row(tree, self.dict_store)), ("Guardar", self._save)]:
            b = Gtk.Button(label=label); b.connect("clicked", cb); btns.pack_start(b, False, False, 0)
        box.pack_start(btns, False, False, 0)
        return box

    def _corrections_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=10)
        self.correction_store = Gtk.ListStore(str, str)
        for wrong, right in sorted(load_corrections().items()):
            self.correction_store.append([wrong, right])
        tree = Gtk.TreeView(model=self.correction_store)
        for title, column in (("Lo que oyó", 0), ("Frase correcta", 1)):
            rend = Gtk.CellRendererText(editable=True)
            rend.connect("edited", self._edited_correction, column)
            tree.append_column(Gtk.TreeViewColumn(title, rend, text=column))
        sw = Gtk.ScrolledWindow(); sw.add(tree)
        box.pack_start(sw, True, True, 0)

        form = Gtk.Grid(column_spacing=6, row_spacing=6)
        form.attach(Gtk.Label(label="Frase que oyó Vosk", xalign=0), 0, 0, 1, 1)
        self.correction_wrong = Gtk.Entry()
        form.attach(self.correction_wrong, 1, 0, 1, 1)
        form.attach(Gtk.Label(label="Frase correcta", xalign=0), 0, 1, 1, 1)
        self.correction_right = Gtk.Entry()
        form.attach(self.correction_right, 1, 1, 1, 1)
        box.pack_start(form, False, False, 0)

        btns = Gtk.Box(spacing=6)
        for label, cb in [
            ("Añadir corrección", self._add_correction),
            ("Eliminar", lambda *_: self._del_row(tree, self.correction_store)),
            ("Guardar correcciones", self._persist_corrections),
        ]:
            b = Gtk.Button(label=label); b.connect("clicked", cb); btns.pack_start(b, False, False, 0)
        box.pack_start(btns, False, False, 0)

        info = Gtk.Label(
            label="También puedes decir «corregir lo que oyó es la frase correcta». "
                  "Los cambios desde esta pestaña se aplican al reiniciar Escúchame.",
            xalign=0,
        )
        info.set_line_wrap(True)
        box.pack_start(info, False, False, 0)
        return box

    def _add_correction(self, *_):
        wrong = self.correction_wrong.get_text().strip()
        right = self.correction_right.get_text().strip()
        if not wrong or not right:
            return
        key = normalize_text(wrong)
        for row in self.correction_store:
            if normalize_text(row[0]) == key:
                row[1] = right
                break
        else:
            self.correction_store.append([wrong, right])
        self.correction_wrong.set_text("")
        self.correction_right.set_text("")

    def _edited_correction(self, _renderer, path, new_text, column):
        row = self.correction_store.get_iter(path)
        self.correction_store.set_value(row, column, new_text)

    def _persist_corrections(self, *_):
        corrections = {}
        for row in self.correction_store:
            wrong = str(row[0]).strip()
            right = str(row[1]).strip()
            if wrong and right:
                corrections[normalize_text(wrong)] = right
        save_corrections(corrections)

    def _general_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=10)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        box.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Modelo Vosk", xalign=0), 0, 0, 1, 1)
        self.model_entry = Gtk.Entry(text=self.config.get("model_path", ""))
        self.model_entry.set_hexpand(True)
        model_box = Gtk.Box(spacing=4)
        model_box.pack_start(self.model_entry, True, True, 0)
        btn_model = Gtk.Button(label="Buscar...")
        btn_model.connect("clicked", self._choose_model)
        model_box.pack_start(btn_model, False, False, 0)
        btn_model_help = Gtk.Button(label="Ayuda modelo")
        btn_model_help.connect("clicked", self._model_help)
        model_box.pack_start(btn_model_help, False, False, 0)
        grid.attach(model_box, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Hotkey", xalign=0), 0, 1, 1, 1)
        self.hotkey_entry = Gtk.Entry(text=self.config.get("hotkey", ""))
        grid.attach(self.hotkey_entry, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Micrófono (source Pulse)", xalign=0), 0, 2, 1, 1)
        self.mic_entry = Gtk.Entry(text=self.config.get("microphone_source", ""))
        self.mic_entry.set_hexpand(True)
        mic_box = Gtk.Box(spacing=4)
        mic_box.pack_start(self.mic_entry, True, True, 0)
        btn_mic = Gtk.Button(label="Detectar")
        btn_mic.connect("clicked", self._detect_mic)
        mic_box.pack_start(btn_mic, False, False, 0)
        grid.attach(mic_box, 1, 2, 1, 1)

        self.notify_check = Gtk.CheckButton(label="Mostrar notificaciones")
        self.notify_check.set_active(bool(self.config.get("show_notifications", True)))
        box.pack_start(self.notify_check, False, False, 0)

        self.autostart_check = Gtk.CheckButton(label="Iniciar con la sesión")
        self.autostart_check.set_active(bool(self.config.get("autostart", False)))
        box.pack_start(self.autostart_check, False, False, 0)

        self.wake_check = Gtk.CheckButton(label="Escuchar siempre «escúchame» / «ensordece»")
        self.wake_check.set_active(bool(self.config.get("wake_word_enabled", True)))
        box.pack_start(self.wake_check, False, False, 0)

        self.start_off_check = Gtk.CheckButton(label="Iniciar siempre desactivado")
        self.start_off_check.set_active(bool(self.config.get("start_off", True)))
        box.pack_start(self.start_off_check, False, False, 0)

        save = Gtk.Button(label="Guardar")
        save.connect("clicked", self._save)
        box.pack_start(save, False, False, 0)

        info = Gtk.Label(
            label="Estados: Apagado (gris), Control activo (verde), Dictado activo (ámbar). "
                  "«escúchame» activa el control y «ensordece» lo desactiva; el despertar mantiene el micrófono activo.",
            xalign=0,
        )
        info.set_line_wrap(True)
        box.pack_end(info, False, False, 0)
        return box

    def _edited_cmd(self, renderer, path, text, col):
        self.cmd_store[path][col] = text.strip()

    def _toggle_cmd(self, renderer, path, col):
        self.cmd_store[path][col] = not self.cmd_store[path][col]

    def _edited_dict(self, renderer, path, text):
        self.dict_store[path][0] = text.strip()

    def _add_cmd(self, *_):
        self.cmd_store.append(["nueva frase", "run", "comando", True])

    def _edit_cmd_from_activation(self, tree, path, column):
        tree.get_selection().select_path(path)
        self._edit_cmd()

    def _edit_cmd(self, *_):
        model, itr = self.cmd_tree.get_selection().get_selected()
        if not itr:
            d = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Selecciona un comando",
            )
            d.format_secondary_text("Elige una fila de la lista y pulsa Editar. También puedes hacer doble clic.")
            d.run()
            d.destroy()
            return

        phrase, action, value, enabled = (self.cmd_store[itr][i] for i in range(4))
        dialog = Gtk.Dialog(title="Editar comando", transient_for=self, flags=0)
        dialog.set_default_size(480, 240)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, border_width=12)
        dialog.get_content_area().add(grid)

        grid.attach(Gtk.Label(label="Frase:", xalign=0), 0, 0, 1, 1)
        phrase_entry = Gtk.Entry(text=phrase)
        phrase_entry.set_hexpand(True)
        grid.attach(phrase_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Acción:", xalign=0), 0, 1, 1, 1)
        action_combo = Gtk.ComboBoxText.new_with_entry()
        for option in ("run", "key", "close_class", "mode"):
            action_combo.append_text(option)
        action_combo.get_child().set_text(action)
        grid.attach(action_combo, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Valor:", xalign=0), 0, 2, 1, 1)
        value_entry = Gtk.Entry(text=value)
        value_entry.set_hexpand(True)
        grid.attach(value_entry, 1, 2, 1, 1)

        enabled_check = Gtk.CheckButton(label="Activo")
        enabled_check.set_active(bool(enabled))
        grid.attach(enabled_check, 1, 3, 1, 1)

        dialog.show_all()
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            new_action = action_combo.get_active_text() or action_combo.get_child().get_text()
            self.cmd_store[itr] = [
                phrase_entry.get_text().strip(),
                (new_action or "run").strip(),
                value_entry.get_text().strip(),
                enabled_check.get_active(),
            ]
        dialog.destroy()

    @staticmethod
    def _app_command(info):
        cmd = ""
        try:
            cmd = info.get_commandline() or ""
        except Exception:
            pass
        if not cmd:
            try:
                executable = info.get_executable() or ""
            except Exception:
                executable = ""
            cmd = shlex.quote(executable) if executable else ""
        for code in ("%f", "%F", "%u", "%U", "%i", "%c", "%k"):
            cmd = cmd.replace(code, "")
        return " ".join(cmd.split()).strip()

    def _system_apps(self):
        apps = {}
        try:
            infos = Gio.AppInfo.get_all()
        except Exception:
            return []
        for info in infos:
            try:
                if not info.should_show():
                    continue
                name = (info.get_name() or "").strip()
                cmd = self._app_command(info)
                if name and cmd:
                    apps.setdefault(name.lower(), (name, cmd))
            except Exception:
                continue
        return sorted(apps.values(), key=lambda item: item[0].lower())

    def _app_selected(self, completion, model, itr):
        name = model[itr][0]
        self.app_entry.set_text(name)
        self.app_command_entry.set_text(self.app_commands.get(name.lower(), ""))
        if not self.app_phrase_entry.get_text().strip():
            self.app_phrase_entry.set_text("abrir " + name.lower())
        return True

    def _pick_app(self, *_):
        apps = self._system_apps()
        dialog = Gtk.Dialog(title="Aplicaciones instaladas", transient_for=self, flags=0)
        dialog.set_default_size(560, 400)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        search = Gtk.Entry()
        search.set_placeholder_text("Buscar aplicación...")
        store = Gtk.ListStore(str, str)
        tree = Gtk.TreeView(model=store)
        tree.append_column(Gtk.TreeViewColumn("Aplicación", Gtk.CellRendererText(), text=0))
        tree.append_column(Gtk.TreeViewColumn("Comando", Gtk.CellRendererText(), text=1))
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(280)
        sw.add(tree)
        content.pack_start(search, False, False, 0)
        content.pack_start(sw, True, True, 0)

        def repopulate(*_):
            term = search.get_text().strip().lower()
            store.clear()
            for name, cmd in apps:
                if not term or term in name.lower() or term in cmd.lower():
                    store.append([name, cmd])

        search.connect("changed", repopulate)
        repopulate()
        dialog.show_all()
        resp = dialog.run()
        model, itr = tree.get_selection().get_selected()
        if resp == Gtk.ResponseType.OK and itr:
            name = model[itr][0]
            self.app_entry.set_text(name)
            self.app_command_entry.set_text(model[itr][1])
            if not self.app_phrase_entry.get_text().strip():
                self.app_phrase_entry.set_text("abrir " + name.lower())
        dialog.destroy()

    def _add_app_command(self, *_):
        cmd = self.app_command_entry.get_text().strip()
        phrase = self.app_phrase_entry.get_text().strip()
        if not cmd or not phrase:
            d = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Faltan datos",
            )
            d.format_secondary_text("Elige una aplicación y escribe la frase que quieres decir para activarla.")
            d.run()
            d.destroy()
            return
        self.cmd_store.append([phrase, "run", cmd, True])
        self.app_entry.set_text("")
        self.app_command_entry.set_text("")
        self.app_phrase_entry.set_text("")

    def _add_dict(self, *_):
        self.dict_store.append(["nueva palabra"])

    def _del_row(self, tree, store):
        model, itr = tree.get_selection().get_selected()
        if itr:
            store.remove(itr)

    def _choose_model(self, *_):
        dialog = Gtk.FileChooserDialog(title="Seleccionar carpeta del modelo Vosk", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK and dialog.get_filename():
            self.model_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _model_help(self, *_):
        from pathlib import Path
        model_dir = str(Path(self.config.get("model_path", DEFAULT_MODEL)).parent)
        msg = (
            "Control por Voz usa modelos Vosk sin conexión.\n\n"
            "Descarga un modelo en español desde:\n"
            "https://alphacephei.com/vosk/models\n\n"
            f"Descomprímelo, por ejemplo, en:\n{model_dir}\n\n"
            "Después pulsa 'Buscar...' y elige la carpeta que contiene los archivos del modelo.\n"
            "El modelo grande reconoce mejor; el pequeño carga más rápido."
        )
        d = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="Modelo Vosk")
        d.format_secondary_text(msg)
        d.run(); d.destroy()

    def _detect_mic(self, *_):
        try:
            from .audio import default_source, list_sources
            sources = list_sources()
            current = self.mic_entry.get_text().strip() or default_source()
            if not sources:
                self.mic_entry.set_text(current)
                return
            dialog = Gtk.Dialog(title="Seleccionar micrófono", transient_for=self, flags=0)
            dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
            box = dialog.get_content_area()
            combo = Gtk.ComboBoxText()
            for name, label in sources:
                combo.append(name, label)
            if current:
                combo.set_active_id(current)
            if combo.get_active_id() is None:
                combo.set_active(0)
            box.add(combo)
            dialog.show_all()
            resp = dialog.run()
            if resp == Gtk.ResponseType.OK and combo.get_active_id():
                self.mic_entry.set_text(combo.get_active_id())
            dialog.destroy()
        except Exception:
            pass

    def _save(self, *_):
        cmds = []
        for row in self.cmd_store:
            phrase, action, value, enabled = row
            if str(phrase).strip() and str(value).strip():
                cmds.append({"phrase": str(phrase).strip(), "action": str(action).strip() or "run", "value": str(value).strip(), "enabled": bool(enabled)})
        words = []
        seen = set()
        for row in self.dict_store:
            w = str(row[0]).strip()
            k = w.lower()
            if w and k not in seen:
                seen.add(k); words.append(w)
        self.config["commands"] = cmds or self.config.get("commands", [])
        self.config["dictionary"] = words or self.config.get("dictionary", [])
        self.config["model_path"] = self.model_entry.get_text().strip()
        self.config["hotkey"] = self.hotkey_entry.get_text().strip() or self.config.get("hotkey")
        self.config["microphone_source"] = self.mic_entry.get_text().strip()
        self.config["show_notifications"] = self.notify_check.get_active()
        self.config["autostart"] = self.autostart_check.get_active()
        self.config["wake_word_enabled"] = self.wake_check.get_active()
        self.config["start_off"] = self.start_off_check.get_active()
        self._persist_corrections()
        self._apply_autostart(self.config["autostart"])
        self.on_save(self.config)
        self.destroy()

    def _apply_autostart(self, enabled: bool):
        from pathlib import Path
        autostart = Path.home() / ".config" / "autostart" / "control-voz.desktop"
        autostart.parent.mkdir(parents=True, exist_ok=True)
        if enabled:
            if autostart.exists():
                return
            src = Path("/usr/share/applications/control-voz.desktop")
            if src.exists():
                autostart.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                autostart.write_text(
                    "[Desktop Entry]\nType=Application\nName=Control por Voz\nExec=control-voz\nIcon=control-voz\nX-GNOME-Autostart-enabled=true\n",
                    encoding="utf-8",
                )
        elif autostart.exists():
            autostart.unlink()


def json_clone(obj):
    import json as _json
    return _json.loads(_json.dumps(obj))
