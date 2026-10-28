# Dispositivos compatíveis

## Mouse Cobra M711 do kit S118

| Identificação             | Suporte confirmado                                        |
| ------------------------- | --------------------------------------------------------- |
| VID:PID                   | `04d9:fc30`                                               |
| Revisão USB               | `0x0112`                                                  |
| Interface de configuração | HID 2, usage page `0xFFA0`                                |
| DPI                       | Cinco níveis por perfil, indicação ao vivo do nível ativo |
| Perfis                    | Visualização e edição dos cinco perfis; nomes locais      |
| Iluminação                | Cor estática RGB e onda multicolorida com velocidade      |

Valores nominais de DPI liberados: **500, 800, 1000, 1200, 2000, 2400, 3000, 3600 e 5000**. A precisão física não foi medida e o limite anunciado de 10.000 DPI não está liberado.

A onda ignora a cor selecionada. A interface não ativa perfis no hardware, não edita brilho e não oferece eixos independentes. Macros, remapeamento, polling rate e teclado não estão implementados.

Detalhes de comunicação: [referência técnica do dispositivo](devices/cobra-m711.md).

## Outros dispositivos

Não há suporte confirmado a outros modelos, revisões ou ao teclado Basike BA-key391. Compartilhar nome comercial ou VID/PID não basta para comprovar compatibilidade.

Contribuições devem incluir identificação da revisão, capacidades verificadas, comandos e respostas documentados, limites e testes significativos. Veja [como contribuir](como_contribuir.md).
