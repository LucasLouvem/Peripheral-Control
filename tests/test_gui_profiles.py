"""Perfil no topo: nome, renomear (local), trocar o perfil exibido (só leitura) e o "+"."""

import json
import unittest
from pathlib import Path

from gui_helpers import APP, WindowCase, click
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from hidctl.gui.profile_names import MAX_LENGTH, ProfileNames


def profile_levels(fake, profile):
    block = fake.block(profile)
    return [block[2 + 6 * i + 1] for i in range(5)]


class NamesTest(unittest.TestCase):
    def test_defaults_and_rename(self):
        names = ProfileNames()
        self.assertEqual([names.name(i) for i in range(5)], [f"Perfil {i}" for i in range(1, 6)])
        names.set_name(2, "  Jogos   FPS ")
        self.assertEqual((names.name(2), names.name(0)), ("Jogos FPS", "Perfil 1"))
        names.set_name(2, "   ")  # vazio volta ao padrão
        self.assertEqual(names.name(2), "Perfil 3")

    def test_invalid_names_are_rejected_and_nothing_changes(self):
        names = ProfileNames()
        names.set_name(0, "Trabalho")
        for bad in (
            "x" * (MAX_LENGTH + 1),
            "a\x00b",
            "tab\there"[:0] + "ctrl\x07",
            None,
            5,
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                names.set_name(0, bad)
        for profile in (-1, 5, True, "0"):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                names.set_name(profile, "ok")
        self.assertEqual(names.name(0), "Trabalho")
        names.set_name(0, "x" * MAX_LENGTH)  # limite exato é aceito
        self.assertEqual(len(names.name(0)), MAX_LENGTH)

    def test_persistence_roundtrip_and_tolerance_to_a_broken_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "names.json"
            self.assertTrue(ProfileNames(path).set_name(1, "Casa"))
            self.assertEqual(json.loads(path.read_text()), {"1": "Casa", "count": 1})
            self.assertEqual(ProfileNames(path).name(1), "Casa")
            path.write_text("{ isto não é json")
            self.assertEqual(ProfileNames(path).name(1), "Perfil 2")  # arquivo ruim é ignorado
            path.write_text(
                json.dumps({"1": "ok", "9": "fora", "x": "y", "2": 7, "3": "", "count": 3})
            )
            names = ProfileNames(path)
            self.assertEqual(
                [names.name(i) for i in range(5)],
                ["Perfil 1", "ok", "Perfil 3", "Perfil 4", "Perfil 5"],
            )
            self.assertEqual(names.count, 3)
            for bad in (
                0,
                6,
                True,
                "3",
                2.0,
                None,
            ):  # contagem inválida no arquivo volta ao padrão
                path.write_text(json.dumps({"count": bad}))
                self.assertEqual(ProfileNames(path).count, 1, bad)

    def test_count_defaults_to_one_validates_and_persists(self):
        import tempfile

        self.assertEqual(ProfileNames().count, 1)
        names = ProfileNames()
        for bad in (0, 6, -1, True, None, "2", 2.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                names.set_count(bad)
        self.assertEqual(names.count, 1)
        for good in (1, 5):
            names.set_count(good)
            self.assertEqual(names.count, good)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n.json"
            ProfileNames(path).set_count(4)
            self.assertEqual(ProfileNames(path).count, 4)

    def test_disk_failure_keeps_the_name_in_memory_and_reports_it(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "arquivo"
            blocker.write_text("x")
            names = ProfileNames(blocker / "names.json")
            self.assertFalse(names.set_name(0, "Volátil"))
            self.assertEqual(names.name(0), "Volátil")


class ProfileBarTest(WindowCase):
    def test_shows_only_the_profile_name_with_pencil_and_chevron(self):
        self.assertEqual(self.bar.name_label.text(), "Perfil 1")
        self.assertEqual(self.bar.rename_button.toolTip().split(" (")[0], "Renomear")
        self.assertEqual(self.bar.menu_button.toolTip(), "Trocar de perfil")
        self.assertFalse(self.bar.name_edit.isVisible())
        self.assertNotIn(
            "Perfil ativo no mouse",
            [w.text() for w in self.window.findChildren(type(self.bar.name_label))],
        )

    def test_menu_has_only_names_and_a_plus_with_no_explanatory_text(self):
        self.model.names.set_count(5)
        self.model.changed.emit()
        texts = [a.text() for a in self.menu_actions()]
        self.assertEqual(texts, ["Perfil 1", "Perfil 2", "Perfil 3", "Perfil 4", "Perfil 5", "+"])
        for text in texts:
            self.assertNotIn("ativo", text)
            self.assertNotIn("Adicionar", text)

    def menu_actions(self):
        return [a for a in self.bar.menu.actions() if not a.isSeparator()]

    def test_by_default_only_profile_1_exists_and_plus_is_enabled(self):
        self.assertEqual([a.text() for a in self.bar.profile_actions], ["Perfil 1"])
        self.assertEqual([a.isChecked() for a in self.bar.profile_actions], [True])
        self.assertEqual(self.bar.add_action.text(), "+")  # só o sinal, sem texto explicativo
        self.assertEqual(self.bar.add_action.toolTip(), "Adicionar perfil")
        self.assertTrue(self.bar.add_action.isEnabled())
        self.assertEqual(self.model.visible_profiles, 1)

    def test_plus_adds_one_profile_at_a_time_up_to_five_and_never_writes_to_the_mouse(
        self,
    ):
        before = (bytes(self.fake.memory), len(self.fake.frames))
        shown = []
        for expected in range(2, 6):
            self.bar.add_action.trigger()
            shown.append(
                (
                    len(self.bar.profile_actions),
                    self.bar.name_label.text(),
                    self.model.profile,
                )
            )
            self.assertEqual(self.model.visible_profiles, expected)
        self.assertEqual(
            shown,
            [
                (2, "Perfil 2", 1),
                (3, "Perfil 3", 2),
                (4, "Perfil 4", 3),
                (5, "Perfil 5", 4),
            ],
        )
        self.assertFalse(self.bar.add_action.isEnabled())  # máximo atingido
        self.assertEqual(self.bar.add_action.toolTip(), "Máximo de 5 perfis")
        count = len(self.bar.profile_actions)
        self.bar.add_action.trigger()  # desabilitado: nada acontece
        self.assertEqual((len(self.bar.profile_actions), self.model.profile), (count, 4))
        self.assertEqual((self.fake.writes, self.fake.f3_frames, self.fake.f1_frames), ([], [], []))
        self.assertEqual(
            bytes(self.fake.memory), before[0]
        )  # perfil ativo e níveis do mouse intactos
        self.assertEqual(self.fake.memory[0x2C], 0)

    def test_the_active_profile_of_the_mouse_is_always_listed_even_if_hidden(self):
        self.fake.memory[0x2C] = 2
        self.model.reload()
        self.assertEqual(self.model.visible_profiles, 3)
        self.assertEqual(self.bar.profile_actions[2].text(), "Perfil 3")
        self.assertEqual([a.text() for a in self.bar.profile_actions[:2]], ["Perfil 1", "Perfil 2"])
        self.assertEqual(
            self.bar.name_label.text(), "Perfil 1"
        )  # recarregar mantém o perfil que o usuário estava vendo

    def test_adding_while_busy_or_with_a_pending_edit_is_safe(self):
        self.choose(0, 1000)
        self.bar.add_action.trigger()
        self.assertEqual(
            (self.model.edits, self.fake.writes), ({}, [])
        )  # a edição foi descartada, nada gravado
        self.assertIn("descartada", self.bar.message_label.text())

    def test_rename_is_local_and_never_touches_the_mouse(self):
        frames = len(self.fake.frames)
        click(self.bar.rename_button)
        self.assertTrue(self.bar.name_edit.isVisible() and not self.bar.name_label.isVisible())
        self.assertEqual(self.bar.name_edit.text(), "Perfil 1")
        self.bar.name_edit.setText("Trabalho")
        QTest.keyClick(self.bar.name_edit, Qt.Key.Key_Return)
        APP.processEvents()
        self.assertEqual(
            (self.bar.name_label.text(), self.bar.name_label.isVisible()),
            ("Trabalho", True),
        )
        self.assertFalse(self.bar.name_edit.isVisible())
        self.assertEqual(self.bar.profile_actions[0].text(), "Trabalho")
        self.assertEqual((len(self.fake.frames), self.fake.writes), (frames, []))
        self.assertFalse(self.model.pending)  # renomear não é alteração do mouse

    def test_renaming_with_a_pending_edit_does_not_save_it(self):
        self.choose(0, 1000)
        click(self.bar.rename_button)
        self.bar.name_edit.setText("Outro")
        QTest.keyClick(self.bar.name_edit, Qt.Key.Key_Return)
        APP.processEvents()
        self.assertEqual((self.fake.writes, self.model.edits), ([], {0: 1000}))
        self.assertEqual(self.bar.name_label.text(), "Outro")

    def test_escape_cancels_the_rename(self):
        click(self.bar.rename_button)
        self.bar.name_edit.setText("Descartado")
        QTest.keyClick(self.bar.name_edit, Qt.Key.Key_Escape)
        APP.processEvents()
        self.assertEqual(self.bar.name_label.text(), "Perfil 1")
        self.assertFalse(self.bar.name_edit.isVisible())

    def test_invalid_name_keeps_the_editor_open_and_changes_nothing(self):
        click(self.bar.rename_button)
        self.bar.name_edit.setMaxLength(100)
        self.bar.name_edit.setText("x" * (MAX_LENGTH + 5))
        QTest.keyClick(self.bar.name_edit, Qt.Key.Key_Return)
        APP.processEvents()
        self.assertTrue(self.bar.name_edit.isVisible())
        self.assertEqual(self.model.profile_name(0), "Perfil 1")
        self.assertIn("inválido", self.bar.name_edit.toolTip())


class ViewingOtherProfilesTest(WindowCase):
    def setUp(self):
        super().setUp()
        self.model.names.set_count(5)  # mostra os 5 perfis para poder olhar cada um
        self.model.changed.emit()

    def test_choosing_another_profile_only_reads_and_does_not_make_it_active(self):
        before = (bytes(self.fake.memory), len(self.fake.writes))
        self.bar.profile_actions[2].trigger()
        self.assertEqual(self.bar.name_label.text(), "Perfil 3")
        self.assertEqual((self.model.profile, self.model.active_profile), (2, 0))
        self.assertEqual(
            self.texts(), ["500", "1000", "2000", "3000", "5000"]
        )  # níveis do perfil 3 (fábrica)
        self.assertEqual(self.fake.memory[0x2C], 0)  # o perfil ativo do mouse não mudou
        self.assertEqual((bytes(self.fake.memory), self.fake.writes), (before[0], []))
        self.assertEqual(self.fake.f3_frames + self.fake.f1_frames, [])
        self.assertEqual(
            [a.isChecked() for a in self.bar.profile_actions],
            [False, False, True, False, False],
        )
        self.assertEqual(self.bar.profile_actions[0].text(), "Perfil 1")

    def test_no_green_number_when_the_viewed_profile_is_not_the_active_one(self):
        self.bar.profile_actions[1].trigger()
        self.assertEqual(
            [bool(c.value_label.property("active")) for c in self.card.columns],
            [False] * 5,
        )
        self.model.set_live_active(2)  # evento do botão (vale para o perfil ativo, não para este)
        self.assertEqual(
            [bool(c.value_label.property("active")) for c in self.card.columns],
            [False] * 5,
        )
        self.bar.profile_actions[0].trigger()
        self.assertEqual(
            [bool(c.value_label.property("active")) for c in self.card.columns],
            [True, False, False, False, False],
        )

    def test_saving_in_another_profile_writes_only_that_profile(self):
        original = {p: self.fake.block(p) for p in range(5)}
        self.bar.profile_actions[3].trigger()
        self.choose(0, 800)
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [(0x262 + 2 + 1, bytes.fromhex("12 00 12 00"))])
        for profile in (0, 1, 2, 4):
            self.assertEqual(self.fake.block(profile), original[profile])
        self.assertEqual(profile_levels(self.fake, 3)[0], 0x12)
        self.assertEqual(self.fake.memory[0x2C], 0)  # continua sem trocar o perfil ativo do mouse
        self.assertEqual(
            self.bar.message_label.text(), "Salvo e confirmado por releitura (nível 1)."
        )
        self.assertEqual(self.model.profile, 3)

    def test_switching_profile_discards_the_pending_edit_without_writing_and_says_so(
        self,
    ):
        self.choose(0, 1000)
        self.bar.profile_actions[1].trigger()
        self.assertEqual(self.model.edits, {})
        self.assertEqual(self.fake.writes, [])
        self.assertIn("descartada", self.bar.message_label.text())
        self.assertEqual(self.bar.message_label.property("kind"), "warn")

    def test_external_change_of_the_active_profile_blocks_the_save_for_any_viewed_profile(
        self,
    ):
        self.bar.profile_actions[2].trigger()
        self.choose(0, 800)
        self.fake.memory[0x2C] = 4
        click(self.bar.save_button)
        self.assertEqual(self.fake.writes, [])
        self.assertIn("perfil ativo", self.bar.message_label.text())

    def test_reload_keeps_the_viewed_profile(self):
        self.bar.profile_actions[2].trigger()
        click(self.card.reload_button)
        self.assertEqual((self.model.profile, self.bar.name_label.text()), (2, "Perfil 3"))

    def test_invalid_profile_numbers_are_rejected(self):
        for bad in (-1, 5, True, None, "1", 1.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.model.select_profile(bad)
        self.assertEqual(self.model.profile, 0)


if __name__ == "__main__":
    unittest.main()
