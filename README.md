Repositório Colaborativo de Imagens (WebSockets) — Sistemas Distribuídos

Projeto da cadeira Introdução aos Sistemas Distribuídos e Redes (CIn/UFPE).
O sistema implementa um repositório colaborativo de imagens com arquitetura Cliente–Servidor usando WebSockets em Python, permitindo upload, listagem, download e visualização de imagens.

💡 Objetivo Central

Implementar um sistema de compartilhamento de imagens com comunicação persistente via WebSockets, permitindo que o cliente permaneça conectado ao servidor e execute múltiplas operações sem reconectar a cada comando.

A comunicação ocorre sobre TCP (subjacente ao WebSocket), garantindo entrega ordenada e confiável do fluxo de bytes, enquanto o aplicativo define um protocolo simples de mensagens (JSON + binário) para comandos e transferência de arquivos.

📝 Funcionalidades

O sistema oferece os seguintes comandos:

UPLOAD: Envia uma imagem do cliente para o servidor. O servidor salva o arquivo e registra metadados (autor, data, etc.).

LIST: Lista as imagens disponíveis no repositório (nome do arquivo e uploader).

DOWNLOAD: Baixa a imagem original do servidor para o cliente, salvando em disco.

VIEW: Recebe a imagem do servidor e abre uma janela própria da aplicação para visualização (Tkinter + Pillow).

DISCONNECT: Encerra a conexão do cliente de forma controlada.

🛠️ Tecnologias e Protocolos

Linguagem: Python 3

Comunicação: WebSockets (websockets + asyncio)

Formato de Mensagens:

JSON (texto) para comandos e metadados (AUTH, UPLOAD, LIST, DOWNLOAD, VIEW, DISCONNECT)

Binário para envio/recebimento do conteúdo da imagem

Manipulação/Exibição de Imagens:

Pillow (PIL) para decodificar bytes da imagem

Tkinter para abrir uma janela própria de visualização no client

Armazenamento:

metadata.json para catálogo persistente das imagens enviadas

📂 Estrutura do Projeto:
.
├── server.py                 # Servidor WebSocket: processa comandos e gerencia repositório
├── client.py                 # Cliente WebSocket: menu interativo, upload/list/download/view
├── metadata.json             # Gerado automaticamente: catálogo de imagens do servidor
├── imagens/                  # Gerado automaticamente: arquivos armazenados no servidor
└── downloads_websocket/      # Gerado automaticamente: arquivos baixados no cliente


▶️ Como Rodar o Projeto
Pré-requisitos

Python 3 instalado

pip funcionando

Dependências instaladas:
pip install websockets pillow
(Observação: o Tkinter normalmente já vem junto com o Python.
Se der erro de Tkinter, reinstale Python marcando a opção “tcl/tk”.)

Rodando o Servidor: 
Abra um terminal na pasta do projeto e execute: python server.py


Rodando o Cliente:
Abra outro terminal na pasta do projeto e execute: python client.py

O cliente irá solicitar um nome de usuário e exibirá um menu com as opções de comando.
