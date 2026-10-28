# Diretrizes para testes automatizados

## Objetivo

Os testes devem verificar comportamentos e resultados concretos dos requisitos. Um teste só é útil quando consegue detectar uma implementação incorreta do comportamento que pretende proteger.

## Casos de sucesso e de erro

Para cada comportamento implementado, cobrir os caminhos de sucesso e os caminhos de erro aplicáveis, incluindo limites relevantes das entradas. Escolher cenários com base nos requisitos e riscos, sem criar casos artificiais apenas para aumentar a quantidade de testes ou a cobertura.

- No sucesso, verificar o resultado esperado e os efeitos observáveis da operação.
- No erro, verificar a rejeição esperada, a exceção ou o estado de falha correspondente e a ausência de efeitos indevidos.
- Quando houver mudança de estado, verificar o estado resultante e a preservação dos dados que não deveriam mudar.

## Asserções concretas

Verificar somente que um resultado existe, possui determinado tipo ou que uma chamada ocorreu não comprova que a operação está correta.

As asserções devem comparar o conteúdo recebido com o valor esperado para a entrada do cenário. Quando o tipo também fizer parte do contrato, verificar tanto o tipo quanto o valor.

Exemplo: se uma operação recebe DPI 1600 e deve retornar esse valor, testar apenas que o retorno é um inteiro é insuficiente. O teste deve confirmar que o retorno é exatamente 1600 e, se o contrato exigir, que seu tipo é inteiro. Um retorno de 800 deve fazer esse teste falhar.

Para estruturas, verificar os campos e valores relevantes. Para comandos ou mensagens, verificar o conteúdo exato esperado, incluindo destino, ordem e quantidade quando fizerem parte do contrato. Não usar comparações vagas que aceitem resultados incorretos.

Resultados esperados devem derivar do requisito ou de uma referência independente. Não calculá-los chamando a própria lógica sob teste ou copiando sua implementação, pois isso pode reproduzir o mesmo defeito.

## Falhas e segurança

Os cenários de erro devem representar falhas reais aplicáveis ao comportamento: entradas inválidas, limites excedidos, dispositivo ausente, acesso negado ou falha de comunicação, conforme o escopo da tarefa.

Além da falha reportada, verificar as proteções relevantes. Por exemplo, uma configuração inválida não deve enviar comandos ao dispositivo, e uma falha de aplicação não deve ser apresentada como sucesso.

Testes automatizados comuns não devem depender de um dispositivo físico nem executar macros reais ou gravar configurações no hardware. Validações com hardware devem ser separadas e explicitamente identificadas.

## Uso de mocks e simulações

Usar mocks ou simulações nas fronteiras necessárias, preservando a execução do comportamento que se deseja testar. Não substituir a própria lógica sob teste por um retorno configurado e depois verificar esse mesmo retorno.

Quando a interação com uma dependência for parte do contrato, verificar os argumentos concretos enviados e os efeitos do retorno ou erro simulado. Confirmar apenas que o mock foi chamado é insuficiente quando o conteúdo da chamada importa.

## Critérios de revisão e entrega

- Priorizar funcionalidades presentes no aplicativo e regressões de defeitos reais. Não criar testes apenas para comprovar que um botão, texto, arquivo ou componente foi removido ou deixou de existir.
- Não testar apenas a presença de elementos ou detalhes da composição visual. Quando houver teste de interface, verificar uma interação e seu resultado funcional concreto.
- Asserções de ausência são pertinentes quando protegem um comportamento funcional, como não gravar antes de salvar ou não enviar uma entrada inválida; não confundir essas garantias com testes de remoção de elementos.
- Evitar cenários redundantes que exercitem a mesma garantia sem acrescentar risco, limite ou comportamento relevante. Não ampliar a bateria apenas para aumentar a contagem.
- Cada teste deve indicar qual comportamento protege e por que falharia diante de um resultado incorreto.
- Testes não podem depender da ordem de execução ou de estado residual de outros testes.
- Não criar testes triviais de detalhes internos, getters ou constantes apenas para aumentar métricas.
- Quantidade de testes e porcentagem de cobertura não substituem a qualidade dos cenários e das asserções.
- No relatório, informar os cenários de sucesso e erro cobertos, os comandos executados, os resultados e as lacunas restantes.
- Distinguir testes escritos de testes efetivamente executados; não declarar sucesso sem evidência de execução.

As validações devem ser proporcionais à mudança. Estas diretrizes não exigem testes artificiais para alterações puramente documentais ou cosméticas; exigem testes significativos para os comportamentos entregues.
