"""Janela: composição, textos, itens futuros, redimensionamento e opção de captura (mouse simulado)."""

import tempfile
import unittest
from itertools import combinations
from pathlib import Path

from gui_helpers import APP, WindowCase, click, rect_in
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QAbstractButton, QLabel

from hidctl.gui import app as gui_app
from hidctl.gui.dpi_model import DpiModel
from hidctl.gui.main_window import MINIMUM_SIZE, REFERENCE_SIZE, MainWindow
from hidctl.gui.widgets.mouse_panel import DISPLAY_LIMIT

SIZES = (
    (REFERENCE_SIZE.width(), REFERENCE_SIZE.height()),
    (1366, 768),
    (MINIMUM_SIZE.width(), MINIMUM_SIZE.height()),
)
FUTURE = "disponível futuramente"
OLD_TEXTS = ("King Cobra", "12000", "Mouse Control", "Aplicar ao mouse", "Perfil local")


def all_texts(window) -> list[str]:
    texts = [w.text() for w in window.findChildren(QLabel)]
    texts += [w.text() for w in window.findChildren(QAbstractButton)]
    texts.append(window.windowTitle())
    return texts


class CompositionTest(WindowCase):
    def test_names_and_texts(self):
        self.assertEqual(self.window.windowTitle(), "Peripheral Control")
        self.assertEqual(self.window.header.title.text(), "Cobra M711")
        self.assertEqual(self.bar.save_button.text(), "Salvar")
        self.assertIn("Peripheral Control", all_texts(self.window))
        self.assertIn("Kit S118", all_texts(self.window))
        self.assertNotIn("Conectado via USB", " | ".join(all_texts(self.window)))
        joined = " | ".join(all_texts(self.window))
        for old in OLD_TEXTS:
            self.assertNotIn(old, joined)

    def test_simulated_badge_only_in_demo_mode(self):
        self.assertTrue(self.window.header.badge.isVisible())
        self.assertEqual(self.window.header.badge.text(), "SIMULADO")
        real = MainWindow(DpiModel(self.controller), simulated=False)
        real.show()
        self.assertFalse(real.header.badge.isVisible())
        real.close()

    def test_sidebar_is_compact_and_has_only_device_macros_and_settings(self):
        sidebar = self.window.sidebar
        self.assertEqual(list(sidebar.nav_buttons), ["Macros"])
        self.assertEqual(sidebar.active_item, "Dispositivo")
        self.assertLessEqual(sidebar.width(), 80)
        # só ícones: o nome de cada opção aparece como dica ao passar o mouse
        self.assertEqual(sidebar.device_button.toolTip(), "Dispositivo: Cobra M711 (kit S118)")
        self.assertEqual(sidebar.nav_buttons["Macros"].toolTip(), "Macros")
        self.assertEqual(sidebar.settings_button.toolTip(), "Configurações")
        for removed in ("DPI", "Iluminação", "Visão geral"):
            self.assertNotIn(removed, sidebar.nav_buttons)
        texts = [w.text() for w in sidebar.findChildren(QLabel)]
        self.assertEqual([t for t in texts if t], [])  # nenhum rótulo de texto na barra lateral

    def test_home_screen_has_only_dpi_and_lighting(self):
        w = self.window
        self.assertFalse(hasattr(w, "macros_card"))
        titles = [c.title_label.text() for c in (w.dpi_card, w.lighting_card)]
        self.assertEqual(titles, ["DPI", "Iluminação"])
        joined = " | ".join(t for t in all_texts(w))
        for gone in (
            "Copiar e colar",
            "Gerenciar macros",
            "Atalho de trabalho",
            "ativo no mouse (acompanha",
            "testado = gravado",
        ):
            self.assertNotIn(gone, joined)


class FutureItemsTest(WindowCase):
    def targets(self):
        return {
            "Macros": self.window.sidebar.nav_buttons["Macros"],
            "Configurações": self.window.sidebar.settings_button,
        }

    def test_each_future_item_warns_without_touching_state_or_device(self):
        for name, widget in self.targets().items():
            with self.subTest(item=name):
                self.window.toast.hide()
                frames, edits = len(self.fake.frames), dict(self.model.edits)
                click(widget)
                self.assertTrue(self.window.toast.isVisible())
                self.assertIn(FUTURE, self.window.toast.text().lower())
                self.assertEqual((len(self.fake.frames), self.model.edits), (frames, edits))
                self.assertEqual(self.window.sidebar.active_item, "Dispositivo")

    def test_device_button_is_the_current_screen_and_does_not_warn(self):
        self.window.toast.hide()
        click(self.window.sidebar.device_button)
        self.assertFalse(self.window.toast.isVisible())


class ResizeTest(WindowCase):
    def layout_checks(self, width, height):
        w = self.window
        w.resize(width, height)
        APP.processEvents()
        body = w.body_scroll.widget()
        self.assertEqual(w.body_scroll.horizontalScrollBar().maximum(), 0)
        cards = [w.dpi_card, w.lighting_card]
        for card in cards:
            self.assertTrue(body.rect().contains(rect_in(body, card)), (width, height, card))
        self.assertFalse(
            rect_in(body, w.dpi_card).intersects(rect_in(body, w.lighting_card)),
            (width, height),
        )
        mouse, light = rect_in(body, w.mouse_panel), rect_in(body, w.lighting_card)
        self.assertLessEqual(mouse.bottom(), light.top() + 1)  # a iluminação fica abaixo do mouse
        self.assertLess(
            rect_in(body, w.lighting_card).right(), rect_in(body, w.dpi_card).left()
        )  # DPI à direita
        lighting = w.lighting_card
        parts = [lighting.swatch, *lighting.dots.values(), lighting.eyedropper]
        boxes = [rect_in(lighting, p) for p in parts]
        for first, second in combinations(boxes, 2):
            self.assertFalse(first.intersects(second), (width, height))
        for box in boxes + [rect_in(lighting, lighting.effect)]:
            self.assertTrue(lighting.rect().contains(box), (width, height))

        card = w.dpi_card
        columns = [rect_in(card, c) for c in card.columns]
        for first, second in combinations(columns, 2):
            self.assertFalse(first.intersects(second), (width, height))
        for column in card.columns:
            box = rect_in(card, column)
            self.assertTrue(card.rect().contains(box), (width, height, column.level))
            self.assertGreaterEqual(column.slider.height(), 70)
            parts = [column.check, column.slider, column.value_label, column.caption]
            rects = [rect_in(column, p) for p in parts]
            for upper, lower in zip(rects, rects[1:]):
                self.assertLessEqual(
                    upper.bottom(), lower.top() + 1, (width, height, column.level)
                )  # empilhados sem sobrepor
            self.assertGreater(
                column.width(),
                column.value_label.fontMetrics().horizontalAdvance(column.value_label.text()) + 8,
            )
        self.assertTrue(card.rect().contains(rect_in(card, card.reload_button)))

        bar = w.action_bar
        self.assertTrue(bar.rect().contains(rect_in(bar, bar.save_button)))
        if (
            bar.message_label.isVisible()
        ):  # a mensagem fica em linha própria, acima dos botões, sem cortes
            message = rect_in(bar, bar.message_label)
            self.assertTrue(bar.rect().contains(message))
            self.assertGreater(
                message.top(), rect_in(bar, bar.save_button).bottom() - 1
            )  # a mensagem fica abaixo da linha do Salvar
            self.assertGreaterEqual(
                message.height(), bar.message_label.heightForWidth(message.width()) - 1
            )

        view = w.mouse_panel.view
        image = view.image_rect()
        self.assertLess(abs(image.width() / image.height() - 350 / 550), 0.02)
        self.assertTrue(view.rect().contains(image))

    def test_layout_is_consistent_at_each_size(self):
        """Falha se algo se sobrepuser/cortar em 1586x940, 1366x768 ou no mínimo, inclusive com mensagem longa e edição."""
        self.choose(0, 1000)
        self.fake.fail_write_number = 1
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                self.layout_checks(width, height)
        click(self.bar.save_button)  # mensagem de falha longa na barra
        self.assertGreater(len(self.bar.message_label.text()), 40)
        for width, height in SIZES:
            with self.subTest(size=(width, height), message="longa"):
                self.layout_checks(width, height)

    def test_content_keeps_a_margin_from_the_bottom_edge(self):
        """Falha se o cartão de DPI ou a iluminação encostarem na borda de baixo da janela."""
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                APP.processEvents()
                for card in (self.window.dpi_card, self.window.lighting_card):
                    bottom = card.mapTo(self.window, card.rect().bottomLeft()).y()
                    self.assertGreaterEqual(self.window.height() - bottom, 16, card)

    def test_level_labels_stay_next_to_the_slider_in_tall_windows(self):
        """Falha se a sobra de altura afastar o valor, a evidência e o nome do nível uns dos outros."""
        self.window.resize(1586, 1040)
        APP.processEvents()
        for column in self.card.columns:
            self.assertLessEqual(
                column.caption.geometry().top() - column.value_label.geometry().bottom(),
                8,
            )
            self.assertLessEqual(column.slider.height(), 300)
            last = column.layout().itemAt(column.layout().count() - 1)
            self.assertIsNotNone(
                last.spacerItem(),
                "falta o espaçador final: a sobra de altura iria para entre as etiquetas",
            )

    def test_window_is_compact_by_default(self):
        """O objetivo é ocupar pouca tela: janela inicial pequena, fontes pequenas e sem rolagem."""
        window = MainWindow(self.model, simulated=True)
        self.addCleanup(window.close)
        window.show()
        APP.processEvents()
        self.assertLessEqual((window.width(), window.height()), (1000, 620))
        self.assertLessEqual((MINIMUM_SIZE.width(), MINIMUM_SIZE.height()), (900, 540))
        self.assertLessEqual(window.sidebar.width(), 56)
        self.assertEqual(window.body_scroll.verticalScrollBar().maximum(), 0)
        for label in (
            window.dpi_card.columns[0].value_label,
            window.header.subtitle,
            window.action_bar.name_label,
        ):
            self.assertLessEqual(label.fontInfo().pixelSize(), 14, label.text())
        self.assertLessEqual(window.header.title.fontInfo().pixelSize(), 24)
        self.assertLessEqual(window.action_bar.height(), 40)  # só a linha do perfil e do Salvar

    def test_window_does_not_shrink_below_minimum(self):
        self.window.resize(500, 400)
        APP.processEvents()
        self.assertGreaterEqual(self.window.width(), MINIMUM_SIZE.width())
        self.assertGreaterEqual(self.window.height(), MINIMUM_SIZE.height())

    def test_mouse_is_small_and_never_scaled_up(self):
        view = self.window.mouse_panel.view
        self.window.resize(*SIZES[0])
        APP.processEvents()
        size = view.image_rect().size()
        self.assertLessEqual(
            (size.width(), size.height()),
            (DISPLAY_LIMIT.width(), DISPLAY_LIMIT.height()),
        )
        self.assertLessEqual(size.width(), 160)  # bem menor que a arte nativa (350x550)
        self.window.resize(3000, 2000)
        APP.processEvents()
        self.assertLessEqual(
            view.image_rect().width(), DISPLAY_LIMIT.width()
        )  # mesmo em janela enorme, não cresce


class MissingAssetTest(WindowCase):
    def test_window_opens_with_placeholder_when_assets_are_missing(self):
        with tempfile.TemporaryDirectory() as empty:
            window = MainWindow(self.model, assets_dir=Path(empty), simulated=True)
            window.show()
            APP.processEvents()
            self.assertFalse(window.mouse_panel.view.has_image)
            self.assertFalse(window.mouse_panel.view.grab().toImage().isNull())
            window.close()


class ScreenshotCliTest(unittest.TestCase):
    def test_demo_screenshot_has_requested_size_and_real_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ui.png"
            self.assertEqual(
                gui_app.main(["--demo", "--screenshot", str(target), "--size", "1300x800"]),
                0,
            )
            image = QImage(str(target))
            self.assertEqual((image.width(), image.height()), (1300, 800))
            colors = {image.pixel(x, y) for x in range(0, 1300, 50) for y in range(0, 800, 50)}
            self.assertGreater(len(colors), 5)

    def test_invalid_sizes_are_rejected_without_creating_file(self):
        for bad in ("0x0", "abc", "1200", "100x100", "1200x", "99999x800", "-5x800"):
            with self.subTest(size=bad), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "ui.png"
                with self.assertRaises(SystemExit) as raised:
                    gui_app.main(["--demo", "--screenshot", str(target), "--size", bad])
                self.assertEqual(raised.exception.code, 2)
                self.assertFalse(target.exists())

    def test_unwritable_target_returns_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing" / "ui.png"
            self.assertEqual(gui_app.main(["--demo", "--screenshot", str(target)]), 1)
            self.assertFalse(target.exists())

    def test_demo_never_builds_the_real_connector(self):
        from unittest import mock

        with (
            mock.patch(
                "hidctl.devices.fc30_mouse.dpi_service.open_mouse",
                side_effect=AssertionError("tocou no aparelho"),
            ),
            tempfile.TemporaryDirectory() as tmp,
        ):
            self.assertEqual(
                gui_app.main(["--demo", "--screenshot", str(Path(tmp) / "a.png")]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
