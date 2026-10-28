"""DPI real na interface: leitura inicial, sliders, nível ativo ao vivo, salvar e falhas (mouse simulado)."""

import unittest
from unittest import mock

from gui_helpers import APP, DeferredRunner, WindowCase, click
from PySide6.QtTest import QTest

from hidctl.gui.watcher import LevelWatcher

LISTED = [500, 800, 1000, 1200, 2000, 2400, 3000, 3600, 5000]


class InitialReadTest(WindowCase):
    def test_opening_only_reads_and_shows_the_five_real_levels(self):
        self.assertEqual((self.fake.f3_frames, self.fake.f1_frames, self.fake.writes), ([], [], []))
        self.assertEqual(self.texts(), ["800", "1200", "2400", "3600", "5000"])
        self.assertEqual(self.bar.name_label.text(), "Perfil 1")
        self.assertFalse(
            self.window.header.status.isVisible()
        )  # tudo certo: nenhum texto de conexão
        self.assertFalse(self.window.header.dot.isVisible())
        self.assertFalse(self.model.pending)
        self.assertFalse(self.bar.save_button.isEnabled())

    def test_each_slider_steps_through_exactly_the_released_values(self):
        for column in self.card.columns:
            self.assertEqual([o.nominal for o in column._options], LISTED)
            self.assertEqual((column.slider.minimum(), column.slider.maximum()), (0, 8))
        self.assertEqual(
            [c.slider.value() for c in self.card.columns], [1, 3, 5, 7, 8]
        )  # posição de 800,1200,2400,3600,5000
        self.assertTrue(all(c.slider.orientation().name == "Vertical" for c in self.card.columns))
        for forbidden in (10000, 12000, 6400, 1600, 3200):
            self.assertNotIn(forbidden, [o.nominal for o in self.card.columns[0]._options])

    def test_screen_has_no_explanatory_text(self):
        """A interface se explica sozinha: nada de legendas, evidência escrita ou instruções na tela."""
        from PySide6.QtWidgets import QLabel

        shown = " | ".join(
            w.text() for w in self.window.findChildren(QLabel) if w.text() and w.isVisible()
        )
        for gone in (
            "arraste",
            "testado",
            "relido",
            "ATIVO",
            "acompanha",
            "Estado do mouse lido",
        ):
            self.assertNotIn(gone, shown)
        self.assertFalse(hasattr(self.card, "caption"))
        self.assertFalse(hasattr(self.card, "legend"))
        self.assertFalse(hasattr(self.card.columns[0], "evidence"))

    def test_evidence_is_visible_in_the_tooltip(self):
        self.assertIn("testado no aparelho", self.card.columns[0].slider.toolTip())
        self.assertIn("sem medição física", self.card.columns[1].slider.toolTip())
        self.assertNotIn("testado no aparelho", self.card.columns[1].slider.toolTip())

    def test_enabled_checkboxes_mirror_the_device_and_are_not_editable(self):
        self.assertTrue(all(c.check.checked for c in self.card.columns))
        self.assertIn("não está disponível", self.card.columns[0].check.toolTip())
        self.fake.memory[0x42 + 2 + 6 * 2] = 0
        self.model.reload()
        self.assertEqual(
            [c.check.checked for c in self.card.columns],
            [True, True, False, True, True],
        )


class ActiveLevelTest(WindowCase):
    def active(self):
        return [bool(c.value_label.property("active")) for c in self.card.columns]

    def test_initial_active_level_comes_from_the_device_and_is_the_green_number(self):
        self.assertEqual(self.active(), [True, False, False, False, False])
        from hidctl.gui import theme

        self.assertIn(
            'QLabel#levelValue[active="true"] { color: %s' % theme.GREEN,
            APP.styleSheet(),
        )  # número ativo = verde
        self.assertEqual(self.card.columns[0].value_label.toolTip(), "Nível ativo no mouse")
        self.assertEqual(self.card.columns[1].value_label.toolTip(), "")
        self.fake.memory[0x42] = 3
        self.model.reload()
        self.assertEqual(self.active(), [False, False, False, True, False])

    def test_live_events_move_the_active_marker_without_touching_the_device_or_the_edits(
        self,
    ):
        self.choose(1, 1000)
        frames = len(self.fake.frames)
        for level in (2, 3, 4, 4, 3, 2, 0):
            self.model.set_live_active(level)
            self.assertEqual(self.active(), [i == level for i in range(5)])
        self.assertEqual(len(self.fake.frames), frames)  # evento ≠ comando: nada vai ao mouse
        self.assertEqual(self.model.edits, {1: 1000})

    def test_invalid_events_are_ignored(self):
        self.model.set_live_active(2)
        for bad in (5, -1, 99, True, None, "2", 2.0):
            self.model.set_live_active(bad)
        self.assertEqual(self.active(), [False, False, True, False, False])

    def test_moving_a_slider_never_changes_which_level_is_active(self):
        self.model.set_live_active(1)
        self.choose(3, 500)
        self.choose(0, 5000)
        self.assertEqual(self.active(), [False, True, False, False, False])

    def test_reload_and_save_resync_with_the_device(self):
        self.model.set_live_active(4)
        self.fake.memory[0x42] = 1
        click(self.card.reload_button)
        self.assertEqual(self.active(), [False, True, False, False, False])
        self.model.set_live_active(3)
        self.choose(0, 1000)
        self.fake.memory[0x42] = 2
        click(self.bar.save_button)
        self.assertEqual(
            self.active(), [False, False, True, False, False]
        )  # a releitura do salvar é a verdade mais nova

    def test_qt_watcher_forwards_events_to_the_model(self):
        def fake_listen(stop, on_level):
            on_level(3)
            on_level(9)  # inválido: ignorado pelo modelo
            stop.wait(5)

        with mock.patch("hidctl.gui.watcher.events.listen", side_effect=fake_listen):
            watcher = LevelWatcher()
            watcher.level_changed.connect(self.model.set_live_active)
            watcher.start()
            for _ in range(100):
                QTest.qWait(20)
                if self.model.active_level == 3:
                    break
            watcher.stop()
        self.assertEqual(self.model.active_level, 3)
        self.assertFalse(watcher.isRunning())


class LocalEditTest(WindowCase):
    def test_dragging_sliders_and_reloading_never_writes(self):
        for level in range(5):
            self.choose(level, 1000)
        self.choose(2, 3000)
        self.choose(4, 800)
        self.assertEqual((self.fake.f3_frames, self.fake.f1_frames, self.fake.writes), ([], [], []))
        self.assertEqual(self.fake.block(0)[0], 0)  # o nível ativo do mouse não mudou

    def test_edit_shows_pending_state_and_marks_only_the_edited_levels(self):
        self.choose(0, 1000)
        self.assertEqual(self.model.edits, {0: 1000})
        self.assertEqual(self.texts(), ["1000", "1200", "2400", "3600", "5000"])
        self.assertEqual(
            [c.value_label.property("edited") for c in self.card.columns],
            [True, False, False, False, False],
        )
        self.assertTrue(self.bar.save_button.isEnabled())
        self.assertIn(
            "testado no aparelho", self.card.columns[0].slider.toolTip()
        )  # 1000 foi percebido
        self.choose(3, 500)
        self.assertIn("sem medição física", self.card.columns[3].slider.toolTip())

    def test_returning_to_the_device_value_removes_the_pending_state(self):
        self.choose(0, 1000)
        self.choose(0, 800)
        self.assertEqual(self.model.edits, {})
        self.assertFalse(self.bar.save_button.isEnabled())

    def test_bar_has_only_the_save_button_and_hides_informative_messages(self):
        from PySide6.QtWidgets import QPushButton

        self.assertEqual(
            [b.text() for b in self.bar.findChildren(QPushButton) if b.text()],
            ["Salvar"],
        )  # os demais só têm ícone
        self.assertFalse(
            self.bar.message_label.isVisible()
        )  # "Estado do mouse lido." é só informativo
        self.assertFalse(hasattr(self.bar, "discard_button"))

    def test_closing_without_saving_writes_nothing_and_leaves_the_mouse_unchanged(self):
        self.choose(0, 1000)
        before = (self.fake.block(0), len(self.fake.frames))
        self.window.close()
        APP.processEvents()
        self.assertEqual((self.fake.block(0), len(self.fake.frames)), before)
        self.assertEqual(self.fake.writes, [])

    def test_discard_restores_the_last_known_state_without_any_write(self):
        self.choose(0, 1000)
        self.choose(4, 500)
        frames = len(self.fake.frames)
        self.model.discard()  # sem botão: o descarte acontece ao sair; o modelo ainda o faz sem I/O
        self.assertEqual(self.model.edits, {})
        self.assertEqual(self.texts(), ["800", "1200", "2400", "3600", "5000"])
        self.assertEqual([c.slider.value() for c in self.card.columns], [1, 3, 5, 7, 8])
        self.assertFalse(self.bar.save_button.isEnabled())
        self.assertEqual((len(self.fake.frames), self.fake.writes), (frames, []))

    def test_invalid_values_cannot_enter_the_model(self):
        for level, value in (
            (0, 12000),
            (0, 10000),
            (0, 1600),
            (0, True),
            (0, "800"),
            (0, None),
            (5, 800),
            (-1, 800),
            (True, 800),
        ):
            with self.subTest(level=level, value=value), self.assertRaises(ValueError):
                self.model.set_value(level, value)
        self.assertEqual(self.model.edits, {})

    def test_unvalidated_and_disabled_levels(self):
        self.fake.set_level_code(0, 2, 0x31)  # código que não está na tabela
        self.fake.memory[0x42 + 2 + 6 * 3] = 0  # nível 4 desabilitado
        self.model.reload()
        APP.processEvents()
        unknown, disabled = self.card.columns[2], self.card.columns[3]
        self.assertEqual(unknown.value_label.text(), "≈2178*")
        self.assertTrue(unknown.slider.property("unvalidated"))
        self.assertIn("não validado", unknown.slider.toolTip())
        self.assertTrue(unknown.slider.isEnabled())
        self.assertEqual(self.model.edits, {})  # só olhar não edita
        self.choose(2, 1000)  # trocar explicitamente por um valor liberado é permitido
        self.assertEqual(self.model.edits, {2: 1000})
        self.assertEqual(disabled.value_label.text(), "—")
        self.assertIn("desabilitado", disabled.slider.toolTip())
        self.assertFalse(disabled.slider.isEnabled())
        with self.assertRaises(ValueError):
            self.model.set_value(3, 1000)


class SaveTest(WindowCase):
    def test_save_writes_only_changed_levels_and_confirms_by_readback(self):
        original = {p: self.fake.block(p) for p in range(5)}
        self.choose(0, 1000)
        self.choose(3, 800)
        self.fake.frames.clear()
        click(self.bar.save_button)
        self.assertEqual(
            self.fake.writes,
            [
                (0x45, bytes.fromhex("16 00 16 00")),
                (0x57, bytes.fromhex("12 00 12 00")),
            ],
        )
        self.assertEqual(len(self.fake.f1_frames), 1)
        self.assertEqual(
            self.bar.message_label.text(),
            "Salvo e confirmado por releitura (nível 1, 4).",
        )
        self.assertFalse(self.model.pending)
        self.assertEqual(self.texts(), ["1000", "1200", "2400", "800", "5000"])
        self.assertEqual([c.value_label.property("edited") for c in self.card.columns], [False] * 5)
        for profile in range(1, 5):
            self.assertEqual(self.fake.block(profile), original[profile])
        after = self.fake.block(0)
        self.assertEqual([i for i in range(32) if after[i] != original[0][i]], [3, 5, 21, 23])

    def test_save_is_never_triggered_by_other_controls(self):
        self.choose(0, 1000)
        click(self.card.reload_button)
        self.assertEqual(self.fake.writes, [])

    def test_failure_keeps_the_pending_edit_and_reports_the_known_result(self):
        self.choose(0, 1000)
        self.choose(3, 800)
        self.choose(4, 1000)
        self.fake.fail_write_number = 2
        click(self.bar.save_button)
        self.assertEqual(
            self.model.edits, {3: 800, 4: 1000}
        )  # o nível 1 já está no mouse e deixou de ser pendente
        self.assertEqual(self.model.loaded.levels[0].nominal, 1000)
        self.assertIn("PARCIAL", self.bar.message_label.text())
        self.assertEqual(self.bar.message_label.property("kind"), "error")
        self.assertTrue(self.bar.save_button.isEnabled())
        self.assertEqual(len(self.fake.f3_frames), 2)  # nada repetido
        self.assertEqual(self.fake.f1_frames, [])
        self.assertEqual(self.texts()[3:], ["800", "1000"])  # a edição continua visível

    def test_divergent_readback_is_not_shown_as_success(self):
        self.choose(0, 1000)
        self.fake.corrupt_after_apply = {0x45: 0x12, 0x47: 0x12}
        click(self.bar.save_button)
        self.assertIn("NÃO confirmou", self.bar.message_label.text())
        self.assertNotIn("Salvo e confirmado", self.bar.message_label.text())
        self.assertEqual(self.model.edits, {0: 1000})
        self.assertEqual(self.card.columns[0].value_label.text(), "1000")

    def test_disconnect_during_save_preserves_the_edit(self):
        self.choose(0, 1000)
        self.fake.fail_after_frames = (
            len(self.fake.frames) + 5
        )  # lock, 3 leituras e o F3: cai no F1
        click(self.bar.save_button)
        self.assertEqual(self.model.edits, {0: 1000})
        self.assertIn("INCERTO", self.bar.message_label.text())

    def test_conflict_with_an_external_change_writes_nothing_and_shows_the_real_value(
        self,
    ):
        self.choose(0, 1000)
        self.fake.set_level_code(0, 0, 0x2E)  # outro programa colocou 2000
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [])
        self.assertIn("outro programa", self.bar.message_label.text())
        self.assertEqual(self.model.saved_value_of(0), 2000)
        self.assertEqual(self.model.edits, {0: 1000})
        self.assertEqual(
            self.card.columns[0].value_label.text(), "1000"
        )  # a edição segue visível; o mouse tem 2000

    def test_device_errors_are_clear_and_nothing_is_written(self):
        self.choose(0, 1000)
        for attribute, text in (
            ("absent", "desconectado"),
            ("permission_denied", "permissão"),
        ):
            setattr(self.fake, attribute, True)
            click(self.bar.save_button)
            self.assertIn(text, self.bar.message_label.text())
            setattr(self.fake, attribute, False)
        self.assertEqual(self.fake.writes, [])
        self.assertEqual(self.model.edits, {0: 1000})


class DeviceStateTest(WindowCase):
    load_on_start = False

    def test_absent_device_disables_editing_and_says_why(self):
        self.fake.absent = True
        self.model.reload()
        APP.processEvents()
        self.assertEqual(
            (self.window.header.status.text(), self.window.header.status.isVisible()),
            ("Mouse não encontrado", True),
        )
        self.assertIn("não encontrado", self.bar.message_label.text().lower())
        self.assertTrue(all(not c.slider.isEnabled() for c in self.card.columns))
        self.assertEqual(self.texts(), ["—"] * 5)
        self.assertFalse(self.bar.save_button.isEnabled())
        self.assertEqual(self.fake.frames, [])

    def test_missing_permission_message_points_to_the_udev_rule(self):
        self.fake.permission_denied = True
        self.model.reload()
        self.assertEqual(self.window.header.status.text(), "Sem permissão de acesso")
        self.assertIn("udev", self.bar.message_label.text())
        self.assertIn("root", self.bar.message_label.text())

    def test_invalid_response_is_reported(self):
        self.fake.bad_header_on_read = 1
        self.model.reload()
        self.assertEqual(self.window.header.status.text(), "Resposta inválida do mouse")
        self.assertIn("Resposta inválida", self.bar.message_label.text())
        self.assertFalse(self.bar.save_button.isEnabled())

    def test_reconnecting_and_reloading_recovers(self):
        self.fake.absent = True
        self.model.reload()
        self.fake.absent = False
        click(self.card.reload_button)
        self.assertFalse(self.window.header.status.isVisible())  # voltou a funcionar: o aviso some
        self.assertEqual(self.texts()[0], "800")


class DeferredTest(WindowCase):
    runner_class = DeferredRunner

    def test_controls_are_blocked_and_second_save_is_refused_while_busy(self):
        self.runner.run_all()  # termina a leitura inicial
        self.model.reload()
        self.runner.run_all()
        self.choose(0, 1000)
        self.assertTrue(self.model.save())
        self.assertTrue(self.model.busy)
        self.assertFalse(self.model.save())  # sem gravações concorrentes
        self.assertFalse(self.model.reload())
        self.assertEqual(len(self.runner.jobs), 1)
        for widget in (
            self.bar.save_button,
            self.card.reload_button,
            *[c.slider for c in self.card.columns],
        ):
            self.assertFalse(widget.isEnabled(), widget)
        self.assertEqual(self.bar.save_button.text(), "Salvando…")
        self.model.discard()  # descartar durante a gravação também é recusado
        self.assertEqual(self.model.edits, {0: 1000})
        self.runner.run_all()
        self.assertFalse(self.model.busy)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(self.bar.save_button.text(), "Salvar")

    def test_closing_is_postponed_during_a_save(self):
        self.runner.run_all()
        self.model.reload()
        self.runner.run_all()
        self.choose(0, 1000)
        self.model.save()
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.runner.run_all()
        self.assertTrue(self.window.close())


if __name__ == "__main__":
    unittest.main()
