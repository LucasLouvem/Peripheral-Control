"""Iluminação na interface: modal de cor, estado pendente e salvamento junto com o DPI."""

import unittest

from gui_helpers import APP, DeferredRunner, WindowCase, click
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

APPLY_DPI_AREA, APPLY_LIGHT_AREA = 2, 4


class LightingCase(WindowCase):
    def setUp(self):
        super().setUp()
        self.card_light = self.window.lighting_card
        self.bar = self.window.action_bar
        self.baseline = len(self.fake.frames)  # quadros da leitura inicial

    def open_dialog(self):
        click(self.card_light.eyedropper)
        self.assertIsNotNone(self.card_light.dialog)
        return self.card_light.dialog

    def pick(self, rgb, confirm=True):
        dialog = self.open_dialog()
        for letter, value in zip("RGB", rgb):
            dialog.spins[letter].setValue(value)
        if confirm:
            click(dialog.confirm_button)
        return dialog

    def light_hex(self):
        return self.card_light.swatch.color


class ModalTest(LightingCase):
    def test_opens_with_the_color_read_from_the_mouse(self):
        dialog = self.open_dialog()
        self.assertEqual(dialog.rgb, (255, 0, 0))
        self.assertEqual([dialog.spins[c].value() for c in "RGB"], [255, 0, 0])
        self.assertEqual(dialog.preview.color, "#ff0000")

    def test_palette_and_channels_stay_in_sync_with_a_local_preview(self):
        dialog = self.open_dialog()
        click(dialog.dots["#0b6efe"])
        self.assertEqual(
            ([dialog.spins[c].value() for c in "RGB"], dialog.preview.color),
            ([11, 110, 254], "#0b6efe"),
        )
        self.assertTrue(dialog.dots["#0b6efe"].isChecked())
        dialog.spins["R"].setValue(12)  # sai da paleta: nenhum ponto marcado e a prévia acompanha
        self.assertEqual((dialog.rgb, dialog.preview.color), ((12, 110, 254), "#0c6efe"))
        self.assertFalse(any(dot.isChecked() for dot in dialog.dots.values()))
        self.assertEqual(len(self.fake.frames), self.baseline)  # prévia não toca o mouse
        self.assertFalse(self.model.pending)

    def test_channels_only_accept_0_to_255(self):
        dialog = self.open_dialog()
        dialog.spins["G"].setValue(999)
        dialog.spins["B"].setValue(-5)
        self.assertEqual(dialog.rgb, (255, 255, 0))


class PickerTest(LightingCase):
    def test_square_and_hue_bar_drive_the_channels_exactly(self):
        dialog = self.open_dialog()
        dialog._from_hsv(120, 255, 255)  # o que o arrasto no seletor produz
        self.assertEqual((dialog.rgb, dialog.hex_edit.text()), ((0, 255, 0), "#00FF00"))
        dialog.square.moved.emit(0.0, 0.0)  # canto superior esquerdo = branco
        self.assertEqual(dialog.rgb, (255, 255, 255))
        dialog.square.moved.emit(1.0, 1.0)  # canto inferior direito = preto
        self.assertEqual(dialog.rgb, (0, 0, 0))
        dialog.hue_bar.moved.emit(
            0.0, 0.5
        )  # matiz 180 com s=255, v=0 → preto; a barra mostra o matiz escolhido
        self.assertEqual(dialog.hue_bar.hue, 180)

    def test_hue_survives_a_gray_pick_and_channels_move_the_picker(self):
        dialog = self.open_dialog()
        dialog.spins["R"].setValue(0)
        dialog.spins["G"].setValue(0)
        dialog.spins["B"].setValue(255)
        self.assertEqual(
            (dialog.hue_bar.hue, dialog.square.sat, dialog.square.val), (240, 255, 255)
        )
        dialog.set_rgb((128, 128, 128))  # cinza não tem matiz: mantém 240
        self.assertEqual((dialog.hue_bar.hue, dialog.square.sat), (240, 0))

    def test_hexadecimal_field_sets_the_color_only_when_complete_and_valid(self):
        dialog = self.open_dialog()
        dialog.hex_edit.clear()
        QTest.keyClicks(dialog.hex_edit, "#0b6e")
        self.assertEqual(dialog.rgb, (255, 0, 0))  # incompleto: nada muda
        QTest.keyClicks(dialog.hex_edit, "fe")
        self.assertEqual(
            (dialog.rgb, [dialog.spins[c].value() for c in "RGB"]),
            ((11, 110, 254), [11, 110, 254]),
        )
        dialog.hex_edit.clear()
        QTest.keyClicks(dialog.hex_edit, "zz#12")
        self.assertEqual(dialog.hex_edit.text(), "#12")  # caracteres inválidos são recusados

    def test_copy_button_puts_the_hexadecimal_in_the_clipboard(self):
        dialog = self.open_dialog()
        dialog.set_rgb((11, 110, 254))
        click(dialog.copy_button)
        self.assertEqual(APP.clipboard().text(), "#0B6EFE")

    def test_recent_colors_are_listed_pickable_and_remembered_after_confirm(self):
        self.pick((1, 2, 3))
        self.pick((4, 5, 6))
        self.assertEqual(self.model.recent.colors, ((4, 5, 6), (1, 2, 3)))  # mais recente primeiro
        dialog = self.open_dialog()
        click(dialog.recent_tab)
        self.assertEqual(dialog.pages.currentIndex(), 1)
        click(dialog.recent_dots[(1, 2, 3)])
        self.assertEqual(dialog.rgb, (1, 2, 3))
        click(dialog.cancel_button)
        self.assertEqual(self.model.recent.colors, ((4, 5, 6), (1, 2, 3)))  # cancelar não registra

    def test_palette_click_and_cancel_do_not_touch_recent_colors(self):
        click(self.card_light.dots["#0b6efe"])
        self.assertEqual(self.model.recent.colors, ())


class ConfirmCancelTest(LightingCase):
    def test_confirm_becomes_pending_without_writing(self):
        self.pick((0, 128, 255))
        self.assertIsNone(self.card_light.dialog)
        self.assertEqual(self.model.light_edit.rgb, (0, 128, 255))
        self.assertTrue(self.bar.save_button.isEnabled())
        self.assertEqual(self.light_hex(), "#0080ff")
        self.assertEqual(self.window.mouse_panel.view._model.light_hex, "#0080ff")
        self.assertEqual(self.card_light.effect.currentText(), "Estático")
        self.assertTrue(self.card_light.effect.property("edited"))
        self.assertEqual(
            (len(self.fake.frames), self.fake.writes, self.fake.light_window(0).hex()),
            (self.baseline, [], "ff00000102040380"),
        )

    def test_cancel_escape_and_close_discard_only_that_opening(self):
        self.pick((1, 2, 3))
        for how in ("cancel", "escape", "close"):
            with self.subTest(how):
                dialog = self.open_dialog()
                self.assertEqual(dialog.rgb, (1, 2, 3))  # reabrir mostra a configuração pendente
                dialog.spins["R"].setValue(200)
                if how == "cancel":
                    click(dialog.cancel_button)
                elif how == "escape":
                    QTest.keyClick(dialog, Qt.Key.Key_Escape)
                else:
                    dialog.close()
                APP.processEvents()
                self.assertIsNone(self.card_light.dialog)
                self.assertEqual(self.model.light_edit.rgb, (1, 2, 3))
        self.assertEqual(len(self.fake.frames), self.baseline)

    def test_cancel_without_a_pending_edit_leaves_nothing_pending(self):
        dialog = self.open_dialog()
        dialog.spins["B"].setValue(77)
        click(dialog.cancel_button)
        self.assertFalse(self.model.pending)
        self.assertEqual(self.light_hex(), "#ff0000")

    def test_does_not_open_while_the_mouse_is_busy(self):
        self.model.status = "saving"
        click(self.card_light.eyedropper)
        self.assertIsNone(self.card_light.dialog)


class SaveTest(LightingCase):
    def test_save_sends_only_the_color_record_and_applies_lighting(self):
        before = bytes(self.fake.memory)
        self.pick((0, 128, 255))
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [(0x449, bytes.fromhex("0080ff010202"))])
        self.assertEqual([f[3] for f in self.fake.f1_frames], [APPLY_LIGHT_AREA])
        self.assertEqual(self.fake.light_window(0).hex(), "0080ff0102020380")
        self.assertEqual(
            {i for i in range(len(before)) if before[i] != self.fake.memory[i]},
            {0x449, 0x44A, 0x44B, 0x44E},
        )
        self.assertFalse(self.model.pending)
        self.assertIn("Salvo e confirmado", self.bar.message_label.text())
        self.assertEqual(
            (self.card_light.effect.currentText(), self.light_hex()),
            ("Estático", "#0080ff"),
        )
        self.assertFalse(self.card_light.effect.property("edited"))

    def test_dpi_and_color_are_saved_together_and_edited_independently(self):
        self.choose(0, 1000)
        self.pick((1, 2, 3))
        self.assertEqual(
            (self.model.edits, self.model.light_edit.rgb), ({0: 1000}, (1, 2, 3))
        )  # a cor não apagou o DPI
        click(self.bar.save_button)
        self.assertEqual(
            self.fake.writes,
            [
                (0x45, bytes.fromhex("16 00 16 00")),
                (0x449, bytes.fromhex("010203010202")),
            ],
        )
        self.assertEqual([f[3] for f in self.fake.f1_frames], [APPLY_DPI_AREA, APPLY_LIGHT_AREA])
        self.assertFalse(self.model.pending)

    def test_discard_drops_dpi_and_color_without_io(self):
        self.choose(0, 1000)
        self.pick((1, 2, 3))
        self.model.discard()
        self.assertEqual(
            (self.model.edits, self.model.light_edit, self.model.pending),
            ({}, None, False),
        )
        self.assertEqual(self.light_hex(), "#ff0000")
        self.assertEqual(len(self.fake.frames), self.baseline)

    def test_failed_save_keeps_the_pending_color(self):
        self.pick((0, 128, 255))
        self.fake.fail_write_number = 1
        click(self.bar.save_button)
        self.assertEqual(self.model.light_edit.rgb, (0, 128, 255))
        self.assertNotIn("Salvo e confirmado", self.bar.message_label.text())
        self.assertEqual(self.fake.light_window(0).hex(), "ff00000102040380")
        self.assertEqual(self.fake.f1_frames, [])

    def test_external_change_is_a_conflict_and_keeps_the_edit(self):
        self.pick((0, 128, 255))
        self.fake.memory[0x449] = 0x10
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [])
        self.assertEqual(self.model.light_edit.rgb, (0, 128, 255))
        self.assertIn("outro programa", self.bar.message_label.text())

    def test_choosing_the_color_the_mouse_already_has_is_not_a_change(self):
        self.pick((0, 128, 255))
        click(self.bar.save_button)
        self.pick((0, 128, 255))
        self.assertFalse(self.model.pending)
        self.assertFalse(self.bar.save_button.isEnabled())

    def test_switching_profile_drops_the_pending_color_and_shows_that_profile_lighting(
        self,
    ):
        self.model._view_profile = None
        self.pick((1, 2, 3))
        self.model.select_profile(1)
        self.assertIsNone(self.model.light_edit)
        self.assertEqual(
            (self.light_hex(), self.card_light.effect.currentText()),
            ("#ff0000", "Onda"),
        )  # perfil 2: onda de fábrica


class CardControlsTest(LightingCase):
    def choose_effect(self, name):
        combo = self.card_light.effect
        combo.setCurrentIndex(combo.findText(name))
        combo.activated.emit(combo.currentIndex())
        APP.processEvents()

    def test_palette_color_is_pending_and_the_modal_is_only_for_other_colors(self):
        click(self.card_light.dots["#0b6efe"])
        self.assertIsNone(self.card_light.dialog)
        self.assertEqual(
            (self.model.light_edit.rgb, self.model.light_edit.effect.value),
            ((11, 110, 254), "static"),
        )
        self.assertTrue(self.card_light.dots["#0b6efe"].isChecked())
        self.assertEqual((len(self.fake.frames), self.fake.writes), (self.baseline, []))

    def test_an_effect_the_program_does_not_edit_is_shown_without_a_selection(self):
        combo = self.card_light.effect
        self.assertEqual(
            (combo.currentIndex(), combo.placeholderText()), (-1, "Respiração")
        )  # perfil 0 de fábrica do teste
        self.assertFalse(self.card_light.speed_row.isVisible())

    def test_wave_shows_rainbow_and_speed_and_keeps_the_color_controls_usable(self):
        self.model.select_profile(1)  # onda de fábrica, velocidade 4
        APP.processEvents()
        card = self.card_light
        self.assertTrue(card.speed_row.isVisible())
        self.assertEqual(card.speed_slider.value(), 9 - 4)
        self.assertTrue(card.swatch.multicolor)
        self.assertTrue(
            all(d.isEnabled() for d in card.dots.values()) and card.eyedropper.isEnabled()
        )
        self.assertFalse(any(d.isChecked() for d in card.dots.values()))

    def test_picking_a_color_while_in_wave_goes_static_and_wave_again_keeps_that_color(
        self,
    ):
        self.model.select_profile(1)
        click(self.card_light.dots["#0b6efe"])
        self.assertEqual(
            (self.model.light_edit.effect.value, self.card_light.effect.currentText()),
            ("static", "Estático"),
        )
        self.assertFalse(self.card_light.swatch.multicolor)
        self.choose_effect("Onda")
        self.assertEqual(
            (self.model.light_edit.rgb, self.model.light_edit.speed),
            ((11, 110, 254), 4),
        )
        click(self.bar.save_button)
        self.assertEqual(
            self.fake.light_window(1).hex(), "0b6efe0204000280"
        )  # cor escolhida guardada, onda, vel 4, brilho preservado
        self.assertEqual(
            self.fake.writes, [(0x451, bytes.fromhex("0b6efe"))]
        )  # só os 3 bytes de cor mudam

    def test_wave_speed_slider_is_inverted_slow_left_fast_right(self):
        self.model.select_profile(1)
        slider = self.card_light.speed_slider
        slider.setValue(8)  # todo à direita = rápido = 1 no aparelho
        self.assertEqual(self.model.light_edit.speed, 1)
        slider.setValue(1)  # todo à esquerda = devagar = 8
        self.assertEqual(self.model.light_edit.speed, 8)
        self.assertEqual(len(self.fake.writes), 0)

    def test_choosing_wave_then_saving_writes_mode_and_speed_only(self):
        self.choose_effect("Onda")
        self.assertTrue(self.card_light.speed_row.isVisible())
        self.assertEqual(
            (self.model.light_edit.effect.value, self.model.light_edit.speed),
            ("wave", 2),
        )  # velocidade lida do aparelho
        self.card_light.speed_slider.setValue(8)
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [(0x44C, bytes.fromhex("020100"))])
        self.assertEqual(self.fake.light_window(0).hex(), "ff00000201000380")
        self.assertEqual(
            (
                self.card_light.effect.currentText(),
                self.card_light.speed_slider.value(),
            ),
            ("Onda", 8),
        )
        self.assertFalse(self.model.pending)

    def test_back_to_static_from_a_pending_wave_restores_the_color_controls(self):
        self.choose_effect("Onda")
        self.choose_effect("Estático")
        self.assertTrue(all(d.isEnabled() for d in self.card_light.dots.values()))
        self.assertFalse(self.card_light.speed_row.isVisible())
        self.assertEqual(self.model.light_edit.effect.value, "static")


class BusyTest(LightingCase):
    runner_class = DeferredRunner

    def test_color_cannot_be_edited_while_saving(self):
        self.runner.run_all()
        self.pick((0, 128, 255))
        click(self.bar.save_button)  # fica pendente no runner adiado
        self.assertTrue(self.model.busy)
        click(self.card_light.eyedropper)
        self.assertIsNone(self.card_light.dialog)
        self.assertFalse(self.card_light.effect.isEnabled())
        self.runner.run_all()
        self.assertFalse(self.model.pending)


if __name__ == "__main__":
    unittest.main()
