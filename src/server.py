# server.py
import asyncio
import websockets
import json
import os
from datetime import datetime
from PIL import Image
import threading

HOST = "0.0.0.0"
PORT = 8765
BASE_DIR = "imagens"
META_FILE = "metadata.json"

lock = threading.Lock()
metadata = []

CONNECTED_CLIENTS = set()
HISTORY_BUFFER = []
MAX_HISTORY = 5

def carregar_metadata():
    if not os.path.exists(META_FILE):
        return []
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_metadata(meta):
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def criar_thumbnail(source_path, thumb_path):
    try:
        with Image.open(source_path) as img:
            img.thumbnail((128, 128))
            img.save(thumb_path)
    except Exception as e:
        print(f"Erro ao criar thumbnail: {e}")

metadata = carregar_metadata()

async def broadcast(message: str):
    if not CONNECTED_CLIENTS:
        return
    tasks = [ws.send(message) for ws in list(CONNECTED_CLIENTS)]
    await asyncio.gather(*tasks, return_exceptions=True)
    print(f"[BROADCAST] Enviado para {len(CONNECTED_CLIENTS)} clientes.")

async def add_to_history_and_broadcast(message_json: dict):
    global HISTORY_BUFFER
    HISTORY_BUFFER.append(message_json)
    if len(HISTORY_BUFFER) > MAX_HISTORY:
        HISTORY_BUFFER.pop(0)
    await broadcast(json.dumps(message_json))

async def handle_auth(websocket, state, args):
    state["username"] = (args[0].strip() if args and args[0] else "anon")
    resp = {"status": "SUCCESS", "message": f"Autenticado como {state['username']}"}
    await websocket.send(json.dumps(resp))

    if HISTORY_BUFFER:
        history_message = {"event": "HISTORY", "data": HISTORY_BUFFER}
        await websocket.send(json.dumps(history_message))
        print(f"[{websocket.remote_address}] Histórico ({len(HISTORY_BUFFER)}) enviado após AUTH.")

async def handle_list(websocket, state, args):
    with lock:
        meta_list = [{"filename": m["filename"], "uploader": m["uploader"]} for m in metadata]
    resp = {"status": "SUCCESS", "cmd": "LIST", "data": meta_list}
    await websocket.send(json.dumps(resp))

async def handle_upload(websocket, state, parts):
    if len(parts) != 2:
        await websocket.send(json.dumps({
            "status": "ERROR",
            "message": "Formato UPLOAD incorreto (esperado: [filename, size])."
        }))
        return

    filename, size_str = parts
    try:
        size = int(size_str)
    except ValueError:
        await websocket.send(json.dumps({"status": "ERROR", "message": "Tamanho do arquivo invalido."}))
        return

    await websocket.send(json.dumps({"status": "READY", "cmd": "UPLOAD_DATA"}))

    try:
        file_data = await websocket.recv()

        if not isinstance(file_data, (bytes, bytearray)):
            raise Exception("Dados de arquivo não recebidos como binário.")

        file_data = bytes(file_data)
        if len(file_data) != size:
            raise Exception(f"Tamanho recebido ({len(file_data)}) != esperado ({size}).")

        with lock:
            new_id = len(metadata) + 1
            os.makedirs(BASE_DIR, exist_ok=True)

            original_path = os.path.join(BASE_DIR, f"{new_id}_{filename}")
            thumb_path = os.path.join(BASE_DIR, f"thumb_{new_id}_{filename}")

            with open(original_path, "wb") as f:
                f.write(file_data)

            criar_thumbnail(original_path, thumb_path)

            new_entry = {
                "id": new_id,
                "filename": filename,
                "uploader": state["username"],
                "path": original_path,
                "thumb_path": thumb_path,
                "timestamp": datetime.now().isoformat()
            }
            metadata.append(new_entry)
            salvar_metadata(metadata)

        await websocket.send(json.dumps({
            "status": "SUCCESS",
            "message": f"Upload de {filename} concluído. ID: {new_id}"
        }))

        notification = {
            "event": "NEW_UPLOAD",
            "message": f"Novo arquivo '{filename}' enviado por {state['username']}."
        }
        await add_to_history_and_broadcast(notification)

    except Exception as e:
        print(f"Erro durante o upload: {e}")
        await websocket.send(json.dumps({"status": "ERROR", "message": f"Falha no upload: {e}"}))

async def handle_download_view(websocket, state, parts, mode_label="DOWNLOAD", use_thumb=False):
    if len(parts) != 1:
        await websocket.send(json.dumps({
            "status": "ERROR",
            "message": "Formato invalido (esperado: [filename])."
        }))
        return

    filename = parts[0]

    with lock:
        info = next((m for m in metadata if m["filename"] == filename), None)

    if not info:
        await websocket.send(json.dumps({"status": "ERROR", "message": "Arquivo nao encontrado."}))
        return

    target_path = info.get("thumb_path") if use_thumb else info.get("path")
    if not target_path or not os.path.exists(target_path):
        await websocket.send(json.dumps({"status": "ERROR", "message": "Arquivo/Thumbnail nao disponivel."}))
        return

    size = os.path.getsize(target_path)

    await websocket.send(json.dumps({
        "status": "SIZE_INFO",
        "size": size,
        "filename": filename,
        "mode": mode_label
    }))

    try:
        with open(target_path, "rb") as f:
            file_data = f.read()

        await websocket.send(file_data)

        await websocket.send(json.dumps({
            "status": "SUCCESS",
            "message": f"Transferência de {filename} concluída."
        }))
    except Exception as e:
        print(f"Erro ao enviar arquivo {target_path}: {e}")
        await websocket.send(json.dumps({"status": "ERROR", "message": "Erro na transferência do arquivo."}))

async def handle_download(websocket, state, parts):
    await handle_download_view(websocket, state, parts, mode_label="DOWNLOAD", use_thumb=False)

async def handle_view(websocket, state, parts):
    # VIEW agora envia a imagem COMPLETA (o client abre em janela própria)
    await handle_download_view(websocket, state, parts, mode_label="VIEW", use_thumb=False)

async def handle_disconnect(websocket, state, parts):
    await websocket.send(json.dumps({
        "status": "BYE",
        "message": f"Cliente {state.get('username', 'anon')} se desconectando..."
    }))

async def handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    addr = websocket.remote_address
    state = {"username": "anon"}
    print(f"[+] Nova Conexão: {addr}")

    COMMANDS = {
        "AUTH": handle_auth,
        "LIST": handle_list,
        "UPLOAD": handle_upload,
        "DOWNLOAD": handle_download,
        "VIEW": handle_view,
        "DISCONNECT": handle_disconnect,
    }

    try:
        async for message in websocket:
            cmd = ""

            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    cmd = data.get("cmd", "").upper()
                    args = data.get("args", [])

                    display_name = state.get("username", "anon")
                    print(f"[{addr} - {display_name}] CMD: {cmd}, Args: {args}")

                    func = COMMANDS.get(cmd)
                    if func is None:
                        await websocket.send(json.dumps({"status": "ERROR", "message": "Comando desconhecido."}))
                    else:
                        await func(websocket, state, args)

                except json.JSONDecodeError:
                    print(f"[{addr}] ERRO: comando não é JSON válido: {message[:50]}")
                    await websocket.send(json.dumps({"status": "ERROR", "message": "Formato inválido (não é JSON)."}))

            elif isinstance(message, (bytes, bytearray)):
                print(f"[{addr}] DADO BINÁRIO fora de contexto: {len(message)} bytes.")

            if cmd == "DISCONNECT":
                break

    except websockets.exceptions.ConnectionClosedOK:
        print(f"[-] Conexão encerrada normalmente por {addr}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[-] Conexão encerrada com erro por {addr}: {e}")
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        print(f"[-] Conexão removida do pool: {addr} ({state.get('username')})")

async def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    print(f"Servidor WebSocket ouvindo em ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
