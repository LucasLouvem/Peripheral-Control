# Como contribuir

Abra uma issue para discutir funcionalidades, falhas ou novos dispositivos. Envie mudanças por pull request, descrevendo o comportamento entregue, a validação executada e limitações.

## Ambiente

Requisitos: Linux, Python 3.11 ou superior e bibliotecas gráficas do Qt. Arch Linux é o ambiente de referência; outras distribuições precisam de validação própria.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[gui,dev]'
python -m hidctl.gui --demo
```

Use o checkout e o ambiente virtual para desenvolvimento. O instalador cria uma cópia independente para uso normal. O atualizador não altera seu checkout nem substitui alterações locais.

## Verificações

```bash
ruff check .
ruff format --check .
QT_QPA_PLATFORM=offscreen pytest
sh -n scripts/install.sh
npx prettier@3.8.1 --check '**/*.md' '*.json'
```

Python é formatado com Ruff; Markdown e JSON com Prettier. Testes devem verificar funcionalidades reais, sucesso, erro e regressões relevantes com valores concretos. Não adicione cenários redundantes nem testes apenas de remoção de componentes.

Consulte as [diretrizes de testes](diretrizes-de-testes.md) e de [implementação](diretrizes-de-implementacao.md). Testes físicos são separados e exigem habilitação explícita; veja [tests_physical](../tests_physical/README.md).

## Documentação

Atualize a documentação afetada. Cada dispositivo possui uma referência em [devices/](devices/), com identificação, transporte, comandos, respostas, capacidades, limites e fontes. Não adicione diários de tentativas, planos antigos ou cópias de código.

Atualize também a [lista de compatibilidade](dispositivos_compativeis.md) ao adicionar suporte validado. O nome comercial, sozinho, não comprova compatibilidade.

## Pull requests

- Mantenha a alteração focada e preserve mudanças existentes.
- Use Conventional Commits, separados por assunto.
- Informe o que foi testado, o resultado e o que não foi possível testar.
- Não inclua credenciais, caches, ambientes virtuais ou backups pessoais.
- Preserve o menor privilégio e o fluxo de edição local antes de salvar.
- O código contribuído deve ser compatível com a licença MIT do projeto.
