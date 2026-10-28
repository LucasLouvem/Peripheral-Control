# Instalação, atualização e remoção

## Instalação por usuário

Execute `./scripts/install.sh` no repositório extraído ou clonado. Python 3.11 ou superior é necessário; no Arch, o ponto de entrada oferece a instalação de Python quando ausente. Git, sudo, udev e bibliotecas de execução do Qt são verificados. No Arch, dependências ausentes podem ser instaladas por pacman, com confirmação. O instalador não atualiza bancos de pacotes isoladamente nem faz atualização geral do sistema.

Fora do Arch, o aviso é:

> O produto não foi feito para seu sistema.
> Gostaria de continuar? (s/N)

Enter, N ou entrada encerrada cancela. S permite prosseguir, sem executar pacman em outra distribuição. Pré-requisitos ausentes precisam ser instalados pelo usuário nesse caso.

O ambiente Python e suas dependências ficam isolados do Python do sistema. Não execute o script inteiro como root. Sudo é usado somente para pacotes ausentes e instalação ou remoção da regra udev específica. O projeto não solicita nem armazena senhas.

## Arquivos e integração

- Instalação: `$XDG_DATA_HOME/hidctl`, por padrão `~/.local/share/hidctl`.
- Versões: subdiretórios de `releases/`, cada um com fonte e ambiente virtual.
- `current`: versão ativa. `previous`: versão anterior à última ativação.
- Comando: `~/.local/bin/hidctl-gui`.
- Menu: `$XDG_DATA_HOME/applications/io.github.LucasLouvem.PeripheralControl.desktop`.
- Ícone próprio: SVG mantido na fonte da versão instalada.
- Preferências e backups: `~/.local/state/hidctl/`, respeitando `XDG_STATE_HOME` do aplicativo.
- Acesso ao mouse: `/etc/udev/rules.d/70-hidctl-04d9-fc30.rules`.

A instalação usa uma cópia independente; a pasta original pode ser movida ou removida. O menu utiliza caminho absoluto e não depende de PATH. O instalador inclui `~/.local/bin` no PATH de novos terminais: Zsh (`$ZDOTDIR/.zshrc`, ou `~/.zshrc`), Bash (`~/.bashrc`), Fish (`conf.d/hidctl-path.fish`) e outros shells de sintaxe POSIX (`~/.profile`, após novo login). O arquivo existente é preservado, com backup de sufixo `.hidctl-backup` antes da primeira edição. Reinstalar não duplica o bloco. O terminal que executou a instalação não pode ter seu ambiente alterado pelo processo filho: abra um novo terminal. Na desinstalação, o PATH é mantido, pois `~/.local/bin` também serve a outros programas.

A regra concede acesso à interface e revisão suportadas para o usuário de uma sessão local ativa. Pode ser necessário reconectar o mouse. A instalação não grava configurações no dispositivo.

## Atualização

Com a ferramenta fechada, execute `hidctl-gui --update`, ou seu caminho completo. Somente instalações gerenciadas aceitam essa operação.

O atualizador obtém a main oficial por HTTPS, em uma cópia nova, sem tocar em checkouts de desenvolvimento. A revisão baixada fica registrada na versão. O ambiente é criado em seu caminho definitivo, pois ambientes virtuais não são portáveis.

Antes da ativação, valida dependências com pip e renderiza a interface no modo simulado, sem acessar hardware. Depois prepara a integração e troca o apontamento da versão ativa. Falhas de preparação mantêm a versão ativa; falhas de integração restauram seus arquivos anteriores. Preferências e backups não são substituídos.

A ferramenta aberta ou uma operação de dispositivo em andamento bloqueia a atualização. Instalação, atualização e remoção são serializadas. A regra udev só exige sudo se seu conteúdo precisar mudar; alterações do sistema já autorizadas não são revertidas automaticamente se uma etapa posterior falhar.

As versões anteriores permanecem no diretório de instalação; a desinstalação remove todas. Não há verificação automática em segundo plano, assinatura de releases nem garantia de que toda alteração futura da main esteja livre de defeitos. O teste de instalação é de integridade e abertura, não substitui a suíte do projeto.

## Remoção

Execute `hidctl-gui --uninstall` e confirme. A operação remove versões e integração do usuário, preservando preferências e backups. Oferece remover a regra udev via sudo se ela ainda corresponder à instalada. Não remove pacotes do sistema e preserva lançadores externos modificados pelo usuário.

Para remover também os dados pessoais, execute `hidctl-gui --uninstall A`. A confirmação informa o diretório de dados que será apagado. Após confirmar, remove preferências, cores recentes, nomes de perfis e todos os backups em `XDG_STATE_HOME/hidctl` (por padrão `~/.local/state/hidctl`). Também remove a regra udev correspondente à instalada, com sudo. A exclusão dos dados é definitiva; cancelar a confirmação não altera nada. Pacotes do sistema e o PATH compartilhado de `~/.local/bin` continuam preservados.

## Referências técnicas

- [Python 3.14: venv](https://docs.python.org/3.14/library/venv.html): ambientes criados no caminho definitivo e isolamento.
- [Python 3.14: subprocess](https://docs.python.org/3.14/library/subprocess.html): comandos com argumentos separados.
- [XDG Base Directory](https://specifications.freedesktop.org/basedir/latest/): diretórios do usuário.
- [Desktop Entry: Exec](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html): caminhos e escape no lançador.
- [pacman](https://man.archlinux.org/man/pacman.8.en): consulta e instalação de pacotes.

- [Zsh: arquivos de inicialização](https://zsh.sourceforge.io/Doc/Release/Files.html).
- [Fish: fish_add_path](https://fishshell.com/docs/current/cmds/fish_add_path.html).
