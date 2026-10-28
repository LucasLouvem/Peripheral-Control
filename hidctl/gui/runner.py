"""Executores de tarefas do aparelho: ``QtRunner`` (thread dedicada) e ``ImmediateRunner`` (testes).

Qt: widgets só podem ser usados no thread principal e um sinal emitido de outro thread é
entregue por conexão enfileirada ao thread do receptor (docs.qt.io/qt-6/threads-qobject.html).
Por isso o trabalho roda num ``QThreadPool`` de 1 thread e o resultado volta ao thread da UI
por um sinal. Com 1 thread as tarefas nunca rodam em paralelo.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

Job = Callable[[], object]
Done = Callable[[object, BaseException | None], None]


class ImmediateRunner:
    """Executa na hora, no mesmo thread. Só para testes e capturas de tela."""

    def submit(self, job: Job, on_done: Done) -> None:
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - o chamador decide o que fazer
            on_done(None, exc)
        else:
            on_done(result, None)

    def wait(self) -> None:
        return None


class _Task(QRunnable):
    def __init__(self, runner: "QtRunner", token: int, job: Job) -> None:
        super().__init__()
        self._runner, self._token, self._job = runner, token, job

    def run(self) -> None:
        try:
            result, error = self._job(), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, exc
        self._runner._finished.emit(self._token, result, error)


class QtRunner(QObject):
    _finished = Signal(int, object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._callbacks: dict[int, Done] = {}
        self._next = 0
        self._finished.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def submit(self, job: Job, on_done: Done) -> None:
        self._next += 1
        self._callbacks[self._next] = on_done
        self._pool.start(_Task(self, self._next, job))

    def _deliver(self, token: int, result: object, error: object) -> None:
        callback = self._callbacks.pop(token)
        callback(result, error)

    def wait(self) -> None:
        self._pool.waitForDone()
