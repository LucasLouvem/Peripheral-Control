PYTHON ?= python3
SHOT   ?= captura.png
SIZE   ?= 1586x940

.PHONY: run demo install test screenshot help

# Alvo padrão: abre a interface com o mouse real (lê ao abrir; só grava ao clicar em Salvar).
run:
	$(PYTHON) -m hidctl.gui

# Interface com um mouse SIMULADO (nenhum dispositivo é acessado).
demo:
	$(PYTHON) -m hidctl.gui --demo

install:
	$(PYTHON) -m pip install -e '.[gui]'

test:
	$(PYTHON) -m unittest discover -s tests

# Salva uma captura sem abrir janela: make screenshot SHOT=ui.png SIZE=1366x768
screenshot:
	$(PYTHON) -m hidctl.gui --demo --screenshot $(SHOT) --size $(SIZE)

help:
	@echo "make run         abre a interface com o mouse real (padrão)"
	@echo "make demo        abre a interface com um mouse simulado"
	@echo "make install     instala o projeto com o extra 'gui' (PySide6)"
	@echo "make test        roda os testes"
	@echo "make screenshot  salva uma captura (SHOT=arquivo.png SIZE=LARGURAxALTURA)"
