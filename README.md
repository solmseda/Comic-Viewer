# CBRReaderPy (Comic Viewer)

Visualizador de quadrinhos (.CBR/.CBZ) em PyQt5, com miniaturas, leitura em tela cheia e sincronização opcional com OneDrive e Google Drive.

- Foco em desktop (macOS/Linux); testado com PyQt5.
- Nome interno do app: `CBRReaderPy` (ver `comic_viewer/config.py`).

## Funcionalidades
- Biblioteca local: escolhe a pasta da biblioteca e lista arquivos `.cbr/.cbz` (modo lista ou grade com miniaturas).
- Busca rápida: filtro por nome conforme você digita.
- Leitor integrado: navegar com setas, barra de espaço, Home/End; zoom; tela cheia; “Ir para página…”.
- Retoma leitura: lembra a última página de cada arquivo.
- Miniaturas: geração em background para `.cbr/.cbz` com cache.
- Sincronização:
  - OneDrive: login via Device Code (MSAL) e download de arquivos selecionados.
  - Google Drive: login OAuth, seletor de pastas e download.

## Requisitos
- Python 3.10+ (recomendado 3.11+).
- Dependências Python: ver `requirements.txt`.
- Utilitários externos para CBR/miniaturas:
  - `unar` e `lsar` (The Unarchiver CLI). Necessários para extrair/inspecionar `.cbr`.
    - macOS (Homebrew): `brew install unar`
    - Debian/Ubuntu: `sudo apt-get install unar`

Dicas de detecção de binários: `comic_viewer/utils.py:6` e `comic_viewer/utils.py:14`.

## Instalação
- Criar e ativar ambiente virtual:
  - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
- Instalar dependências:
  - `pip install -r requirements.txt`
- Instalar utilitários externos (se necessário):
  - `brew install unar` (macOS) ou `sudo apt-get install unar` (Linux)

## Configuração
- Caminhos e constantes principais: `comic_viewer/config.py:1`.
- Pasta padrão da biblioteca: `~/CBRLibrary` (pode ser alterada pela UI).
- Dados do app: `~/Library/Application Support/CBRReaderPy/` (macOS). Contém:
  - `state.json`: preferências e progresso de leitura.
  - `msal_cache.bin`: cache MSAL (OneDrive).
  - `gdrive_credentials.json` e `gdrive_token.json` (Google Drive).

### OneDrive (MSAL)
- Defina o `CLIENT_ID` do seu app Entra/Azure AD em `comic_viewer/config.py:15`.
- Escopos utilizados (somente leitura de arquivos): `comic_viewer/config.py:23`.
- O login usa Device Code Flow no próprio app; não requer URI de redirecionamento.

### Google Drive
- Crie um “OAuth Client ID” do tipo “Desktop App” no Google Cloud Console.
- Baixe o JSON e salve em: `~/Library/Application Support/CBRReaderPy/gdrive_credentials.json`.
- O app vai abrir o navegador para autenticação e salvar o token em `gdrive_token.json`.

## Execução
- Ative o venv (se aplicável) e rode:
  - `python app.py`
- Ponto de entrada: `app.py:1`. A janela principal é `comic_viewer/ui/main_window.py`.

## Uso Rápido
- Selecione/alterne a “Pasta da biblioteca” pela toolbar.
- Modo de exibição: Lista/Grade (grade usa miniaturas; pode levar alguns segundos no primeiro carregamento).
- Clique duas vezes em um item para abrir o leitor.
- Painel lateral mostra pastas conectadas e status de contas.

### Leitor de páginas
- Navegação: ← → ↑ ↓, PageUp/PageDown, Espaço, Home/End.
- Zoom: slider na barra inferior.
- Tela cheia: `F` ou `F11`.
- Ir para página: menu/atalho (`Cmd+G` no macOS, `Ctrl+G` no Windows/Linux).

### Miniaturas e Extração
- `.cbz`: lido via `zipfile` internamente.
- `.cbr`: requer `lsar` para listar e `unar` para extrair a primeira imagem.
- Cache em `~/Library/Application Support/CBRReaderPy/thumbnails/`.

### Sincronização de Arquivos
- OneDrive:
  - Toolbar → “OneDrive” → Conectar → Escolher pasta → Sincronizar.
  - Apenas `.cbr/.cbz` são baixa dos. Arquivos já existentes (mesmo tamanho) são ignorados.
- Google Drive:
  - Toolbar → “Google Drive” → Conectar → Escolher pasta (seletor) → Sincronizar.
  - Suporta “Incluir subpastas: ON/OFF”.

## Solução de Problemas
- “Ferramenta 'unar' não encontrada”: instale `unar` (ver Requisitos). Mensagem originada em `comic_viewer/extractor.py`.
- Miniaturas não aparecem para `.cbr`: garanta `lsar` e `unar` instalados e no caminho esperado.
- OneDrive “CLIENT_ID” não definido: ajuste em `comic_viewer/config.py:15`.
- Google Drive: coloque o `gdrive_credentials.json` no caminho correto antes de conectar.

## Desenvolvimento
- Estrutura principal:
  - UI principal: `comic_viewer/ui/main_window.py`
  - Leitor: `comic_viewer/ui/reader_window.py`
  - Extração/miniaturas: `comic_viewer/extractor.py`, `comic_viewer/thumbnails.py`
  - OneDrive: `comic_viewer/onedrive/*`
  - Google Drive: `comic_viewer/gdrive/*`
  - Estado: `comic_viewer/state.py`
- Log global configurado em `app.py` (ajuste o nível se necessário).
- Utilitário simples para testar Google Drive: `test_gdrive_list.py`.

---

Sinta-se à vontade para abrir issues ou sugestões de melhoria.
