# Peripheral Control

Aplicativo desktop para configurar periféricos USB HID no Linux, com interface em Python e PySide6 e comunicação própria com o dispositivo. O pacote e a CLI se chamam **hidctl**.

![Peripheral Control em execução](docs/images/peripheral-control.png)

_Captura da aplicação em execução, sem acesso ao hardware._

## Funcionalidades

- Edição dos cinco níveis de DPI por perfil e indicação ao vivo do nível ativo pelo botão físico.
- Cor estática com seletor visual, hexadecimal, canais RGB e cores recentes locais.
- Onda multicolorida com velocidade ajustável.
- Visualização dos cinco perfis e nomes personalizados salvos localmente.
- Edição local: somente **Salvar** grava, com backup e confirmação por releitura.
- Modo de demonstração sem acesso a dispositivos físicos.

## Compatibilidade

Validado no **Cobra M711 do kit S118**, USB `04d9:fc30`, revisão `0x0112`. Outros modelos ou revisões não têm suporte confirmado.

DPI disponível: **500, 800, 1000, 1200, 2000, 2400, 3000, 3600 e 5000**. São valores nominais, sem medição da precisão física. A faixa anunciada de 10.000 DPI não está liberada.

A onda é multicolorida e ignora a cor selecionada. Não há ativação de perfis no hardware ou edição de brilho. Macros, remapeamento, polling rate e teclado ainda não estão implementados.

## Instalação

Requisitos: Linux, Python 3.11 ou superior e ambiente gráfico compatível com Qt/PySide6.

```bash
git clone https://github.com/LucasLouvem/Peripheral-Control.git
cd Peripheral-Control
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[gui]'
hidctl-gui
```

Para explorar sem hardware:

```bash
hidctl-gui --demo
```

### Permissão de acesso ao mouse

Execute o aplicativo como usuário comum. Instale a regra específica para conceder acesso à interface de configuração:

```bash
sudo install -m 0644 packaging/udev/70-hidctl-04d9-fc30.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --action=change --subsystem-match=hidraw
```

Reconecte o mouse se necessário. A regra utiliza `uaccess`, para o usuário da sessão local ativa.

## Uso

1. Abra o aplicativo para carregar as configurações do mouse.
2. Ajuste o DPI ou a iluminação. Confirmar uma cor no modal apenas prepara a edição.
3. Clique em **Salvar** para gravar e confirmar por releitura.

O salvamento não é atômico: uma falha pode deixar alterações parciais. A interface informa falhas e estados não confirmados. A releitura confirma os dados; confira o efeito luminoso visualmente.

Inspeção pela CLI:

```bash
python -m hidctl.cli dpi-inspect
python -m hidctl.cli dpi-read --trace
```

Preferências e backups ficam em `~/.local/state/hidctl/`. O comando opcional `hidctl devices` requer o extra `hid`: `python -m pip install -e '.[hid]'`.

## Desenvolvimento e contribuições

```bash
python -m pip install -e '.[gui,dev]'
ruff check .
ruff format --check .
QT_QPA_PLATFORM=offscreen pytest
npx prettier@3.8.1 --check '**/*.md' '*.json'
```

Python é formatado com Ruff; Markdown e JSON, com Prettier. Os [testes físicos](tests_physical/README.md) ficam separados da suíte automática.

Contribuições são bem-vindas. Consulte as [diretrizes e referências dos dispositivos](docs/README.md). Novos modelos precisam de identificação e evidências próprias de compatibilidade.

## Licença

[MIT](LICENSE). Projeto independente, sem afiliação aos fabricantes citados.
