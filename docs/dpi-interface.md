# DPI e perfis

O [Cobra M711 do kit S118](devices/cobra-m711.md) oferece cinco perfis com cinco níveis de DPI cada. A interface visualiza e edita esses perfis, mas não altera o perfil ativo no hardware.

## Edição

O nível ativo aparece em verde e acompanha o botão físico. Alterações pendentes aparecem em laranja. Os sliders percorrem os nove valores nominais liberados na referência do dispositivo.

Selecionar um perfil muda apenas a visualização. O botão + revela perfis já existentes no mouse, até cinco. Nomes e quantidade de perfis visíveis ficam salvos somente neste computador. Trocar de perfil ou recarregar descarta a edição pendente com aviso.

## Salvamento

Editar não grava no aparelho. Salvar valida as entradas, lê o estado atual, verifica conflitos nos campos editados, faz backup, grava somente as alterações e confirma por releitura. Alterações externas nos campos não editados são preservadas.

O aplicativo serializa operações e mantém a interface responsiva. Uma gravação precisa terminar antes do fechamento. Não há atomicidade: falhas podem deixar gravações parciais ou sem confirmação. A edição pendente é preservada e o resultado é informado sem apresentar sucesso indevido.

## Dados locais e acesso

Preferências, backups e trava de acesso ficam em `~/.local/state/hidctl/`. O modo simulado não acessa dispositivos.

A [regra udev](../packaging/udev/70-hidctl-04d9-fc30.rules) concede `uaccess` somente à revisão e interface suportadas, para o usuário da sessão local ativa. A instalação está no [README](../README.md). Não execute o aplicativo como root.

## Limitações

Não há digitação livre de DPI, edição independente dos eixos ou suporte à edição de níveis desabilitados. A precisão física não foi medida. Chamadas bloqueadas no kernel podem manter uma operação pendente até retornar. O observador acompanha eventos de nível, mas não de troca de perfil; recarregar consulta novamente o aparelho.
