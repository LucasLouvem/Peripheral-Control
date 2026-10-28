#!/usr/bin/env python3
"""Passos físicos de DPI, um por vez. Uso: HIDCTL_PHYSICAL=1 python tests_physical/physical.py <passo> ...

Passos (leitura): ``open`` (abre o nó, sem enviar), ``probe`` (GET_FEATURE ID 2 sem sessão),
``read`` (sessão, perfil ativo e blocos). Passos (escrita): ``write`` e ``restore``, que
exigem ``--i-confirm-write``. Nada aqui varre comandos ou valores.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hidctl.core import discovery
from hidctl.core.errors import HidctlError
from hidctl.core.transport import HidrawTransport, LoggingTransport
from hidctl.devices.fc30_mouse import (
    dpi,
    frames,
    lighting,
    values,
)
from hidctl.devices.fc30_mouse.dpi import CodeEntry
from hidctl.devices.fc30_mouse.dpi_service import DpiController, open_mouse
from hidctl.devices.fc30_mouse.session import MouseSession
from hidctl.devices.fc30_mouse.spec import SPEC

STATE = Path.home() / ".local" / "state" / "hidctl"
LOG_FILE = STATE / "physical-logs" / f"{datetime.now():%Y%m%d-%H%M%S}.log"

# Códigos com evidência. 1000 → 0x16/0: observado NO APARELHO nos perfis 1-4 (nível 1, leitura de
# 2026-10-28), e igual nas tabelas de duas fontes externas independentes (E2 e E5).
VERIFIED_CODES: dict[int, CodeEntry] = {
    1000: CodeEntry(1000, 0x16, 0, "device(p1-4 n1)+E2+E5"),
    # 0x73/0 está nos 25 registros lidos (nível 4); "5000" é o rótulo da fonte E2 (a E5 diz 5100).
    5000: CodeEntry(5000, 0x73, 0, "device(p0-4 n4)+E2"),
}


def log(line: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamped = f"{datetime.now():%H:%M:%S.%f}  {line}"
    print(stamped)
    with LOG_FILE.open("a") as handle:
        handle.write(stamped + "\n")


def describe(block: dpi.DpiBlock) -> None:
    log(f"perfil {block.profile} @ {block.address:#06x}: {block.raw.hex(' ')}")
    log(f"  nível ativo = {block.active_level}")
    for i, lv in enumerate(block.levels):
        log(
            f"  nível {i}: en={lv.enabled} x={lv.x_code:#04x}/{lv.x_flag} y={lv.y_code:#04x}/{lv.y_flag} pad={lv.pad:#04x} ≈{lv.estimate()}"
        )


def diff(before: bytes, after: bytes) -> list[str]:
    return [
        f"+{i:02d}: {a:02x} -> {b:02x}" for i, (a, b) in enumerate(zip(before, after)) if a != b
    ]


def open_transport() -> tuple[discovery.HidInterface, HidrawTransport]:
    found = discovery.find(SPEC)
    log(
        f"descoberto: {found.name} {found.node} bcd=0x{found.bcd_device:04x} if={found.interface_number}"
    )
    return found, HidrawTransport(found.node)


def step_open(_args: argparse.Namespace) -> None:
    """Passo 2: abre o nó e fecha. Não envia nenhum report."""
    _found, transport = open_transport()
    log("nó aberto em O_RDWR; nenhum report enviado")
    transport.close()


def step_probe(_args: argparse.Namespace) -> None:
    """H-R1: um único GET_FEATURE do ID 2 (16 bytes), sem sessão. Somente observa."""
    _found, transport = open_transport()
    try:
        raw = LoggingTransport(transport, log).get_feature(frames.REPORT_ID, 16)
        log(f"resposta bruta ({len(raw)} bytes): {raw.hex(' ')}")
    finally:
        transport.close()


def step_read(args: argparse.Namespace) -> None:
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            active = session.read_active_profile()
            log(f"perfil ativo = {active}")
            profiles = (
                range(len(dpi.PROFILE_BASES))
                if args.profile == "all"
                else [active if args.profile == "active" else int(args.profile)]
            )
            for number in profiles:
                describe(session.read_dpi_block(number))
    finally:
        transport.close()


def step_write(args: argparse.Namespace) -> None:
    """Um único byte de um nível; releitura antes e depois do commit (``--commit``)."""
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            before = session.read_dpi_block(args.profile)
            describe(before)
            plan = dpi.plan_level_change(before, args.level, args.dpi, VERIFIED_CODES)
            log(
                f"plano: endereço {plan.address:#06x} {plan.old.hex()} -> {plan.new.hex()} (DPI nominal {plan.nominal})"
            )
            log(f"backup: {session.apply_plan(plan, STATE / 'backups')}")
            mid = session.read_dpi_block(args.profile)
            log(
                "após F3 (sem F1): "
                + (", ".join(diff(before.raw, mid.raw)) or "sem mudança na memória")
            )
            start = plan.address - before.address
            expected = before.raw[:start] + plan.new + before.raw[start + len(plan.new) :]
            if mid.raw not in (before.raw, expected):
                log(
                    "ABORTADO: a releitura difere do esperado e do original; F1 NÃO enviado. Analise antes de qualquer outra escrita."
                )
                return
            if args.commit:
                session.commit_dpi()
                log("F1 02 02 enviado")
                after = session.read_dpi_block(args.profile)
                log("após F1: " + (", ".join(diff(before.raw, after.raw)) or "sem mudança"))
    finally:
        transport.close()


def step_restore(args: argparse.Namespace) -> None:
    backup = json.loads(Path(args.backup).read_text())
    profile, level = int(backup["profile"]), int(backup["planned"]["level"])
    original = int(backup["planned"]["old"].split()[0], 16)
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            current = session.read_dpi_block(profile)
            describe(current)
            plan = dpi.plan_code_restore(current, level, original)
            log(f"restauração: {plan.address:#06x} {plan.old.hex()} -> {plan.new.hex()}")
            session.apply_plan(plan, STATE / "backups")
            session.commit_dpi()
            after = session.read_dpi_block(profile)
            describe(after)
            original_block = bytes.fromhex(backup["block_hex"])
            log(
                "diferença para o bloco original: "
                + (", ".join(diff(original_block, after.raw)) or "NENHUMA (restaurado)")
            )
    finally:
        transport.close()


LIGHT_BASE, LIGHT_STRIDE = (
    0x449,
    8,
)  # [FONTE] OpenRGB + mouse_m908; confirmado só pelos passos light-*


def step_light_read(_args: argparse.Namespace) -> None:
    """Iluminação: SOMENTE LEITURA. 5 janelas de 8 bytes (0x449 + 8·perfil): R G B modo1 vel modo2 brilho ?."""
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            log(f"perfil ativo = {session.read_active_profile()}")
            for profile in range(5):
                address = LIGHT_BASE + LIGHT_STRIDE * profile
                raw = session.read_memory(address, 8)
                log(
                    f"luz perfil {profile} @ {address:#06x}: {raw.hex(' ')}  rgb={raw[0]:02x}{raw[1]:02x}{raw[2]:02x} modo={raw[3]:02x}/{raw[5]:02x} vel={raw[4]} brilho={raw[6]}"
                )
    finally:
        transport.close()


def describe_light(light: lighting.Lighting) -> None:
    log(
        f"luz perfil {light.profile} @ {light.address:#06x}: {light.raw.hex(' ')} rgb={bytes(light.rgb).hex()} efeito={light.effect.value} vel={light.speed} brilho={light.brightness}"
    )


def step_light_write(args: argparse.Namespace) -> None:
    """Grava UMA edição de iluminação (backup antes); ``--apply`` envia F1 02 04 depois. Relê em cada etapa."""
    rgb = bytes.fromhex(args.rgb)
    edit = lighting.LightingEdit(
        tuple(rgb),
        lighting.Effect(args.effect),
        args.speed if args.effect == "wave" else None,
    )
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            before = session.read_lighting(args.profile)
            describe_light(before)
            plan = lighting.plan_lighting_change(before, edit)
            if plan is None:
                log("nada a gravar: o registro já está assim")
                if args.apply:
                    session.commit_lighting()
                    log("F1 02 04 enviado (sem escrita)")
                    describe_light(session.read_lighting(args.profile))
                return
            log(f"plano: {plan.address:#06x} {plan.old.hex(' ')} -> {plan.new.hex(' ')}")
            log(f"backup: {session.apply_lighting_plan(plan, STATE / 'backups')}")
            mid = session.read_lighting(args.profile)
            describe_light(mid)
            start = plan.address - before.address
            expected = before.raw[:start] + plan.new + before.raw[start + len(plan.new) :]
            log(
                "releitura após F3: "
                + (
                    "IGUAL ao esperado"
                    if mid.raw == expected
                    else f"DIVERGE (esperado {expected.hex(' ')})"
                )
            )
            if mid.raw != expected:
                log("ABORTADO: F1 NÃO enviado.")
                return
            if args.apply:
                session.commit_lighting()
                log("F1 02 04 enviado")
                describe_light(session.read_lighting(args.profile))
    finally:
        transport.close()


def step_light_restore(args: argparse.Namespace) -> None:
    backup = json.loads(Path(args.backup).read_text())
    original = bytes.fromhex(backup["window_hex"])
    profile = int(backup["profile"])
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            current = session.read_lighting(profile)
            describe_light(current)
            changed = [i for i in range(lighting.RECORD_SIZE) if current.raw[i] != original[i]]
            if changed:
                first, last = changed[0], changed[-1]
                plan = lighting.LightingPlan(
                    profile,
                    current.address + first,
                    current.raw[first : last + 1],
                    original[first : last + 1],
                    current.raw,
                    current.token,
                )
                log(f"restauração: {plan.address:#06x} {plan.old.hex(' ')} -> {plan.new.hex(' ')}")
                session.apply_lighting_plan(plan, STATE / "backups")
            session.commit_lighting()
            after = session.read_lighting(profile)
            describe_light(after)
            log(
                "diferença para a janela original: "
                + (", ".join(diff(original, after.raw)) or "NENHUMA (restaurado)")
            )
    finally:
        transport.close()


def step_light_save_test(args: argparse.Namespace) -> None:
    """Salva uma cor pelo serviço real (o mesmo caminho do botão Salvar) e mostra o resultado. Restaure com light-restore."""
    controller = DpiController(lambda: open_mouse(log), STATE / "backups", STATE / "device.lock")
    loaded = controller.load()
    log(f"carregado: perfil {loaded.profile} luz {loaded.lighting.raw.hex(' ')}")
    outcome = controller.save(loaded, {}, lighting.LightingEdit(tuple(bytes.fromhex(args.rgb))))
    log(f"resultado: {outcome.kind.value}: {outcome.message}")
    if outcome.snapshot:
        log(
            f"luz depois: {outcome.snapshot.lighting.raw.hex(' ')}  dpi: {outcome.snapshot.raw.hex(' ')}"
        )


def read_all_blocks(session: MouseSession) -> dict[int, bytes]:
    return {p: session.read_dpi_block(p).raw for p in range(len(dpi.PROFILE_BASES))}


def same_except_active(a: bytes, b: bytes) -> bool:
    """Compara blocos ignorando o byte 0 (nível ativo, alterado pelo botão do mouse)."""
    return a[1:] == b[1:]


def step_watch_active(args: argparse.Namespace) -> None:
    """Somente leitura: imprime cada mudança do byte 0 do perfil ativo durante N segundos."""
    import time

    _found, transport = open_transport()
    last: int | None = None
    try:
        end = time.monotonic() + args.seconds
        log(
            f"observando por {args.seconds}s: aperte o botão de DPI do mouse e diga o que o LED/indicador mostra"
        )
        while time.monotonic() < end:
            with MouseSession(transport) as session:
                profile = session.read_active_profile()
                value = session.read_memory(dpi.PROFILE_BASES[profile], 1)[0]
            if value != last:
                log(
                    f"perfil {profile}: byte 0 (nível ativo) = {value}"
                    + (" [inicial]" if last is None else f" (antes: {last})")
                )
                last = value
            time.sleep(args.interval)
    finally:
        transport.close()
    log("fim da observação")


def step_verify_values(args: argparse.Namespace) -> None:
    """Grava, em um nível NÃO ativo, cada valor da lista explícita; relê; restaura; confere."""
    wanted = [int(v) for v in args.values.split(",")]
    _found, transport = open_transport()
    try:
        with MouseSession(LoggingTransport(transport, log)) as session:
            before_all = read_all_blocks(session)
            block = session.read_dpi_block(args.profile)
            original_code = block.levels[args.level].x_code
            log(
                f"nível {args.level}: código original {original_code:#04x}; ativo no mouse = nível {block.active_level}"
            )
            if block.active_level == args.level:
                log("ABORTADO: o nível escolhido é o ativo; escolha outro para não mudar o cursor.")
                return
        for nominal in wanted:
            entry = values.by_nominal(nominal)
            if entry is None:
                log(f"ABORTADO: {nominal} não está na tabela")
                return
            with MouseSession(LoggingTransport(transport, log)) as session:
                block = session.read_dpi_block(args.profile)
                plan = dpi.plan_level_change(
                    block,
                    args.level,
                    nominal,
                    {nominal: CodeEntry(nominal, entry.code, entry.flag, "verify")},
                )
                log(
                    f"== {nominal} -> código {entry.code:#04x}: {plan.old.hex(' ')} -> {plan.new.hex(' ')}"
                )
                session.apply_plan(plan, STATE / "backups")
                mid = session.read_dpi_block(args.profile)
                start = plan.address - block.address
                expected = block.raw[:start] + plan.new + block.raw[start + 4 :]
                if not same_except_active(mid.raw, expected):
                    log(f"ABORTADO após F3: esperado {expected.hex(' ')} obtido {mid.raw.hex(' ')}")
                    return
                session.commit_dpi()
                after = session.read_dpi_block(args.profile)
                if not same_except_active(after.raw, expected):
                    log(
                        f"ABORTADO após F1: esperado {expected.hex(' ')} obtido {after.raw.hex(' ')}"
                    )
                    return
                log(f"   OK: gravado e relido byte a byte ({nominal})")
        with MouseSession(LoggingTransport(transport, log)) as session:
            block = session.read_dpi_block(args.profile)
            plan = dpi.plan_code_restore(block, args.level, original_code)
            log(f"== restauração: {plan.old.hex(' ')} -> {plan.new.hex(' ')}")
            session.apply_plan(plan, STATE / "backups")
            session.commit_dpi()
            after_all = read_all_blocks(session)
        changed = {
            p: diff(before_all[p], after_all[p])
            for p in before_all
            if not same_except_active(before_all[p], after_all[p])
        }
        log(
            "diferença final para o estado original (ignorando byte 0): "
            + (str(changed) if changed else "NENHUMA")
        )
    finally:
        transport.close()


def step_save_test(args: argparse.Namespace) -> None:
    """Fluxo real de salvar (serviço) com 2 níveis; depois restaura pelo mesmo serviço."""
    controller = DpiController(lambda: open_mouse(log), STATE / "backups", STATE / "device.lock")
    original = controller.load()
    log(
        "original: "
        + ", ".join(
            f"n{level.index + 1}={level.nominal}({level.code:#04x})" for level in original.levels
        )
        + f" ativo=n{original.active_level + 1}"
    )
    edits = {int(k): int(v) for k, v in (item.split(":") for item in args.edits.split(","))}
    if original.active_level in edits:
        log("ABORTADO: um dos níveis é o ativo")
        return
    outcome = controller.save(original, edits)
    log(f"salvar -> {outcome.kind.value}: {outcome.message}")
    if not outcome.ok:
        log("ABORTADO: sem restauração automática; analise antes de continuar")
        return
    back = {i: original.levels[i].nominal for i in edits}
    restored = controller.save(outcome.snapshot, back)
    log(f"restaurar -> {restored.kind.value}: {restored.message}")
    final = controller.load()
    same = same_except_active(original.raw, final.raw)
    log("estado final igual ao original (ignorando byte 0): " + ("SIM" if same else "NÃO"))


def step_listen_events(args: argparse.Namespace) -> None:
    """Somente escuta: Input Reports do hidraw (sem enviar nada) + o byte 0 lido a cada ~1 s."""
    import select
    import time

    found = discovery.find(SPEC)
    log(
        f"descoberto: {found.name} bcd=0x{found.bcd_device:04x}; escutando {args.seconds}s - aperte o botão de DPI devagar"
    )
    listener = os.open(found.node, os.O_RDONLY | os.O_NONBLOCK)
    transport = HidrawTransport(found.node)
    last: int | None = None
    next_poll = 0.0
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end:
            ready, _, _ = select.select([listener], [], [], 0.2)
            if ready:
                try:
                    data = os.read(listener, 64)
                except BlockingIOError:
                    data = b""
                if data:
                    log(f"EVENTO (input report) {data.hex(' ')}")
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic() + 1.0
                with MouseSession(transport) as session:
                    profile = session.read_active_profile()
                    value = session.read_memory(dpi.PROFILE_BASES[profile], 1)[0]
                if value != last:
                    log(
                        f"byte 0 do bloco do perfil {profile} = {value}"
                        + ("" if last is None else f" (antes {last})")
                    )
                    last = value
    finally:
        transport.close()
        os.close(listener)
    log("fim da escuta")


def main() -> int:
    if os.environ.get("HIDCTL_PHYSICAL") != "1":
        print("Defina HIDCTL_PHYSICAL=1 para executar testes físicos.")
        return 2
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="step", required=True)
    sub.add_parser("open")
    sub.add_parser("probe")
    sub.add_parser("light-read")
    lw = sub.add_parser("light-write")
    lw.add_argument("--profile", type=int, required=True)
    lw.add_argument("--effect", choices=["static", "wave"], required=True)
    lw.add_argument("--rgb", required=True, help="RRGGBB em hexadecimal")
    lw.add_argument("--speed", type=int, default=None)
    lw.add_argument("--apply", action="store_true", help="envia F1 02 04 depois de gravar")
    lw.add_argument("--i-confirm-write", action="store_true", required=True)
    ls = sub.add_parser("light-save-test")
    ls.add_argument("--rgb", required=True)
    ls.add_argument("--i-confirm-write", action="store_true", required=True)
    lr = sub.add_parser("light-restore")
    lr.add_argument("--backup", required=True)
    lr.add_argument("--i-confirm-write", action="store_true", required=True)
    read = sub.add_parser("read")
    read.add_argument(
        "--profile",
        default="active",
        choices=["active", "all", "0", "1", "2", "3", "4"],
    )
    write = sub.add_parser("write")
    write.add_argument("--profile", type=int, required=True)
    write.add_argument("--level", type=int, required=True)
    write.add_argument("--dpi", type=int, required=True)
    write.add_argument("--commit", action="store_true")
    write.add_argument("--i-confirm-write", action="store_true", required=True)
    watch = sub.add_parser("watch-active")
    watch.add_argument("--seconds", type=int, default=25)
    watch.add_argument("--interval", type=float, default=1.0)
    listen = sub.add_parser("listen-events")
    listen.add_argument("--seconds", type=int, default=45)
    verify = sub.add_parser("verify-values")
    verify.add_argument("--profile", type=int, required=True)
    verify.add_argument("--level", type=int, required=True)
    verify.add_argument("--values", required=True)
    verify.add_argument("--i-confirm-write", action="store_true", required=True)
    save_test = sub.add_parser("save-test")
    save_test.add_argument("--edits", required=True, help="nível:dpi,nível:dpi (níveis 0-4)")
    save_test.add_argument("--i-confirm-write", action="store_true", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--i-confirm-write", action="store_true", required=True)
    args = parser.parse_args()
    try:
        {
            "open": step_open,
            "probe": step_probe,
            "light-read": step_light_read,
            "light-write": step_light_write,
            "light-restore": step_light_restore,
            "light-save-test": step_light_save_test,
            "read": step_read,
            "write": step_write,
            "restore": step_restore,
            "watch-active": step_watch_active,
            "listen-events": step_listen_events,
            "verify-values": step_verify_values,
            "save-test": step_save_test,
        }[args.step](args)
    except HidctlError as exc:
        log(f"ERRO: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
