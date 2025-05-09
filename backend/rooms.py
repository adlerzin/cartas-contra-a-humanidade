import asyncio
import websockets
import json
import subprocess
import os

def iniciar_partida(porta):
    diretorio = __file__
    diretorio = os.path.dirname(__file__)
    subprocess.Popen(
        ["python3", f"{diretorio}/app.py", str(porta)]
    )
    print(f"Partida iniciada na porta {porta}")

# Dicionário para armazenar as salas e nomes conectados
salas = {}

async def handler(websocket):
    try:
        async for message in websocket:
            print("Mensagem recebida:", message)

            try:
                data = json.loads(message)
                if data["type"] == "join":
                    nome = data["nome"]
                    sala = data["sala"]

                    if sala not in salas:
                        salas[sala] = []
                        iniciar_partida(sala)
                    salas[sala].append(nome)

                    print(f"{nome} entrou na sala '{sala}'")
                    await websocket.send(f"Bem-vindo, {nome}! Você entrou na sala '{sala}'.")

                else:
                    await websocket.send("Tipo de mensagem não reconhecido.")

            except json.JSONDecodeError:
                await websocket.send("Erro: mensagem JSON inválida.")

    except websockets.exceptions.ConnectionClosed:
        print("Conexão encerrada.")

# Iniciar o servidor na porta 4000
async def main():
    async with websockets.serve(handler, "localhost", 4000):
        print("Servidor WebSocket iniciado em ws://localhost:4000")
        await asyncio.Future()  # mantém o servidor rodando

asyncio.run(main())
