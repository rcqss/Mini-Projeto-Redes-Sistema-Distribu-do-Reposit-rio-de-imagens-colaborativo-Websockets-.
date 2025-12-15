# client.py
import asyncio
import websockets
import json
import os
import threading
from io import BytesIO

from PIL import Image, ImageTk
import tkinter as tk

HOST = "127.0.0.1"
PORT = 8765
URI = f"ws://{HOST}:{PORT}"
DOWNLOAD_DIR = "downloads_websocket"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# fila para separar respostas JSON vs dados binarios
RESP_QUEUE: asyncio.Queue = asyncio.Queue()
BIN_QUEUE: asyncio.Queue = asyncio.Queue()

async def ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)

def pretty_event(data: dict):
    event = data.get("event")
    if event == "NEW_UPLOAD":
        print(f"\n [NOVO UPLOAD] {data.get('message')}\n")
    elif event == "HISTORY":
        print("\n [HISTÓRICO] Últimos uploads:")
        for msg in data.get("data", []):
            print(f"   -> {msg.get('message')}")
        print()
    else:
        print(f"\n[EVENTO] {json.dumps(data, ensure_ascii=False)}\n")

def show_image_window(image_bytes: bytes, title: str = "VIEW"):
    #função para abrir a janela de visualizacao com tkinter
    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception as e:
        print(f"[VIEW ERRO] Não consegui decodificar a imagem: {e}")
        return

    root = tk.Tk()
    root.title(f"Visualizador - {title}")

    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    max_w = int(screen_w * 0.75)
    max_h = int(screen_h * 0.75)

    # mantem proporcao
    img.thumbnail((max_w, max_h))

    photo = ImageTk.PhotoImage(img)
    label = tk.Label(root, image=photo)
    label.image = photo  
    label.pack(padx=10, pady=10)

    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()

async def receiver(websocket):
    try:
        async for message in websocket:
            if isinstance(message, (bytes, bytearray)):
                await BIN_QUEUE.put(bytes(message))
                continue

            try:
                data = json.loads(message)
            except Exception:
                continue

            if "event" in data:
                pretty_event(data)
                continue

            await RESP_QUEUE.put(data)

    except websockets.exceptions.ConnectionClosed:
        await RESP_QUEUE.put({"status": "CLOSED"})
        await BIN_QUEUE.put(b"")

async def recv_response():
    return await RESP_QUEUE.get()

async def cmd_upload(websocket, username):
    path = (await ainput("Caminho da imagem: ")).strip()
    if not os.path.exists(path):
        print("Arquivo não existe.")
        return

    filename = os.path.basename(path)
    size = os.path.getsize(path)

    upload_cmd = {"cmd": "UPLOAD", "args": [filename, str(size)]}
    await websocket.send(json.dumps(upload_cmd))

    resp = await recv_response()

    if resp.get("status") == "READY":
        print(f"Servidor pronto. Enviando {filename} ({size} bytes)...")

        with open(path, "rb") as f:
            file_data = f.read()

        await websocket.send(file_data)

        final_resp = await recv_response()
        print(f"\n[SERVER]: [{final_resp.get('status')}]: {final_resp.get('message')}")

    elif resp.get("status") == "ERROR":
        print(f"\n[SERVER ERRO]: {resp.get('message')}")
    else:
        print("\n[SERVER ERRO]: Resposta inesperada do servidor após UPLOAD.")
        print(resp)

async def cmd_list(websocket):
    await websocket.send(json.dumps({"cmd": "LIST", "args": []}))
    resp = await recv_response()

    if resp.get("status") == "SUCCESS":
        print("\n--- Arquivos no Repositório (WS) --")
        data = resp.get("data", [])
        if not data:
            print("| Repositório vazio.")
        else:
            for item in data:
                print(f"| {item['filename']:<20} | Uploader: {item['uploader']}")
        print("----------------------------------")
    else:
        print(f"\n[SERVER ERRO]: {resp.get('message')}")

async def cmd_download_view(websocket, mode="DOWNLOAD"):
    nome = (await ainput(f"Nome do arquivo para {mode.lower()}: ")).strip()
    if not nome:
        return

    await websocket.send(json.dumps({"cmd": mode, "args": [nome]}))

    resp = await recv_response()

    if resp.get("status") == "SIZE_INFO":
        size = resp.get("size")
        filename = resp.get("filename")

        print(f"Recebendo {filename} ({size} bytes)...")

        file_data = await BIN_QUEUE.get()
        final_resp = await recv_response()

        if final_resp.get("status") == "SUCCESS":
            if isinstance(file_data, (bytes, bytearray)) and len(file_data) == size:

                if mode == "VIEW":
                    # abre janela própria sem bloquear o menu
                    t = threading.Thread(
                        target=show_image_window,
                        args=(bytes(file_data), filename),
                        daemon=True
                    )
                    t.start()
                    print("[VIEW] Janela aberta (feche com ESC).")
                    return

                # DOWNLOAD salva em disco
                out_name = os.path.join(DOWNLOAD_DIR, "baixado_" + filename)
                with open(out_name, "wb") as f:
                    f.write(file_data)
                print(f"\n[SUCESSO] Arquivo salvo em: {out_name}")

            else:
                got = len(file_data) if isinstance(file_data, (bytes, bytearray)) else -1
                print(f"\n[ERRO] Tamanho incorreto. Recebido: {got} bytes. Esperado: {size} bytes.")
        else:
            print(f"\n[SERVER ERRO] Falha na transferência: {final_resp.get('message')}")

    elif resp.get("status") == "ERROR":
        print(f"\n[SERVER ERRO]: {resp.get('message')}")
    elif resp.get("status") == "CLOSED":
        print("\n[ERRO] Conexão fechada.")
    else:
        print("\n[SERVER ERRO]: Resposta inesperada do servidor.")
        print(resp)

async def user_input_loop(websocket, username):
    while True:
        print("\n=== Cliente Imagens (WS) ===")
        print("1 - Upload")
        print("2 - Listar")
        print("3 - Download (Arquivo Original)")
        print("4 - View (Abrir Janela)")
        print("5 - Sair (DISCONNECT)")
        op = (await ainput("Opção (>>> ): ")).strip()

        if op == "1":
            await cmd_upload(websocket, username)
        elif op == "2":
            await cmd_list(websocket)
        elif op == "3":
            await cmd_download_view(websocket, "DOWNLOAD")
        elif op == "4":
            await cmd_download_view(websocket, "VIEW")
        elif op == "5":
            print("Encerrando conexão...")
            await websocket.send(json.dumps({"cmd": "DISCONNECT", "args": []}))

            resp = await recv_response()
            if resp.get("status") == "BYE":
                print(f"Servidor: {resp.get('message')}")

            await websocket.close()
            break
        else:
            print("Opção inválida.")

async def main():
    username = (await ainput("Informe seu usuário: ")).strip() or "anon"

    try:
        async with websockets.connect(URI) as websocket:
            print(f"Conectado ao servidor WebSocket em {URI}")

            recv_task = asyncio.create_task(receiver(websocket))

            await websocket.send(json.dumps({"cmd": "AUTH", "args": [username]}))
            resp = await recv_response()
            print("Servidor:", resp.get("message"))

            await user_input_loop(websocket, username)

            recv_task.cancel()

    except ConnectionRefusedError:
        print(f"Erro: Não foi possível conectar ao servidor em {URI}.")
    except Exception as e:
        print(f"Ocorreu um erro geral: {e}")
    finally:
        print("Cliente encerrado.")

if __name__ == "__main__":
    asyncio.run(main())
