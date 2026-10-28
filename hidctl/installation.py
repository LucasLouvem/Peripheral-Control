"""Instalação por usuário e substituição transacional da versão ativa, sem acesso ao HID."""

import ctypes.util
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

REPOSITORY = "https://github.com/LucasLouvem/Peripheral-Control.git"
RULE_NAME = "70-hidctl-04d9-fc30.rules"
RULE_TARGET = Path("/etc/udev/rules.d") / RULE_NAME


class InstallError(RuntimeError):
    """Falha que pode ser apresentada diretamente ao usuário."""


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def confirm(message: str) -> bool:
    try:
        return input(message + " ").strip().lower() == "s"
    except EOFError:
        return False


def data_home() -> Path:
    value = Path(os.environ.get("XDG_DATA_HOME", ""))
    return value if value.is_absolute() else Path.home() / ".local/share"


def install_root() -> Path:
    return data_home() / "hidctl"


def supported_system() -> bool:
    return sys.platform == "linux" and sys.version_info >= (3, 11)


def check_platform() -> bool:
    if not supported_system():
        raise InstallError("É necessário Linux com Python 3.11 ou superior.")
    arch = Path("/etc/os-release").exists() and (
        "ID=arch" in Path("/etc/os-release").read_text().splitlines()
        or 'ID="arch"' in Path("/etc/os-release").read_text().splitlines()
    )
    if not arch and not confirm(
        "O produto não foi feito para seu sistema.\nGostaria de continuar? (s/N)"
    ):
        raise InstallError("Instalação cancelada; nenhuma alteração realizada.")
    return arch


def prerequisites(arch: bool) -> None:
    tools = {"git": "git", "udevadm": "systemd", "sudo": "sudo"}
    missing = sorted({package for tool, package in tools.items() if not shutil.which(tool)})
    libraries = {
        "EGL": "libglvnd",
        "GL": "libglvnd",
        "xkbcommon": "libxkbcommon",
        "xkbcommon-x11": "libxkbcommon-x11",
        "xcb-cursor": "xcb-util-cursor",
    }
    missing = sorted(
        set(missing)
        | {
            package
            for library, package in libraries.items()
            if not ctypes.util.find_library(library)
        }
    )
    # venv needs ensurepip; do not install into Arch's system-managed Python.
    run([sys.executable, "-m", "venv", "--help"], stdout=subprocess.DEVNULL)
    if missing:
        if not arch or "sudo" in missing:
            raise InstallError("Instale os pré-requisitos e tente novamente: " + ", ".join(missing))
        print("Pré-requisitos ausentes: " + ", ".join(missing))
        if not confirm("Instalar pelo pacman? (s/N)"):
            raise InstallError("Instalação cancelada.")
        # Never refresh databases in isolation (-Sy) or upgrade the OS automatically.
        run(["sudo", "pacman", "-S", "--needed", *missing])


@contextmanager
def lock(path: Path, *, shared: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallError("Feche a ferramenta ou aguarde a operação em andamento.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def managed_root() -> Path | None:
    release = Path(sys.prefix).resolve().parent
    root = release.parent.parent
    if (root / "install.json").is_file() and (root / "current").resolve() == release:
        return root
    return None


def application_lock():
    root = managed_root()
    return lock(root / "runtime.lock", shared=True) if root else nullcontext()


def write_atomic(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".hidctl-", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        temp.chmod(mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def point_to(root: Path, name: str, target: Path) -> None:
    temp = root / (".link-" + uuid.uuid4().hex)
    try:
        temp.symlink_to(target)
        os.replace(temp, root / name)
    finally:
        temp.unlink(missing_ok=True)


def desktop_quote(path: Path) -> str:
    value = str(path).replace("%", "%%")
    if any(c in value for c in "\n\r\t="):
        raise InstallError("Caminho de instalação incompatível com o menu de aplicativos.")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    # Desktop Entry string escaping precedes Exec parsing.
    return '"' + value.replace("\\", "\\\\") + '"'


def launcher(root: Path) -> str:
    python = root / "current/venv/bin/python"
    return "#!/bin/sh\nexec " + shlex.quote(str(python)) + ' -I -m hidctl.gui "$@"\n'


def configure_user_path() -> Path:
    """Persiste o PATH no shell do usuário, preservando conteúdo e evitando duplicatas."""
    shell = Path(os.environ.get("SHELL", "/bin/sh")).name
    home = Path.home()
    if shell == "zsh":
        profile = Path(os.environ.get("ZDOTDIR") or home) / ".zshrc"
    elif shell == "bash":
        profile = home / ".bashrc"
    elif shell == "fish":
        config = Path(os.environ.get("XDG_CONFIG_HOME", ""))
        if not config.is_absolute():
            config = home / ".config"
        profile = config / "fish/conf.d/hidctl-path.fish"
    else:
        profile = home / ".profile"
    profile = profile.resolve()  # preserve symlinks used by dotfile managers
    start = "# >>> Peripheral Control: PATH >>>"
    end = "# <<< Peripheral Control: PATH <<<"
    body = (
        'fish_add_path --global --path "$HOME/.local/bin"\n'
        if shell == "fish"
        else 'case ":$PATH:" in\n'
        '    *":$HOME/.local/bin:"*) ;;\n'
        '    *) export PATH="$HOME/.local/bin:$PATH" ;;\n'
        "esac\n"
    )
    block = start + "\n" + body + end
    original = profile.read_text() if profile.exists() else ""
    if block in original:
        return profile
    if start in original or end in original:
        raise InstallError(f"Bloco PATH modificado em {profile}; revise-o antes de reinstalar.")
    mode = profile.stat().st_mode & 0o777 if profile.exists() else 0o644
    if profile.exists():
        backup = profile.with_name(profile.name + ".hidctl-backup")
        if not backup.exists():
            write_atomic(backup, original, mode)
    write_atomic(profile, original.rstrip("\n") + "\n\n" + block + "\n", mode)
    return profile


def integration_files(root: Path) -> dict[Path, tuple[str, int]]:
    if any(char in str(root) for char in "\n\r\t\\"):
        raise InstallError("Caminho de dados incompatível com o menu de aplicativos.")
    command = Path.home() / ".local/bin/hidctl-gui"
    desktop = data_home() / "applications/io.github.LucasLouvem.PeripheralControl.desktop"
    entry = (
        "[Desktop Entry]\nType=Application\nName=Peripheral Control\n"
        "Comment=Configure DPI e iluminação de periféricos\n"
        f"Exec={desktop_quote(command)}\n"
        f"Icon={root / 'current/source/packaging/peripheral-control.svg'}\n"
        "Terminal=false\nCategories=Settings;HardwareSettings;\nStartupNotify=true\n"
    )
    return {command: (launcher(root), 0o755), desktop: (entry, 0o644)}


def validate_candidate(release: Path) -> None:
    python = release / "venv/bin/python"
    run([python, "-I", "-m", "pip", "check"])
    run(
        [
            python,
            "-I",
            "-c",
            "from hidctl.installation import maintenance, application_lock; "
            "from hidctl.gui.app import build_parser; "
            "assert build_parser().parse_args(['--update']).update; "
            "assert build_parser().parse_args(['--uninstall']).uninstall",
        ],
        timeout=30,
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    with tempfile.TemporaryDirectory(prefix="hidctl-check-") as directory:
        run(
            [
                python,
                "-I",
                "-m",
                "hidctl.gui",
                "--demo",
                "--screenshot",
                Path(directory) / "check.png",
            ],
            env=env,
            timeout=90,
            cwd=directory,
        )


def build_release(root: Path, source: Path | None) -> Path:
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    release = releases / uuid.uuid4().hex
    release.mkdir()
    try:
        tree = release / "source"
        if source is None:
            run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    "main",
                    "--single-branch",
                    REPOSITORY,
                    tree,
                ],
                timeout=180,
            )
        else:
            # Explicit allowlist: never copy local credentials, venvs or agent files.
            tree.mkdir()
            for name in ("hidctl", "packaging"):
                shutil.copytree(
                    source / name,
                    tree / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                shutil.copy2(source / name, tree / name)
        if source is None:
            revision = run(
                ["git", "-C", tree, "rev-parse", "HEAD"], capture_output=True, text=True
            ).stdout.strip()
        else:
            revision = "local"
        (release / "revision").write_text(revision + "\n")
        # venvs are created at their final path; moving them breaks console-script shebangs.
        run(["/usr/bin/python3", "-m", "venv", release / "venv"])
        run(
            [release / "venv/bin/python", "-I", "-m", "pip", "install", str(tree) + "[gui]"],
            timeout=900,
        )
        validate_candidate(release)
        return release
    except BaseException:
        shutil.rmtree(release)
        raise


def configure_udev(release: Path) -> None:
    rule = release / "source/packaging/udev" / RULE_NAME
    if RULE_TARGET.exists() and RULE_TARGET.read_bytes() == rule.read_bytes():
        return
    print("Configurando acesso ao mouse; sudo será usado apenas para a regra udev.")
    run(["sudo", "install", "-m", "0644", rule, RULE_TARGET])
    run(["sudo", "udevadm", "control", "--reload"])
    run(["sudo", "udevadm", "trigger", "--action=change", "--subsystem-match=hidraw"])


def activate(root: Path, release: Path) -> None:
    files = integration_files(root)
    old_release = (root / "current").resolve() if (root / "current").is_symlink() else None
    backups = {p: (p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None for p in files}
    manifest = root / "install.json"
    old_manifest = manifest.read_text() if manifest.exists() else None
    try:
        for path, (content, mode) in files.items():
            write_atomic(path, content, mode)
        if old_release:
            point_to(root, "previous", old_release)
        write_atomic(root / "install.json", json.dumps({"format": 1, "repository": REPOSITORY}))
        point_to(root, "current", release)
    except BaseException:
        for path, backup in backups.items():
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                write_atomic(path, backup[0].decode(), backup[1])
        if old_manifest is None:
            manifest.unlink(missing_ok=True)
        else:
            write_atomic(manifest, old_manifest)
        raise


def deploy(root: Path, source: Path | None) -> None:
    from ._paths import state_dir

    root.mkdir(parents=True, exist_ok=True)
    with lock(root / "runtime.lock"), lock(state_dir() / "device.lock"):
        if not (root / "install.json").exists():
            for path in integration_files(root):
                if path.exists() or path.is_symlink():
                    raise InstallError(f"Não vou sobrescrever um arquivo existente: {path}")
        release = build_release(root, source)
        try:
            configure_udev(release)
            activate(root, release)
        except BaseException:
            shutil.rmtree(release)
            raise
    print("Peripheral Control instalado. Abra pelo menu de aplicativos ou use hidctl-gui.")
    try:
        profile = configure_user_path()
        print(f"PATH configurado em {profile}. Abra um novo terminal para usar hidctl-gui.")
    except (OSError, InstallError) as exc:
        print(f"Aplicativo instalado, mas não foi possível configurar o PATH: {exc}")
        print("Use ~/.local/bin/hidctl-gui até ajustar a configuração do shell.")


def uninstall(root: Path, *, purge: bool = False) -> None:
    from ._paths import state_dir

    state = state_dir()
    if purge:
        if state.is_symlink() or state.name != "hidctl":
            raise InstallError("Diretório de dados inesperado; remoção completa recusada.")
        if root.resolve().is_relative_to(state.resolve()) or state.resolve().is_relative_to(
            root.resolve()
        ):
            raise InstallError("Instalação e dados se sobrepõem; revise os diretórios XDG.")
        question = f"Desinstalar e APAGAR DEFINITIVAMENTE todas as preferências e backups em {state}? (s/N)"
    else:
        question = "Desinstalar Peripheral Control, preservando preferências e backups? (s/N)"
    if not confirm(question):
        return
    with lock(root / "runtime.lock"), lock(state / "device.lock"):
        files = integration_files(root)
        rule = root / "current/source/packaging/udev" / RULE_NAME
        if RULE_TARGET.exists() and rule.exists() and RULE_TARGET.read_bytes() == rule.read_bytes():
            if purge or confirm("Remover também a regra de acesso ao mouse (sudo)? (s/N)"):
                run(["sudo", "rm", "--", RULE_TARGET])
                run(["sudo", "udevadm", "control", "--reload"])
                run(["sudo", "udevadm", "trigger", "--action=change", "--subsystem-match=hidraw"])
        for path, (content, _) in files.items():
            if path.is_file() and path.read_text() == content:
                path.unlink()
        shutil.rmtree(root)
        if purge:
            shutil.rmtree(state)
    print(
        "Desinstalado. Preferências e backups foram " + ("apagados." if purge else "preservados.")
    )


def maintenance(action: str, *, purge: bool = False) -> int:
    try:
        if os.geteuid() == 0:
            raise InstallError("Execute como usuário comum, sem sudo.")
        root = managed_root()
        if root is None:
            raise InstallError(
                "Este ambiente não é uma instalação gerenciada. Execute ./scripts/install.sh."
            )
        if action == "uninstall":
            uninstall(root, purge=purge)
        else:
            arch = check_platform()
            prerequisites(arch)
            deploy(root, None)
        return 0
    except (InstallError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print(f"Não foi possível concluir: {exc}", file=sys.stderr)
        return 1


def install_main(source: Path) -> int:
    try:
        if os.geteuid() == 0:
            raise InstallError("Execute ./scripts/install.sh como usuário comum, sem sudo.")
        arch = check_platform()
        prerequisites(arch)
        deploy(install_root(), source)
        if confirm("Abrir Peripheral Control agora? (s/N)"):
            subprocess.Popen([str(Path.home() / ".local/bin/hidctl-gui")], start_new_session=True)
        return 0
    except (InstallError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print(f"Instalação não concluída: {exc}", file=sys.stderr)
        return 1
