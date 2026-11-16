# Raio-X de Reputação de Comércios (Google Maps + IA)

Cole o link de qualquer estabelecimento do Google Maps e receba indicadores, gráficos de evolução da nota e um diagnóstico com plano de ação gerado por IA local (Ollama). Exporta tudo para Excel.

## Como usar (Windows)

1. Instale o [Python](https://www.python.org/downloads/) (marque **Add Python to PATH**) e o [Ollama](https://ollama.com/download)
2. Baixe este projeto (**Code → Download ZIP**) e extraia
3. Dê dois cliques em **`iniciar.bat`**

Na primeira vez ele instala tudo sozinho, baixa o modelo de IA e abre o Edge para você entrar na sua conta Google (depois é só fechar a janela). Nas próximas, abre direto.

## Funcionalidades

- Coleta de nome, data aproximada, nota e comentário das avaliações
- Nota média, taxa de satisfação e distribuição de notas
- Gráfico de evolução da nota com filtro de período
- Diagnóstico por IA: pontos fortes, gargalos e plano de ação
- Exportação para Excel formatado

## Tecnologias

Python, Streamlit, Selenium, Pandas, Altair, Ollama, XlsxWriter

## Observações

- Requer Windows e Microsoft Edge. Use de preferência uma conta Google secundária
- Datas são aproximadas (o Google informa "há 2 meses")