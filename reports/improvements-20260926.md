# Melhorias de 26/09/2026

## Entregue

- Proteção de todas as mensagens externas, arquivos privados, limites de leitura e redirecionamentos HTTP.
- Rejeição de contexto excessivo mesmo sem tokenizador; compactação de contexto opcional.
- Ciclo EXPERT com correção única e revisão final, preservação do rascunho e status explícito de divergências.
- Orçamentos de chamadas e saída externa, prazo entre etapas, métricas de falhas e fallback.
- Memória somente por ação explícita, gravação atômica, remoção por índice e desligamento da leitura.
- CLI interativa, sessões persistentes opcionais, skills locais, concisão, arquivos locais e proposta textual de diff.
- Ferramentas de listagem, sintaxe e unittest com execução explícita e timeout.
- Diagnóstico de endpoints e modelos sem geração; tratamento seguro de erros dos provedores.
- Benchmark com seis tarefas, três modos, comparação de skills, persistência parcial e memória isolada.
- Documentação atualizada e workflow de CI para Python 3.11, 3.12 e 3.13.

## Evidência local

- Python 3.14.7.
- `python -m unittest discover -q`: 52 testes passaram.
- `python main.py --check syntax`: 29 arquivos Python válidos.
- `python main.py --check unittest --allow-exec`: execução real da suíte pela ferramenta, exit code 0.
- `python main.py --help`: CLI disponível.
- `python benchmarks/run.py --task simple_clamp --skills none auto`: matriz de seis execuções descrita sem inferência.

Testes usam provedores simulados para reproduzir falhas, limites e papéis. Nesta entrega não foram executadas novas inferências reais nem medições de hardware. O diagnóstico foi implementado; disponibilidade real dos serviços não foi afirmada. A matriz de versões de CI ainda depende da execução no GitHub.

## Limites conhecidos

A sanitização usa padrões e não é uma garantia absoluta de privacidade. Execução de unittest não é uma sandbox. O limite de tokens externos cobre saída reservada, não entrada nem custo monetário. O prazo é verificado entre etapas e combinado com timeout HTTP. Sem tokenizador a estimativa pode recusar entradas que caberiam em contagem exata. Persistência não mescla gravações concorrentes. Conteúdo local privado força fallback local. Diffs são propostas, sem aplicação automática. Qualidade funcional do código gerado, streaming, comparação de modelos e otimização de GPU continuam pendentes no roadmap.
