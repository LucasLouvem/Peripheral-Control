# Implementação orientada pela documentação oficial

## Regra obrigatória

Antes de escrever ou alterar código que utilize uma ferramenta, biblioteca, framework ou API, o Claude Code deve consultar a documentação oficial correspondente à versão utilizada no projeto e seguir as orientações aplicáveis à tarefa.

Essa consulta faz parte da implementação. Não basta presumir o comportamento de uma API com base em memória, exemplos antigos ou código gerado anteriormente.

## O que verificar

- APIs disponíveis, assinaturas e comportamentos documentados;
- compatibilidade com a versão e a plataforma utilizadas;
- práticas recomendadas e restrições de uso;
- avisos de segurança, recursos obsoletos, problemas conhecidos e soluções documentadas.

Quando a documentação alertar sobre uma abordagem problemática, a implementação deve respeitar essa restrição e adotar a alternativa recomendada, quando houver. Não repetir uma prática contraindicada sem discutir o impedimento com o usuário e o Codex.

## Quando não houver orientação documentada

Somente quando a documentação oficial não cobrir o caso necessário, o Claude Code pode definir uma solução com seu próprio julgamento técnico, dentro do escopo aprovado.

Nesse caso, deve:

1. identificar a lacuna encontrada e distinguir fatos documentados de hipóteses;
2. justificar brevemente a abordagem escolhida;
3. validar o comportamento com verificações proporcionais ao risco;
4. registrar limitações e resultados no relatório final e na documentação afetada.

A indisponibilidade de acesso à documentação não equivale à ausência de orientação. Se o acesso impedir uma decisão necessária, informar a limitação e seu impacto antes de avançar na parte dependente.

## Evidências e manutenção

Registrar na documentação da entrega as fontes oficiais consultadas, as versões relevantes e as decisões que dependam dessas fontes. O relatório final deve mencionar a consulta e eventuais lacunas, sem afirmar validações que não foram executadas.

Esta regra busca reduzir bugs por uso incorreto de ferramentas; ela não substitui testes nem garante ausência de falhas. Também não autoriza ampliar o escopo ou alterar requisitos aprovados.
