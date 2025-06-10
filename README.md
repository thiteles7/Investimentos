# Investimentos

Este projeto utiliza SQLite e Streamlit para gerenciar investimentos.

## Executando os testes

Para rodar os testes unitários, execute o seguinte comando na raiz do projeto:

```bash
pytest
```

## Consulta de Cotações

Na aba **Cotações** é possível buscar ativos informando o ticker ou apenas o
nome da empresa/fundo. O aplicativo consulta a API de busca do Yahoo Finance e
lista os tickers encontrados com a cotação atual, permitindo adicioná-los aos
favoritos.
