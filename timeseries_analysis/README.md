# Análise Introdutória de Séries Temporais: Engajamento Radar BVR

Este diretório contém os scripts, dados (CSV) e um Jupyter Notebook dedicados a ilustrar e explicar os conceitos fundamentais de **Análise de Séries Temporais** aplicados a um caso prático do simulador tático Glaukopis.

O caso de estudo apresenta o engajamento de rastreio de um caça interceptador contra um **Su-27 Flanker** voando a altas velocidades em um ambiente de longo alcance (Beyond Visual Range - BVR).

## 🎯 Objetivo da Análise
O foco pedagógico destes documentos é usar a física e a eletrônica emuladas do Glaukopis para tornar reais conceitos abstratos de estatística e filtros numéricos. A simulação oferece uma distinção cristalina entre os elementos puros e os elementos estocásticos.

### 1. Tendência Determinística (Trend)
* **Conceito Matemático:** O comportamento fundamental contínuo sem anomalias, guiado por regras estritas (como a Cinemática).
* **Na Simulação:** Representado pela posição real (`TGT_01_pos_x`). O decaimento linear da distância ao longo do eixo demonstra com precisão a verdadeira trajetória, livre de incertezas. Vemos o avanço contínuo de 43.000m até o interceptador cruzar seu caminho.

### 2. Ruído Gaussiano Branco e Limiares (Noise / Signal Thresholds)
* **Conceito Matemático:** A poluição dos dados via Distribuição Normal e limites categóricos.
* **Na Simulação:** Observado no Signal-to-Noise Ratio (`snr_db`). O retorno do radar é corrompido instantaneamente baseando-se nas equações de Radar Eletromagnético acrescido de AWGN. Disso nasce o conceito visível do threshold/limiar: as instabilidades violentas ao longo cruzamento do `CFAR` (~13 dB) evidenciam bem como ruído se opõe à detecção de padrão no algoritmo.

### 3. Dinâmica Não-Estacionária e Cintilação (Stochastic Variations)
* **Conceito Matemático:** Um valor médio que esconde variâncias agudas não previsíveis individualmente. 
* **Na Simulação:** Visível na medição instantânea do Radar Cross Section do Su-27 (`TGT_01_rcs_instantaneous`). A assinatura térmica/eletromagnética se altera (Swirling Scintillation Model) dramaticamente enquanto a pose do alvo no arrot de Euler muda. Aqui notamos que a média `3.3 m²` se destaca visivelmente como constante contra picos ruidosos caóticos. Justifica cabalmente pela geometria física o "porquê" de precisarmos de suavização (Time Series Smoothing/Alpha-Beta filters).

---

## 📂 Arquivos no Diretório

### Notebooks
* `Cap1_Analise_Introdutoria_Series_Temporais_Radar.ipynb` — **Capítulo 1**: Notebook introdutório detalhando passo a passo a demonstração com plots visuais e explicações descritivas. *Recomendado abrir este primeiro.*
* `Cap2_Graficos_Series_Temporais_Radar.ipynb` — **Capítulo 2**: Gráficos de Séries Temporais (FPP3 §2.2–§2.9). 13 gráficos cobrindo time plots, scatterplots, lag plots, autocorrelação (ACF) e ruído branco, aplicados ao dataset radar.
* `Cap3_Decomposicao_Series_Temporais_Radar.ipynb` — **Capítulo 3**: Decomposição de Séries Temporais (FPP3 §3.1–§3.6). Transformações Box-Cox, médias móveis (SMA/WMA/2×m-MA), decomposição clássica aditiva e decomposição STL robusta, aplicadas ao SNR, RCS, g_force e miss_distance.

### Dados e Scripts
* `timeseries_seed_101.csv` — O banco de dados em si! Uma única thread (Seed 101) extraída frame a frame ($0.1s$) dos cálculos matriciais com a telemetria integral dos módulos físicos para sua importação PANDAS.
* `time_series_plot.png` — Uma compilação de rápido acesso da plotagem renderizada na simulação atual.
* `run_mc_single_seed.py` — Script responsável por conectar-se ao compilador numérico do simulador (BatchRunner backend), isolar uma seed (ex. 101) e extrair os dados formatados perfeitamente para CSV. 
* `visualize_dataset.py` — Script autônomo baseado em matplotlib sem depender do jupyter para re-renderizar a plotagem `time_series_plot.png`.

## 🛠️ Como Reproduzir

1. Se a seed principal precisar de mudanças ou outros cenários testados:
```bash
python timeseries_analysis/run_mc_single_seed.py
```
*(Certifique-se de executar da raiz principal do repositório `/Glaukopis/` )*

2. Apenas regerar o gráfico `png` se mudanças analíticas foram aplicadas:
```bash
python timeseries_analysis/visualize_dataset.py
```

3. Abra os notebooks via extensão Jupyter no VSCode ou Browser:
   - 👉 Cap. 1: `Cap1_Analise_Introdutoria_Series_Temporais_Radar.ipynb`
   - 👉 Cap. 2: `Cap2_Graficos_Series_Temporais_Radar.ipynb`
   - 👉 Cap. 3: `Cap3_Decomposicao_Series_Temporais_Radar.ipynb`
