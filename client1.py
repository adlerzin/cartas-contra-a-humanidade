import pygame
import asyncio
import websockets
import json
import threading
import sys
import os
from typing import Optional, List, Dict, Any

# Inicialização do Pygame
pygame.init()

# Configurações da tela
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Cards Against Humanity")

# Cores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
PURPLE = (128, 0, 128)

# Fontes
font_large = pygame.font.Font(None, 48)
font_medium = pygame.font.Font(None, 32)
font_small = pygame.font.Font(None, 24)

class GameClient:
    def __init__(self):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = True
        self.connected = False
        
        # Estado do jogo
        self.game_state = "disconnected"
        self.player_name = ""
        self.room_code = ""
        self.hand = []
        self.current_black_card = ""
        self.scores = {}
        self.countdown = 0
        self.submitted_count = 0
        self.voting_cards = []
        self.selected_card_index = -1
        self.selected_vote_index = -1
        self.round_result = {}
        self.game_message = ""
        
        # UI
        self.input_text = ""
        self.input_active = False
        self.input_type = "name"  # "name", "room", "none"
        
        # Thread para WebSocket
        self.ws_thread = None
        self.websocket_loop: Optional[asyncio.AbstractEventLoop] = None # Adicionado para armazenar o loop de eventos
        
    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Quebra texto em múltiplas linhas se necessário"""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
        
        if current_line:
            lines.append(current_line.strip())
            
        return lines
    
    def draw_card(self, text: str, x: int, y: int, width: int, height: int, 
                  color: tuple, selected: bool = False):
        """Desenha uma carta na tela"""
        # Borda da carta
        border_color = YELLOW if selected else BLACK
        border_width = 3 if selected else 1
        
        pygame.draw.rect(screen, border_color, (x-2, y-2, width+4, height+4))
        pygame.draw.rect(screen, color, (x, y, width, height))
        
        # Texto da carta
        lines = self.wrap_text(text, font_small, width - 20)
        line_height = font_small.get_height()
        total_height = len(lines) * line_height
        start_y = y + (height - total_height) // 2
        
        text_color = WHITE if color == BLACK else BLACK
        
        for i, line in enumerate(lines):
            text_surface = font_small.render(line, True, text_color)
            text_rect = text_surface.get_rect()
            text_rect.centerx = x + width // 2
            text_rect.y = start_y + i * line_height
            screen.blit(text_surface, text_rect)
    
    def draw_button(self, text: str, x: int, y: int, width: int, height: int, 
                   color: tuple = LIGHT_GRAY, text_color: tuple = BLACK) -> pygame.Rect:
        """Desenha um botão e retorna seu rect"""
        button_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(screen, color, button_rect)
        pygame.draw.rect(screen, BLACK, button_rect, 2)
        
        text_surface = font_medium.render(text, True, text_color)
        text_rect = text_surface.get_rect(center=button_rect.center)
        screen.blit(text_surface, text_rect)
        
        return button_rect
    
    def draw_input_box(self, x: int, y: int, width: int, height: int, 
                      text: str, active: bool) -> pygame.Rect:
        """Desenha uma caixa de input"""
        input_rect = pygame.Rect(x, y, width, height)
        color = WHITE if active else LIGHT_GRAY
        pygame.draw.rect(screen, color, input_rect)
        pygame.draw.rect(screen, BLACK, input_rect, 2)
        
        text_surface = font_medium.render(text, True, BLACK)
        screen.blit(text_surface, (x + 5, y + 5))
        
        if active:
            cursor_x = x + 5 + text_surface.get_width()
            pygame.draw.line(screen, BLACK, (cursor_x, y + 5), (cursor_x, y + height - 5), 2)
        
        return input_rect
    
    def draw_connection_screen(self):
        """Tela de conexão inicial"""
        screen.fill(WHITE)
        
        # Título
        title = font_large.render("Cards Against Humanity", True, BLACK)
        title_rect = title.get_rect(center=(SCREEN_WIDTH//2, 100))
        screen.blit(title, title_rect)
        
        if self.input_type == "name":
            # Input do nome
            prompt = font_medium.render("Digite seu nome:", True, BLACK)
            screen.blit(prompt, (SCREEN_WIDTH//2 - 100, 200))
            
            self.input_rect = self.draw_input_box(SCREEN_WIDTH//2 - 150, 240, 300, 40, 
                                                 self.input_text, self.input_active)
            
            # Botão confirmar
            self.confirm_button = self.draw_button("OK", SCREEN_WIDTH//2 - 50, 300, 100, 40)
            
        elif self.input_type == "room":
            # Input do código da sala
            prompt = font_medium.render("Digite o código da sala:", True, BLACK)
            screen.blit(prompt, (SCREEN_WIDTH//2 - 120, 200))
            
            self.input_rect = self.draw_input_box(SCREEN_WIDTH//2 - 150, 240, 300, 40, 
                                                 self.input_text, self.input_active)
            
            # Botão conectar
            self.connect_button = self.draw_button("Conectar", SCREEN_WIDTH//2 - 60, 300, 120, 40)
    
    def draw_waiting_screen(self):
        """Tela de espera por jogadores"""
        screen.fill(WHITE)
        
        # Título
        title = font_large.render("Aguardando Jogadores", True, BLACK)
        title_rect = title.get_rect(center=(SCREEN_WIDTH//2, 150))
        screen.blit(title, title_rect)
        
        # Código da sala
        if self.room_code:
            room_text = font_medium.render(f"Sala: {self.room_code}", True, BLACK)
            room_rect = room_text.get_rect(center=(SCREEN_WIDTH//2, 200))
            screen.blit(room_text, room_rect)
        
        # Mensagem do jogo
        if self.game_message:
            msg_text = font_medium.render(self.game_message, True, BLACK)
            msg_rect = msg_text.get_rect(center=(SCREEN_WIDTH//2, 250))
            screen.blit(msg_text, msg_rect)
        
        # Pontuações
        if self.scores:
            y_offset = 300
            scores_title = font_medium.render("Jogadores:", True, BLACK)
            screen.blit(scores_title, (SCREEN_WIDTH//2 - 50, y_offset))
            y_offset += 40
            
            for name, score in self.scores.items():
                if name:  # Só mostra jogadores com nome
                    score_text = font_small.render(f"{name}: {score} pontos", True, BLACK)
                    screen.blit(score_text, (SCREEN_WIDTH//2 - 100, y_offset))
                    y_offset += 30
    
    def draw_countdown_screen(self):
        """Tela de countdown"""
        screen.fill(WHITE)
        
        # Countdown
        countdown_text = font_large.render(f"Começando em: {self.countdown}", True, RED)
        countdown_rect = countdown_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        screen.blit(countdown_text, countdown_rect)
        
        # Pontuações
        if self.scores:
            y_offset = SCREEN_HEIGHT//2 + 100
            for name, score in self.scores.items():
                if name:
                    score_text = font_small.render(f"{name}: {score} pontos", True, BLACK)
                    score_rect = score_text.get_rect(center=(SCREEN_WIDTH//2, y_offset))
                    screen.blit(score_text, score_rect)
                    y_offset += 30
    
    def draw_game_screen(self):
        """Tela principal do jogo"""
        screen.fill(WHITE)
        
        # Carta preta no topo
        if self.current_black_card:
            self.draw_card(self.current_black_card, SCREEN_WIDTH//2 - 200, 20, 400, 120, BLACK)
        
        # Pontuações no canto superior direito
        if self.scores:
            y_offset = 20
            for name, score in self.scores.items():
                if name:
                    score_text = font_small.render(f"{name}: {score}", True, BLACK)
                    screen.blit(score_text, (SCREEN_WIDTH - 200, y_offset))
                    y_offset += 25
        
        # Cartas submetidas (contador)
        if hasattr(self, 'submitted_count') and self.submitted_count > 0:
            submitted_text = font_medium.render(f"Cartas submetidas: {self.submitted_count}", True, BLACK)
            screen.blit(submitted_text, (20, 160))
        
        # Mão do jogador (cartas brancas)
        if self.hand:
            cards_per_row = 4
            card_width = 180
            card_height = 120
            card_spacing = 20
            start_x = (SCREEN_WIDTH - (cards_per_row * card_width + (cards_per_row - 1) * card_spacing)) // 2
            start_y = SCREEN_HEIGHT - card_height - 50
            
            for i, card in enumerate(self.hand):
                row = i // cards_per_row
                col = i % cards_per_row
                x = start_x + col * (card_width + card_spacing)
                y = start_y - row * (card_height + card_spacing)
                
                selected = (i == self.selected_card_index)
                self.draw_card(card, x, y, card_width, card_height, WHITE, selected)
        
        # Botão de submeter carta
        if self.selected_card_index != -1:
            self.submit_button = self.draw_button("Submeter Carta", SCREEN_WIDTH//2 - 80, 
                                                 SCREEN_HEIGHT - 200, 160, 40, GREEN)
    
    def draw_voting_screen(self):
        """Tela de votação"""
        screen.fill(WHITE)
        
        # Carta preta
        if self.current_black_card:
            self.draw_card(self.current_black_card, SCREEN_WIDTH//2 - 200, 20, 400, 120, BLACK)
        
        # Título da votação
        vote_title = font_medium.render("Vote na melhor resposta:", True, BLACK)
        vote_rect = vote_title.get_rect(center=(SCREEN_WIDTH//2, 160))
        screen.blit(vote_title, vote_rect)
        
        # Cartas para votação
        if self.voting_cards:
            cards_per_row = 3
            card_width = 200
            card_height = 120
            card_spacing = 20
            start_x = (SCREEN_WIDTH - (cards_per_row * card_width + (cards_per_row - 1) * card_spacing)) // 2
            start_y = 200
            
            for i, card in enumerate(self.voting_cards):
                row = i // cards_per_row
                col = i % cards_per_row
                x = start_x + col * (card_width + card_spacing)
                y = start_y + row * (card_height + card_spacing)
                
                selected = (i == self.selected_vote_index)
                self.draw_card(card, x, y, card_width, card_height, WHITE, selected)
        
        # Botão de votar
        if self.selected_vote_index != -1:
            self.vote_button = self.draw_button("Votar", SCREEN_WIDTH//2 - 50, 
                                               SCREEN_HEIGHT - 100, 100, 40, BLUE)
    
    def draw_result_screen(self):
        """Tela de resultado da rodada"""
        screen.fill(WHITE)
        
        # Carta preta
        if self.current_black_card:
            self.draw_card(self.current_black_card, SCREEN_WIDTH//2 - 200, 20, 400, 120, BLACK)
        
        # Resultado
        if self.round_result:
            winner_card = self.round_result.get("winner_card", "")
            winner_name = self.round_result.get("winner_address", "")
            
            # Carta vencedora
            result_text = font_medium.render("Carta Vencedora:", True, BLACK)
            result_rect = result_text.get_rect(center=(SCREEN_WIDTH//2, 160))
            screen.blit(result_text, result_rect)
            
            self.draw_card(winner_card, SCREEN_WIDTH//2 - 200, 200, 400, 120, YELLOW)
            
            # Vencedor
            winner_text = font_medium.render(f"Vencedor: {winner_name}", True, GREEN)
            winner_rect = winner_text.get_rect(center=(SCREEN_WIDTH//2, 350))
            screen.blit(winner_text, winner_rect)
        
        # Pontuações atualizadas
        if self.scores:
            y_offset = 400
            scores_title = font_medium.render("Pontuações:", True, BLACK)
            scores_rect = scores_title.get_rect(center=(SCREEN_WIDTH//2, y_offset))
            screen.blit(scores_title, scores_rect)
            y_offset += 40
            
            for name, score in self.scores.items():
                if name:
                    score_text = font_small.render(f"{name}: {score} pontos", True, BLACK)
                    score_rect = score_text.get_rect(center=(SCREEN_WIDTH//2, y_offset))
                    screen.blit(score_text, score_rect)
                    y_offset += 30
    
    def draw_game_over_screen(self):
        """Tela de fim de jogo"""
        screen.fill(WHITE)
        
        # Título
        title = font_large.render("Fim de Jogo!", True, RED)
        title_rect = title.get_rect(center=(SCREEN_WIDTH//2, 150))
        screen.blit(title, title_rect)
        
        # Vencedor
        if self.round_result:
            winner_name = self.round_result.get("winner", "")
            winner_score = self.round_result.get("score", "")
            winner_text = font_medium.render(f"Vencedor: {winner_name} ({winner_score} pontos)", True, GREEN)
            winner_rect = winner_text.get_rect(center=(SCREEN_WIDTH//2, 220))
            screen.blit(winner_text, winner_rect)
        
        # Pontuações finais
        if self.scores:
            y_offset = 300
            scores_title = font_medium.render("Pontuações Finais:", True, BLACK)
            scores_rect = scores_title.get_rect(center=(SCREEN_WIDTH//2, y_offset))
            screen.blit(scores_title, scores_rect)
            y_offset += 40
            
            # Ordena por pontuação
            sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
            for name, score in sorted_scores:
                if name:
                    score_text = font_small.render(f"{name}: {score} pontos", True, BLACK)
                    score_rect = score_text.get_rect(center=(SCREEN_WIDTH//2, y_offset))
                    screen.blit(score_text, score_rect)
                    y_offset += 30
        
        # Botão de nova partida
        self.new_game_button = self.draw_button("Nova Partida", SCREEN_WIDTH//2 - 80, 
                                               SCREEN_HEIGHT - 100, 160, 40, GREEN)
    
    def draw(self):
        """Função principal de desenho"""
        if self.game_state == "disconnected":
            self.draw_connection_screen()
        elif self.game_state == "waiting_for_players":
            self.draw_waiting_screen()
        elif self.game_state == "starting_countdown":
            self.draw_countdown_screen()
        elif self.game_state == "in_game":
            if self.voting_cards:
                self.draw_voting_screen()
            else:
                self.draw_game_screen()
        elif self.game_state == "round_result":
            self.draw_result_screen()
        elif self.game_state == "game_over":
            self.draw_game_over_screen()
        
        pygame.display.flip()
    
    def handle_click(self, pos):
        """Lida com cliques do mouse"""
        if self.game_state == "disconnected":
            if self.input_type == "name":
                if hasattr(self, 'input_rect') and self.input_rect.collidepoint(pos):
                    self.input_active = True
                elif hasattr(self, 'confirm_button') and self.confirm_button.collidepoint(pos):
                    if self.input_text.strip():
                        self.player_name = self.input_text.strip()
                        self.input_text = ""
                        self.input_type = "room"
                        self.input_active = True
            
            elif self.input_type == "room":
                if hasattr(self, 'input_rect') and self.input_rect.collidepoint(pos):
                    self.input_active = True
                elif hasattr(self, 'connect_button') and self.connect_button.collidepoint(pos):
                    if self.input_text.strip():
                        self.room_code = self.input_text.strip()
                        self.connect_to_server()
        
        elif self.game_state == "in_game":
            if not self.voting_cards:  # Fase de submissão
                # Clique nas cartas da mão
                if self.hand:
                    cards_per_row = 4
                    card_width = 180
                    card_height = 120
                    card_spacing = 20
                    start_x = (SCREEN_WIDTH - (cards_per_row * card_width + (cards_per_row - 1) * card_spacing)) // 2
                    start_y = SCREEN_HEIGHT - card_height - 50
                    
                    for i, card in enumerate(self.hand):
                        row = i // cards_per_row
                        col = i % cards_per_row
                        x = start_x + col * (card_width + card_spacing)
                        y = start_y - row * (card_height + card_spacing)
                        
                        card_rect = pygame.Rect(x, y, card_width, card_height)
                        if card_rect.collidepoint(pos):
                            self.selected_card_index = i
                            break
                
                # Botão de submeter
                if (hasattr(self, 'submit_button') and 
                    self.submit_button.collidepoint(pos) and 
                    self.selected_card_index != -1):
                    self.submit_card()
            
            else:  # Fase de votação
                # Clique nas cartas de votação
                cards_per_row = 3
                card_width = 200
                card_height = 120
                card_spacing = 20
                start_x = (SCREEN_WIDTH - (cards_per_row * card_width + (cards_per_row - 1) * card_spacing)) // 2
                start_y = 200
                
                for i, card in enumerate(self.voting_cards):
                    row = i // cards_per_row
                    col = i % cards_per_row
                    x = start_x + col * (card_width + card_spacing)
                    y = start_y + row * (card_height + card_spacing)
                    
                    card_rect = pygame.Rect(x, y, card_width, card_height)
                    if card_rect.collidepoint(pos):
                        self.selected_vote_index = i
                        break
                
                # Botão de votar
                if (hasattr(self, 'vote_button') and 
                    self.vote_button.collidepoint(pos) and 
                    self.selected_vote_index != -1):
                    self.vote_card()
        
        elif self.game_state == "game_over":
            if hasattr(self, 'new_game_button') and self.new_game_button.collidepoint(pos):
                self.restart_game()
    
    def handle_keydown(self, event):
        """Lida com teclas pressionadas"""
        if self.input_active:
            if event.key == pygame.K_RETURN:
                if self.input_type == "name" and self.input_text.strip():
                    self.player_name = self.input_text.strip()
                    self.input_text = ""
                    self.input_type = "room"
                elif self.input_type == "room" and self.input_text.strip():
                    self.room_code = self.input_text.strip()
                    self.connect_to_server()
            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            else:
                self.input_text += event.unicode
    
    def connect_to_server(self):
        """Conecta ao servidor WebSocket"""
        if self.ws_thread is None or not self.ws_thread.is_alive():
            self.ws_thread = threading.Thread(target=self.run_websocket)
            self.ws_thread.daemon = True
            self.ws_thread.start()
    
    def run_websocket(self):
        """Executa o cliente WebSocket em thread separada"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.websocket_loop = loop # Armazena o loop de eventos
        loop.run_until_complete(self.websocket_client())
    
    async def websocket_client(self):
        """Cliente WebSocket principal"""
        try:
            # Conecta ao servidor (ajuste a URL conforme necessário)
            uri = f"ws://localhost:10000"  # ou use o IP do servidor
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                self.connected = True
                
                # Envia o nome do jogador
                await websocket.send(json.dumps({
                    "action": "nome",
                    "nome": self.player_name
                }))
                
                # Loop para receber mensagens
                async for message in websocket:
                    data = json.loads(message)
                    await self.handle_server_message(data)
                    
        except Exception as e:
            print(f"Erro na conexão WebSocket: {e}")
            self.connected = False
            self.game_state = "disconnected"
    
    async def handle_server_message(self, data):
        """Lida com mensagens do servidor"""
        action = data.get("action")
        
        if action == "game_state_update":
            self.game_state = data.get("state", "disconnected")
            self.game_message = data.get("message", "")
        
        elif action == "get_nome":
            await self.websocket.send(json.dumps({
                "action": "nome",
                "nome": self.player_name
            }))
        
        elif action == "nova_mao":
            self.hand = data.get("cartas", [])
            self.selected_card_index = -1
        
        elif action == "scores_update":
            self.scores = data.get("scores", {})
        
        elif action == "codigo_sala":
            self.room_code = data.get("sala", "")
        
        elif action == "countdown":
            self.countdown = data.get("seconds", 0)
        
        elif action == "black_card":
            self.current_black_card = data.get("card", "")
        
        elif action == "white_card_submitted":
            self.submitted_count = data.get("count", 0)
        
        elif action == "start_vote":
            self.voting_cards = data.get("cards", [])
            self.selected_vote_index = -1
        
        elif action == "round_result":
            self.round_result = {
                "winner_card": data.get("winner_card", ""),
                "winner_address": data.get("winner_address", "")
            }
            self.game_state = "round_result"
            self.voting_cards = []
            # Limpa resultado após alguns segundos
            threading.Timer(3.0, self.clear_round_result).start()
        
        elif action == "game_over":
            self.round_result = {
                "winner": data.get("winner", ""),
                "score": data.get("score", "")
            }
            self.game_state = "game_over"
        
        elif action == "next_round":
            self.voting_cards = []
            self.selected_card_index = -1
            self.selected_vote_index = -1
            self.submitted_count = 0
    
    def clear_round_result(self):
        """Limpa o resultado da rodada"""
        if self.game_state == "round_result":
            self.game_state = "in_game"
    
    def submit_card(self):
        """Submete a carta selecionada"""
        if (self.selected_card_index != -1 and 
            self.selected_card_index < len(self.hand) and 
            self.websocket and
            self.websocket_loop): # Verifica se o loop está disponível
            
            card = self.hand[self.selected_card_index]
            
            async def send_submit():
                await self.websocket.send(json.dumps({
                    "action": "submit_white_card",
                    "card": card
                }))
            
            asyncio.run_coroutine_threadsafe(send_submit(), self.websocket_loop) # Usa o loop correto
            self.selected_card_index = -1
    
    def vote_card(self):
        """Vota na carta selecionada"""
        if (self.selected_vote_index != -1 and 
            self.selected_vote_index < len(self.voting_cards) and 
            self.websocket and
            self.websocket_loop): # Verifica se o loop está disponível
            
            card = self.voting_cards[self.selected_vote_index]
            
            async def send_vote():
                await self.websocket.send(json.dumps({
                    "action": "vote",
                    "card": card
                }))
            
            asyncio.run_coroutine_threadsafe(send_vote(), self.websocket_loop) # Usa o loop correto
            self.selected_vote_index = -1
    
    def restart_game(self):
        """Reinicia o jogo"""
        self.game_state = "waiting_for_players"
        self.round_result = {}
        self.voting_cards = []
        self.selected_card_index = -1
        self.selected_vote_index = -1
    
    def run(self):
        """Loop principal do jogo"""
        clock = pygame.time.Clock()
        
        while self.running:
            # Eventos
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Botão esquerdo
                        self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event)
            
            # Desenhar
            self.draw()
            clock.tick(60)
        
        # Cleanup
        if self.websocket and self.websocket_loop: # Verifica se o loop está disponível
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.websocket_loop) # Usa o loop correto
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    client = GameClient()
    client.run()