from unittest.mock import Mock, patch

from auto_prizma.automation.moodle.client import MoodleClient


def test_adds_resource_before_following_moodle_block_in_active_section():
    events = []

    class Locator:
        count_value = 1

        @property
        def first(self):
            return self

        def count(self):
            return self.count_value

        def nth(self, _index):
            return self

        def wait_for(self, **options):
            events.append(("wait", options))

        def is_visible(self):
            return True

        def scroll_into_view_if_needed(self):
            events.append(("scroll",))

        def evaluate(self, script):
            events.append(("click", script))

    destination = Locator()
    add = Locator()

    class Page:
        def get_by_text(self, text, exact=False):
            assert text == "Recurso educativo audiovisual"
            assert exact is True
            return destination

        def locator(self, selector):
            assert selector == (
                'button[data-action="open-chooser"][data-sectionid="81"]'
                '[aria-label*="Recurso educativo audiovisual"]'
            )
            return add

    client = MoodleClient.__new__(MoodleClient)
    client.page = Page()
    client.current_week = "Semana 1"
    client.current_section_id = "81"
    client.unavailable_destination_blocks = {}

    client.begin_add_resource("digital")

    assert events[-2][0] == "scroll"
    assert events[-1] == ("click", "element => element.click()")


def test_save_marks_pending_then_waits_and_verifies_like_original_flow():
    events = []

    class Locator:
        def __init__(self, present=True):
            self.present = present
            self.first = self

        def count(self):
            return int(self.present)

        def is_checked(self):
            return False

        def wait_for(self, **options):
            events.append(("save-wait", options))

        def click(self, **options):
            events.append(("save-click", options))

    class Page:
        url = "https://prizma.americana.edu.co/course/modedit.php"

        def locator(self, selector):
            if selector.startswith("input[name="):
                return Locator(False)
            return Locator()

        def get_by_role(self, role, name=None):
            if name == "Guardar cambios y regresar al curso":
                return Locator()
            return Locator(False)

        def evaluate(self, script):
            events.append(("scroll-bottom", script))

        def wait_for_timeout(self, milliseconds):
            events.append(("pause", milliseconds))

        def wait_for_url(self, url, **options):
            events.append(("return-to-course", options))
            self.url = "https://prizma.americana.edu.co/course/view.php?id=1"

    client = MoodleClient.__new__(MoodleClient)
    client.page = Page()
    client._verify_published = lambda title, module, count: events.append(("verify", title, module, count)) or "verified-h5p-1"
    result = client._save_and_verify(
        "Infografía de ejemplo",
        "h5p",
        0,
        on_before_save=lambda: events.append(("mark-pending",)),
    )

    assert result == "verified-h5p-1"
    assert events.index(("mark-pending",)) < next(i for i, event in enumerate(events) if event[0] == "save-click")
    assert ("pause", 1000) in events
    assert ("pause", 5000) in events
    assert events[-1] == ("verify", "Infografía de ejemplo", "h5p", 0)


def test_clicks_the_visible_upload_tab_and_waits_for_the_h5p_file_prompt():
    events = []

    class Locator:
        def __init__(self, name):
            self.first = self
            self.name = name

        def wait_for(self, **options):
            events.append((self.name, options))

    class Editor:
        def locator(self, selector):
            assert selector == "text=Create Content"
            return Locator("wait-create-content")

        def evaluate(self, script):
            # Como MOODLE: clic en la pestaña "Upload"; el radio oculto solo como respaldo.
            assert "textContent.trim() === 'Upload'" in script
            assert script.index("textContent.trim() === 'Upload'") < script.index('input[value="upload"]')
            events.append(("click-upload-tab",))

        def get_by_text(self, text):
            assert "Upload an H5P file" in str(text)
            return Locator("wait-prompt")

    client = MoodleClient.__new__(MoodleClient)
    client.page = object()
    client._select_h5p_upload_mode(Editor())

    assert events == [
        ("wait-create-content", {"state": "visible", "timeout": 15_000}),
        ("click-upload-tab",),
        ("wait-prompt", {"state": "visible", "timeout": 15_000}),
    ]


def test_launch_keeps_the_original_visible_moodle_browser_settings(tmp_path):
    page = Mock()
    page.evaluate.return_value = {"authenticated": True}
    context = Mock()
    context.pages = [page]
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context

    with patch("auto_prizma.automation.moodle.client.sync_playwright") as start:
        start.return_value.start.return_value = playwright
        with patch.object(MoodleClient, "ensure_edit_mode") as ensure_edit:
            client = MoodleClient.launch(
                "https://prizma.americana.edu.co/course/view.php?id=42",
                str(tmp_path / "profile"),
                enable_edit_mode=False,
            )

    kwargs = playwright.chromium.launch_persistent_context.call_args.kwargs
    assert kwargs["headless"] is False
    assert set(kwargs) == {"headless"}
    assert client.page is page
    assert page.goto.call_count == 2
    ensure_edit.assert_not_called()


def test_h5p_upload_sets_the_file_input_then_uses_the_package_like_original():
    events = []

    class Locator:
        def __init__(self, name):
            self.first = self
            self.name = name

        def wait_for(self, **options):
            events.append(("wait-" + self.name, options))

        def set_input_files(self, path):
            events.append(("set-files", path))

        def click(self):
            events.append(("click-" + self.name,))

    class Editor:
        def locator(self, selector):
            assert selector == 'input[type="file"]'
            return Locator("file-input")

        def get_by_role(self, role, name):
            assert role == "button"
            assert name.pattern == "^Use$"
            return Locator("use")

        def get_by_text(self, text):
            return Locator("success")

        def wait_for_timeout(self, milliseconds):
            events.append(("pause", milliseconds))

    client = MoodleClient.__new__(MoodleClient)
    client.page = object()
    client._h5p_validation_error = lambda path: ""
    client._upload_h5p_file(Editor(), "C:/resources/example.h5p")

    assert events[0] == ("wait-file-input", {"state": "attached", "timeout": 15_000})
    assert events[1] == ("set-files", "C:/resources/example.h5p")
    assert ("click-use",) in events
    assert events[-1] == ("pause", 3000)


def test_h5p_rejected_package_cancels_the_form():
    class Locator:
        def __init__(self):
            self.first = self

        def wait_for(self, **options):
            pass

        def set_input_files(self, path):
            pass

    class Editor:
        def locator(self, selector):
            return Locator()

        def wait_for_timeout(self, milliseconds):
            pass

    cancelled = []
    client = MoodleClient.__new__(MoodleClient)
    client.page = object()
    client._h5p_editor_frame = lambda: Editor()
    client._select_h5p_upload_mode = lambda editor: None
    client._h5p_validation_error = lambda path: "Paquete H5P rechazado (x.h5p): Moodle no permitió a.js."
    client._cancel_h5p_form = lambda: cancelled.append(True)

    try:
        client._upload_h5p("Recurso", "x.h5p")
    except ValueError as exc:
        assert exc.code == "H5P_PACKAGE_VALIDATION_FAILED"
    else:
        raise AssertionError("debía rechazar el paquete")
    assert cancelled == [True]


def test_h5p_publish_does_not_fill_the_name_like_original():
    events = []
    client = MoodleClient.__new__(MoodleClient)

    class Page:
        def get_by_text(self, text, exact=False):
            return Mock(count=Mock(return_value=0))

    client.page = Page()
    client.begin_add_resource = lambda block: events.append(("add", block))
    client._open_resource_type = lambda module: events.append(("type", module))
    client._fill_name = lambda title: events.append(("name", title))
    client._upload_h5p = lambda title, path: events.append(("h5p", title, path))
    client._save_and_verify = lambda title, module, count, on_before_save=None: "42"

    entry = {"title": "Infografía", "path": "C:/r/i.h5p", "destination": {"block": "digital", "module": "h5p"}}
    assert client.publish(entry) == "42"
    assert events == [("add", "digital"), ("type", "h5p"), ("h5p", "Infografía", "C:/r/i.h5p")]


def test_open_course_turns_on_edit_mode_before_working():
    events = []
    state = {"checked": False}

    class Toggle:
        first = None

        def __init__(self):
            self.first = self

        def count(self):
            return 1

        def wait_for(self, **options):
            pass

        def is_checked(self):
            return state["checked"]

        def click(self):
            events.append("click-edit-mode")
            state["checked"] = True

    class Page:
        def evaluate(self, script):
            return {"authenticated": True, "loginError": ""}

        def goto(self, url, **options):
            events.append("goto")

        def get_by_text(self, text, exact=False):
            return Mock()

        def locator(self, selector):
            assert 'input[name="setmode"]' in selector
            return Toggle()

        def wait_for_timeout(self, milliseconds):
            pass

        def wait_for_load_state(self, state_name):
            pass

    client = MoodleClient.__new__(MoodleClient)
    client.page = Page()
    client.open_course("https://prizma.americana.edu.co/course/view.php?id=1")
    assert events == ["goto", "click-edit-mode"]

    # Si ya está activo no se vuelve a pulsar (pulsarlo lo apagaría).
    client.open_course("https://prizma.americana.edu.co/course/view.php?id=1")
    assert events == ["goto", "click-edit-mode", "goto"]


def test_login_wait_does_not_depend_on_spanish_course_label():
    states = iter([
        {"authenticated": False, "loginError": ""},
        {"authenticated": True, "loginError": ""},
    ])

    class Page:
        def evaluate(self, _script):
            return next(states)

        def wait_for_timeout(self, _milliseconds):
            pass

    client = MoodleClient.__new__(MoodleClient)
    client.page = Page()
    client._wait_for_manual_login()


def test_auditoria_captura_descarga_directa_y_reutiliza_la_pestana(tmp_path):
    pdf = tmp_path / "guia.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    class Download:
        suggested_filename = "guia.pdf"

        def path(self):
            return str(pdf)

    class Page:
        def __init__(self):
            self.handlers = {}

        def is_closed(self):
            return False

        def on(self, name, callback):
            self.handlers[name] = callback

        def remove_listener(self, name, callback):
            if self.handlers.get(name) is callback:
                self.handlers.pop(name)

        def goto(self, *_args, **_kwargs):
            self.handlers["download"](Download())
            raise RuntimeError("Download is starting")

    class Context:
        def __init__(self):
            self.page = Page()
            self.created = 0

        def new_page(self):
            self.created += 1
            return self.page

    context = Context()
    client = MoodleClient(context, object())

    primero = client.audit_activity("https://moodle/recurso-1")
    segundo = client.audit_activity("https://moodle/recurso-2")

    assert primero["download"]["filename"] == "guia.pdf"
    assert primero["download"]["bytes"] == b"%PDF-1.4 test"
    assert segundo["download"]["bytes"] == b"%PDF-1.4 test"
    assert context.created == 1
