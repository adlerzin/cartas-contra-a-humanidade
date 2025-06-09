import asyncio
import websockets
import json
import random
import time
from cartas import white_cards 
from cartas import black_cards
import os
# import random # Removido import duplicado

# --- Server State ---
clients = set()
# {websocket: {"score": 0, "submitted_this_round": False, "voted_this_round": False, "hand": []}}
players = {}
# Combinando as duas listas de cartas brancas fornecidas
# A segunda lista fornecida parece mais com cartas pretas/perguntas
current_black_card = None
submitted_white_cards = [] # [{"player": websocket, "card": card_text}]
votes = {} # {card_text: count}
max_points = 2
min_players = 2 # Mínimo de jogadores para iniciar
HAND_SIZE = 7 # Tamanho da mão de cartas brancas de cada jogador

# Game state
game_state = "waiting_for_players" # "waiting_for_players", "starting_countdown", "in_game", "game_over"
start_timer_task = None # Task para o countdown
countdown_seconds_left = 0
COUNTDOWN_DURATION = 10 # Segundos para o countdown

# --- Helper Functions ---

async def broadcast(message):
    """Envia mensagem a todos os clientes conectados."""
    if clients:
        # print(f"Broadcasting: {message}") # Debugging broadcast
        # Usa list() para criar uma cópia e evitar "Set changed size during iteration" se um cliente desconectar durante o broadcast
        # Envia em paralelo usando gather
        await asyncio.gather(*[send_to_client(client, message) for client in list(clients)])


async def send_to_client(websocket, message):
    """Envia mensagem a um cliente específico, tratando desconexões."""
    # Verifica se o websocket ainda está no set clients antes de tentar enviar
    if websocket in clients:
        try:
            # Use asyncio.wait_for para adicionar um timeout ao envio (opcional, mas pode evitar hangs)
            # await asyncio.wait_for(websocket.send(json.dumps(message)), timeout=5.0) # Exemplo com timeout
             await websocket.send(json.dumps(message))
            # print(f"Mensagem enviada para {websocket.remote_address}: {message}") # Debugging send sucesso
        except websockets.exceptions.ConnectionClosed:
            # Esta exceção é esperada se o cliente desconectar, não precisa de erro grave
            print(f"Falha ao enviar mensagem para {websocket.remote_address}, conexão já fechada.")
            # A limpeza deste cliente será tratada no finally do handler dele
        except Exception as e:
            # Captura outros erros de envio (buffer cheio, etc.)
            print(f"Erro ao enviar mensagem para {websocket.remote_address}: {e}")
            # O handler deste cliente eventualmente terá seu loop encerrado ou exceção tratada.


def get_player_count():
    """Retorna o número de jogadores conectados (excluindo possíveis espectadores, se houvesse distinção)."""
    # Conta quantos websockets estão no dicionário players (representam jogadores ativos)
    return len(players)

async def update_game_state(new_state, message=""):
    """Atualiza o estado do jogo e broadcasta a mudança."""
    global game_state
    if game_state != new_state:
        game_state = new_state
        print(f"Game State changed to: {game_state}. Message: {message}") # Debugging state change
        await broadcast({"action": "game_state_update", "state": game_state, "message": message})

# --- Game Logic Functions ---

async def start_countdown():
    """Inicia o countdown para começar o jogo."""
    global game_state, countdown_seconds_left, start_timer_task
    # Garante que o countdown só inicie se estiver no estado de espera e houver jogadores suficientes
    if game_state == "waiting_for_players" and get_player_count() >= min_players:
        await update_game_state("starting_countdown", f"Game starting in {COUNTDOWN_DURATION} seconds...")
        countdown_seconds_left = COUNTDOWN_DURATION
        # Cancela a task anterior caso start_countdown seja chamado novamente
        if start_timer_task and not start_timer_task.done():
            start_timer_task.cancel()
            try:
                 await start_timer_task # Aguarda a task ser cancelada (evita warning)
            except asyncio.CancelledError:
                 pass
        start_timer_task = asyncio.create_task(run_countdown_timer())
    # else: # Debugging
        # print(f"Não iniciou countdown. State: {game_state}, Players: {get_player_count()}")


async def run_countdown_timer():
    """Tarefa assíncrona que executa o timer do countdown."""
    global countdown_seconds_left, start_timer_task
    try:
        while countdown_seconds_left > 0:
            # Verifica se o número de jogadores ainda é suficiente DENTRO do loop do timer
            if get_player_count() < min_players:
                 print("Número de jogadores insuficiente durante countdown. Cancelando.") # Debugging
                 # Levanta CancelledError para ser pego na exceção e ir para finally
                 raise asyncio.CancelledError

            await broadcast({"action": "countdown", "seconds": countdown_seconds_left})
            await asyncio.sleep(1)
            countdown_seconds_left -= 1

        # Timer terminou (sem ser cancelado)
        if get_player_count() >= min_players:
            await start_game()
            
        else:
            # Esta parte só seria atingida se o get_player_count() mudasse exatamente após o loop
            # O raise CancelledError acima lida melhor com a queda de jogadores
            print("Countdown terminou, mas jogadores insuficientes (Edge case?).") # Debugging
            await update_game_state("waiting_for_players", "Not enough players. Countdown stopped.")

    except asyncio.CancelledError:
        print("Countdown timer task was cancelled.") # Debugging
        # O estado será definido para waiting_for_players no handler do cliente que causou a queda de jogadores.
        # Ou podemos definir aqui se quisermos:
        # if game_state == "starting_countdown": # Evita mudar estado se já for game over, etc.
        #      await update_game_state("waiting_for_players", "Not enough players. Countdown stopped.")
    except Exception as e:
         print(f"Erro inesperado no countdown timer: {e}")
         traceback.print_exc() # Imprime o traceback do erro no timer


async def start_game():
    """Inicia a primeira rodada do jogo."""
    global game_state
    print("Starting game...") # Debugging
    # Resetar pontuações APENAS se quisermos um jogo completamente novo a cada vez que atinge min_players
    # Caso contrário, as pontuações persistem para quem continua conectado
    # for player_data in players.values():
    #     player_data["score"] = 0

    await update_game_state("in_game", "Game started!")
    # Começa a primeira rodada
    await start_new_round()


async def start_new_round():
    """Prepara e inicia uma nova rodada."""
    global current_black_card, submitted_white_cards, votes

    print("Starting new round...") # Debugging

    # Resetar estado da rodada
    submitted_white_cards.clear()
    votes.clear()

    # Resetar flags de submissão/voto E DISTRIBUIR NOVAS MÃOS para TODOS os jogadores ATIVOS
    # Cria uma lista temporária das chaves para evitar "dictionary changed size during iteration"
    for player_ws in list(players.keys()):
        if player_ws in players: # Verifica novamente se o player ainda existe (edge case)
             players[player_ws]["submitted_this_round"] = False
             players[player_ws]["voted_this_round"] = False
             
             await send_to_client(player_ws, {"action": "get_nome"})
             # >>> CORRIGIDO/AJUSTADO: Distribuir nova mão para CADA jogador <<<
             # Garante que há cartas brancas suficientes para dar uma mão completa
             if len(players[player_ws]["hand"]) < HAND_SIZE and white_cards:
                nova_carta = random.choice(white_cards)
                players[player_ws]["hand"].append(nova_carta)
                await send_to_client(player_ws, {"action": "nova_mao", "cartas": players[player_ws]["hand"]})

             else:
                 # Tratar caso não haja cartas brancas suficientes para dar uma mão
                 print("Erro: Não há cartas brancas suficientes para dar uma mão completa!") # Debugging
                 await send_to_client(player_ws, {"action": "error", "reason": "Not enough white cards for a full hand."})
                 # Talvez terminar o jogo ou esperar mais cartas? Vamos esperar.


    # Selecionar nova carta preta
    if black_cards:
        current_black_card = random.choice(black_cards)
        print(f"New Black Card: {current_black_card}") # Debugging
        # Broadcast para avisar que uma nova rodada vai começar/está pronta
        # O cliente Pygame/Web, ao receber next_round, saberá que uma nova rodada começou.
        # A carta preta será enviada APÓS o next_round (se o cliente solicitar) ou pode ser enviada aqui também.
        await broadcast({"action": "next_round"})

        # >>> AJUSTADO: Enviar a carta preta para todos AGORA, após distribuir as mãos e o next_round <<<
        # Isso garante que todos recebam a carta preta para a nova rodada de forma sincronizada.
        # O cliente ainda pode solicitar com get_black_card se precisar.
        await broadcast({"action": "black_card", "card": current_black_card})


    else:
        # Tratar caso não haja mais cartas pretas
        print("No more black cards!") # Debugging
        await end_game(winner_ws=None) # Termina o jogo se não há mais cartas
        # O estado já será game_over via end_game


async def end_game(winner_ws=None):
    """Finaliza o jogo."""
    global game_state, start_timer_task, current_black_card
    print("Game ending...") # Debugging

    winner_address = "No winner (game ended unexpectedly)"
    final_winner_score = "N/A"

    # Encontrar o endereço e pontuação do vencedor (se houver um)
    if winner_ws and winner_ws in players:
         try:
              winner_address = str(players[winner_ws]['nome'])
              final_winner_score = players[winner_ws]["score"]
         except Exception as e:
              print(f"Erro ao obter endereço/score do vencedor: {e}")
              winner_address = "Unknown Winner"
              final_winner_score = "N/A"

    # Broadcast final de scores ANTES do game over principal, para garantir que o frontend os receba
    scores_data = {
        players[ws]["nome"]: data["score"]
        for ws, data in players.items()
    }  
    await broadcast({"action": "scores_update", "scores": scores_data})

    # Broadcast da mensagem de game over
    await broadcast({"action": "game_over", "winner": winner_address, "score": final_winner_score}) # Inclui pontuação final do vencedor

    # Atualiza o estado interno do servidor
    await update_game_state("game_over", f"Game Over! Winner: {winner_address} ({final_winner_score} pts)")

    # Cancelar qualquer timer ativo (countdown)
    if start_timer_task and not start_timer_task.done():
        try:
            start_timer_task.cancel()
            await start_timer_task # Aguarda a task ser cancelada (evita warning)
        except asyncio.CancelledError:
            pass # Já era esperado
        except Exception as e:
             print(f"Erro ao cancelar/aguardar task do timer: {e}")
             traceback.print_exc()


    # Resetar estado do jogo para aguardar novos jogadores (sem limpar clientes/players)
    # Mantém clientes e pontuações para um novo jogo com os mesmos jogadores
    submitted_white_cards.clear()
    votes.clear()
    current_black_card = None
    # As flags submitted_this_round/voted_this_round serão resetadas ao iniciar uma nova rodada.
    # As mãos serão distribuídas na próxima start_new_round.
    
    # Transiciona para o estado de espera após um breve delay para o cliente processar GAME_OVER
    await asyncio.sleep(10) # Tempo para o cliente exibir "Game Over"
    os.execv(sys.executable, [sys.executable] + sys.argv)
    # Verifica se ainda há jogadores suficientes para iniciar um novo countdown imediatamente
    if get_player_count() >= min_players:
         print("Jogadores suficientes ainda conectados. Iniciando novo countdown para novo jogo.")
         await start_countdown() # Inicia um novo countdown
    else:
         await update_game_state("waiting_for_players", f"Waiting for at least {min_players} players...") # Volta para o estado de espera


# --- WebSocket Handler ---

async def handler(websocket):
    """Lida com a conexão e as mensagens de um cliente."""
    print(f"Cliente conectado: {websocket.remote_address}") # Debugging
    

    # Adiciona o novo cliente e inicializa os dados do jogador
    # Cria um novo registro para a NOVA conexão deste websocket object
    # Inicializa a mão vazia aqui
    players[websocket] = {"nome": "","score": 0, "submitted_this_round": False, "voted_this_round": False, "hand": random.sample(white_cards, HAND_SIZE)}
    clients.add(websocket) # Adiciona ao set de clientes ATIVOS para broadcast
    print(f"Total players connected: {len(players)}") # Debugging (usando len(players) pois todos são jogadores por enquanto)


    # Informar o novo cliente sobre o estado atual do jogo e pontuações
    # Envia o estado ANTES das pontuações ou countdown, para o cliente saber o que esperar
    await send_to_client(websocket, {"action": "game_state_update", "state": game_state, "message": f"Current state: {game_state}"})
    await send_to_client(websocket, {"action": "nova_mao", "cartas": players[websocket]["hand"]})
    # Enviar pontuações atuais para o novo cliente (SEMPRE)
    scores_data = {
        players[ws]["nome"]: data["score"]
        for ws, data in players.items()
    }   
    await send_to_client(websocket, {"action": "scores_update", "scores": scores_data})
    await send_to_client(websocket, {"action": "codigo_sala", "sala": sys.argv[1]})

    # Envia info específica do estado atual
    if game_state == "starting_countdown":
         await send_to_client(websocket, {"action": "countdown", "seconds": countdown_seconds_left})
         await send_to_client(websocket, {"action": "nova_mao", "cartas": players[websocket]["hand"]})

    elif game_state in ["in_game", "round_result", "voting"]: # Inclui 'voting' e 'round_result'
         if current_black_card:
              await send_to_client(websocket, {"action": "black_card", "card": current_black_card})
         # Em 'voting', enviar cartas submetidas (não implementado para simplificar, cliente espera 'start_vote')
         # Em 'round_result', enviar resultado da rodada (não implementado, cliente espera 'round_result')

         # >>> AJUSTADO: Enviar mão do jogador ao conectar mid-game (se ele tiver uma) <<<
         # Isso é para o caso de reconexão ou join mid-round
         if players[websocket]["hand"]:
              await send_to_client(websocket, {"action": "nova_mao", "cartas": players[websocket]["hand"]})
              print(f"Enviando mão existente para novo cliente {websocket.remote_address}: {players[websocket]['hand']}") # Debugging
         # Senão, ele receberá a mão na próxima start_new_round


    # Verifica se é hora de iniciar o countdown
    # Faz essa checagem APÓS enviar o estado inicial para o novo cliente
    if game_state == "waiting_for_players" and get_player_count() >= min_players:
        await start_countdown()


    # --- Loop principal para receber mensagens ---
    # Usamos async for, que lida nativamente com ConnectionClosed levantando StopAsyncIteration
    try:
        async for message in websocket:
            data = json.loads(message)
            # print(f"Mensagem recebida de {websocket.remote_address}: {data}") # Debugging received message

            action = data.get("action")

            # Ações permitidas dependendo do estado
            # Permite get_black_card no estado 'waiting_for_black_card' também,
            # para clientes que chegam após next_round mas antes de receberem black_card 

            
            if game_state == "in_game" or (action == "get_black_card" and game_state == "waiting_for_black_card"):

                if action == "get_black_card":
                    # O cliente está pedindo a carta preta atual
                    # Responde APENAS se uma carta preta estiver definida
                    if current_black_card:
                        await send_to_client(websocket, {"action": "black_card", "card": current_black_card})
                    # else: # Debugging
                         # print(f"Received get_black_card from {websocket.remote_address} but current_black_card is None. State: {game_state}")

                elif action == "submit_white_card":
                    card_text = data.get("card")
                    # Verifica se a carta é válida, o jogador ainda não submeteu, E A CARTA ESTÁ NA MÃO DELE
                    if card_text and websocket in players:
                        print("rodou")
                        submitted_white_cards.append({"player": websocket, "card": card_text})
                        players[websocket]["submitted_this_round"] = True
                        players[websocket]["hand"].remove(card_text)  # Remover carta usada
                        print(f"Carta branca recebida. Carta: {card_text} Player: {players[websocket]}")

                        # >>> AJUSTADO: Remover a carta da mão do jogador após submeter <<<
                        
                        print(f"Card submitted by {websocket.remote_address}. Removed from hand. Total submitted: {len(submitted_white_cards)}") # Debugging


                        await broadcast({"action": "white_card_submitted", "count": len(submitted_white_cards)})

                        # Verifica se todos os jogadores ATIVOS submeteram
                        # O round de submissão termina quando o número de cartas submetidas
                        # for igual ao número de jogadores ATIVOS (que estão no dicionário players)
                        if len(submitted_white_cards) == len(players):
                             print("All active players submitted. Starting vote.") # Debugging
                             # Todos enviaram, enviar cartas para votação
                             cards_to_vote = [entry["card"] for entry in submitted_white_cards]
                             # Embaralhar a ordem das cartas para votação (para anonimato)
                             random.shuffle(cards_to_vote)
                             # Broadcasta as cartas para votação E sinaliza a mudança de estado
                             await broadcast({"action": "start_vote", "cards": cards_to_vote})
                             # O estado do jogo MUDARÁ para voting NO FRONTEND ao receber start_vote.

                elif action == "nome":
                    nome = data.get("nome")
                    print(f"Nome do {players[websocket]} é {nome}")
                    if nome:
                        players[websocket]["nome"] = nome

                elif action == "vote" and game_state == "in_game":
                    chosen_card = data.get("card")
                    # Verifica se a carta votada está entre as submetidas nesta rodada e se o jogador ainda não votou
                    # Verifica se o jogador ainda está no dicionário players
                    valid_cards_to_vote = [entry["card"] for entry in submitted_white_cards]
                    if chosen_card and chosen_card in valid_cards_to_vote and websocket in players and not players[websocket]["voted_this_round"]:
                        votes[chosen_card] = votes.get(chosen_card, 0) + 1
                        players[websocket]["voted_this_round"] = True
                        print(f"Vote received for '{chosen_card}' from {websocket.remote_address}. Total votes: {sum(votes.values())}") # Debugging

                        # Verifica se todos os jogadores ATIVOS votaram.
                        # Compara o total de votos com o número de jogadores atualmente conectados.
                        # Isso lida implicitamente com jogadores que desconectaram antes de votar.
                        if sum(votes.values()) == len(players):
                            print("All active players voted. Calculating result.") # Debugging
                            # Todos votaram, calcular vencedor
                            if votes:
                                # Encontrar a carta com mais votos. Se houver empate, random.choice
                                max_votes = max(votes.values())
                                potential_winners = [card for card, count in votes.items() if count == max_votes]
                                winner_card = random.choice(potential_winners) # Escolhe aleatoriamente em caso de empate

                                # Encontrar o jogador que submeteu a carta vencedora
                                winner_player_ws = None
                                # Itera sobre as cartas submetidas para encontrar o websocket do jogador
                                for entry in submitted_white_cards:
                                    # Usa 'is' para comparar objetos websocket, mais seguro que ==
                                    if entry["card"] == winner_card:
                                        winner_player_ws = entry["player"]
                                        break # Encontrou o jogador que submeteu a carta vencedora

                                # Verifica se o jogador vencedor ainda está conectado E está no dicionário players
                                # Um jogador desconectado não estará em 'players'
                                if winner_player_ws and winner_player_ws in players:
                                     players[winner_player_ws]["score"] += 1
                                     winner_score = players[winner_player_ws]["score"]
                                     print(f"Round winner card: '{winner_card}' by {winner_player_ws.remote_address}. New score: {winner_score}") # Debugging

                                     # Broadcasta o resultado da rodada
                                     await broadcast({
                                         "action": "round_result",
                                         "winner_card": winner_card,
                                         # Envia o endereço do vencedor (ou uma representação string)
                                         "winner_address": players[winner_player_ws]['nome'],
                                         # O score enviado aqui é o score ATUALIZADO do vencedor da rodada
                                         # Isso pode ser confuso para o frontend. Melhor enviar score_update separado.
                                         # "score": winner_score
                                     })

                                     # Broadcasta a pontuação ATUALIZADA de TODOS os jogadores APÓS o resultado da rodada
                                     scores_data = {
                                        players[ws]["nome"]: data["score"]
                                        for ws, data in players.items()
                                    }                                
                                     await broadcast({"action": "scores_update", "scores": scores_data})

                                     # Verifica se o vencedor atingiu a pontuação máxima
                                     if winner_score >= max_points:
                                         print(f"Jogador {players[winner_player_ws]['nome']} atingiu {max_points} pontos. Finalizando jogo.")
                                         await end_game(winner_player_ws) # Termina o jogo
                                     else:
                                         # Iniciar próxima rodada após uma pausa
                                         print("Round finished. Starting next round.") # Debugging
                                         await asyncio.sleep(3) # Pequena pausa para o frontend mostrar o resultado
                                         await start_new_round() # Inicia uma nova rodada
                                else:
                                     print("Erro/Edge case: Jogador que submeteu a carta vencedora desconectou antes do fim da votação.") # Debugging
                                     # O que fazer se o vencedor desconectou? Vamos iniciar uma nova rodada.
                                     # Broadcasta o resultado da rodada com informação de jogador desconectado
                                     await broadcast({"action": "round_result", "winner_card": winner_card, "winner_address": "Disconnected Player", "score": "N/A"})
                                     # Broadcasta as pontuações atuais (sem o vencedor desconectado, pois ele já foi removido de 'players' no finally anterior)
                                     scores_data = {
                                        players[ws]["nome"]: data["score"]
                                        for ws, data in players.items()
                                    }                                    
                                     await broadcast({"action": "scores_update", "scores": scores_data})
                                     await asyncio.sleep(3)
                                     await start_new_round()

                            else: # Caso não tenha votos (improvável se sum(votes.values()) > 0, mas seguro)
                                 print("Vote check passed, but no votes recorded?") # Debugging
                                 await broadcast({"action": "round_result", "winner_card": "No votes recorded", "winner_address": "N/A", "score": "N/A"})
                                 scores_data = {
                                    players[ws]["nome"]: data["score"]
                                    for ws, data in players.items()
                                }                                
                                 await broadcast({"action": "scores_update", "scores": scores_data})
                                 await asyncio.sleep(3)
                                 await start_new_round()


                    # else: # Debugging invalid vote attempt
                         # print(f"Invalid vote attempt from {websocket.remote_address}. Card: {chosen_card}, Voted before: {players[websocket]['voted_this_round'] if websocket in players else 'N/A'}, Card in list: {chosen_card in valid_cards_to_vote}")

            # else if actions allowed in other states (like get_black_card in waiting_for_black_card)
            # A lógica para get_black_card em 'waiting_for_black_card' foi movida para o if principal acima.

            # else: # Debugging ignored actions
                 # print(f"Ignorando ação '{action}' no estado '{game_state}' de {websocket.remote_address}")


    # --- Tratamento de Exceções e Limpeza Final ---
    # Este bloco try/except/finally captura exceções que ocorrem DENTRO do loop 'async for message'
    # Incluindo ConnectionClosed, que faz o loop terminar normalmente e NÃO levanta uma exceção aqui, mas vai para finally.
    except Exception as e:
        # Captura QUALQUER outra exceção inesperada durante o processamento de mensagens
        # A exceção ConnectionClosed NÃO virá para cá.
        print(f"Erro inesperado com o cliente {websocket.remote_address} durante processamento:\n")
        traceback.print_exc() # Imprime o traceback completo


    finally:
        # Este bloco é executado quando o handler task termina (loop async for concluído, exceção capturada, cancelamento)
        # O 'websocket' aqui refere-se ao cliente cuja task handler está terminando.
        print(f"Limpando dados do cliente: {websocket.remote_address}") # Debugging
        # Garantir a remoção segura do cliente dos sets e dicionários
        # Usa copy() e verifica a existência antes de remover
        client_to_remove = websocket
        if client_to_remove in clients:
            clients.remove(client_to_remove)
        # A remoção de 'players' significa que este websocket não é mais um jogador ATIVO para contagem ou lógica de rodada.
        if client_to_remove in players:
            del players[client_to_remove] # Remove do dicionário de jogadores ativos

        print(f"Clientes restantes: {len(clients)}. Jogadores restantes: {len(players)}") # Debugging

        # Verifica se o jogo deve parar ou countdown ser cancelado
        # Se o número de jogadores ATIVOS cair abaixo do mínimo
        if game_state in ["starting_countdown", "in_game", "round_result"] and get_player_count() < min_players:
            print("Número de jogadores insuficiente após desconexão. Verificando ação.") # Debugging
            if game_state == "starting_countdown" and start_timer_task and not start_timer_task.done():
                 print("Cancelando countdown devido a poucos jogadores.")
                 start_timer_task.cancel() # Cancela o timer
                 # O run_countdown_timer lidará com o estado 'waiting_for_players'
            elif game_state in ["in_game", "round_result"]:
                 print("Finalizando jogo devido a poucos jogadores.")
                 # Cria uma task separada para chamar end_game para não bloquear o finally
                 # Passa None como vencedor, pois o jogo terminou por falta de jogadores
                 asyncio.create_task(end_game(winner_ws=None))

        # Se o jogo está em game_over e jogadores suficientes ainda estão conectados, talvez reiniciar o countdown?
        # Isso já é tratado no final da função end_game.


# --- Server Startup ---

async def main(port):
    print(f"Iniciando servidor na porta {port}...")
    # Inicializa o estado do jogo
    # Use create_task para a primeira atualização de estado para não bloquear o main
    asyncio.create_task(update_game_state("waiting_for_players", f"Waiting for at least {min_players} players..."))

    # Configura e roda o servidor WebSocket
    async with websockets.serve(handler, "0.0.0.0", port):
        print("Servidor iniciado com sucesso.")
        # Mantém o servidor rodando indefinidamente
        await asyncio.Future() # Bloqueia aqui até que o loop de eventos seja interrompido

# --- Run the server ---
if __name__ == "__main__":
    try:
        import sys
        # Roda o loop de eventos asyncio
        port = int(os.environ.get("PORT", 10000))
        asyncio.run(main(port))
    except KeyboardInterrupt:
        print("Servidor encerrado manualmente (KeyboardInterrupt).")
    except Exception as e:
        print(f"Erro fatal no servidor: {e}")
        traceback.print_exc() # Imprime o traceback completo para erros na inicialização
