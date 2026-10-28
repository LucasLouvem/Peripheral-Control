# Iluminação na interface

- O cartão **Iluminação** (embaixo do mouse) tem: seletor de **efeito** (Estático ou Onda; um efeito que o programa não edita, como Respiração,
  aparece como texto de apoio no seletor), a **amostra** da cor, a **paleta** de cores prontas e o **conta-gotas**. O desenho do mouse acompanha a cor e o brilho lidos.
- **Paleta** do cartão: aplica a cor na hora (só local) e passa o efeito para Estático. **Conta-gotas** (ou clicar na amostra): abre o modal
  **Cor da iluminação**, com duas abas:
  - **Cor sólida**: quadrado de saturação/brilho e barra de matiz (arrastáveis), 11 **predefinições**, **Cor atual** (prévia, campo hexadecimal
    `#RRGGBB`, botão de copiar) e os canais **R, G, B** (0–255). Todos os controles ficam sincronizados e a prévia é local.
  - **Cores recentes**: as últimas 12 cores **confirmadas** no modal (guardadas só neste computador, `~/.local/state/hidctl/recent-colors.json`;
    nada disso vai ao mouse). Clicar numa recente só a coloca no modal; ainda é preciso confirmar.
    O modal nunca acessa o mouse. **Confirmar** passa a cor para o estado pendente do painel; **Cancelar**, Esc ou fechar descartam só a edição
    daquela abertura (e não registram recentes); reabrir mostra a cor pendente (ou a do mouse). A aba "Efeito" da referência não existe: o efeito
    e a velocidade ficam no cartão.
- **Onda**: aparece o controle **Devagar ↔ Rápido** (velocidade 8 … 1 do aparelho, invertida para crescer à direita) e a amostra mostra um
  arco-íris (o efeito real do aparelho). A onda é multicolor e ignora a cor, mas a cor continua escolhível: escolher uma cor passa para
  Estático e, escolhendo Onda de novo, a cor fica guardada no registro junto com o modo e a velocidade.
- O seletor, a paleta e a velocidade só alteram o estado pendente (valor mudado fica em laranja no seletor); nada vai ao mouse até **Salvar**.
- **Salvar** envia DPI e iluminação numa só operação: grava só o necessário, aplica (`F1 02 02` para DPI e/ou `F1 02 04` para a luz), relê e só então
  mostra "Salvo e confirmado por releitura". A releitura confirma os **dados**; que a luz mudou de fato é conferido a olho.
- Trocar de perfil (ou recarregar) descarta a edição pendente, como no DPI. Conflito (outro programa mexeu na luz), falha, gravação parcial
  ou desconexão mantêm a edição e nunca mostram sucesso.
- O brilho (1–3) é lido e preservado, mas não é editável.

Capacidades e limites do hardware: [referência do Cobra M711](devices/cobra-m711.md).
