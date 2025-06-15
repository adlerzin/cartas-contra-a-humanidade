import pygame
import asyncio
import websockets
import json
import threading
import sys
import os
import time # Para animações baseadas em tempo
from typing import Optional, List, Dict, Any, Tuple

# Inicialização do Pygame
pygame.init()

# Configurações da tela
# Definindo uma resolução 16:9 padrão para iniciar, pode ser ajustada ou fullscreen
SCREEN_WIDTH = 1366
SCREEN_HEIGHT = 768
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Cards Against Humanity")
# pygame.display.toggle_fullscreen() # Descomente para iniciar em fullscreen

# Paleta de Cores (Cores mais agradáveis)
COLOR_BACKGROUND = (30, 30, 30) # Cinza escuro para o fundo
COLOR_CARD_WHITE = (240, 240, 240) # Branco quase puro para cartas brancas
COLOR_CARD_BLACK = (40, 40, 40) # Preto profundo para cartas pretas
COLOR_TEXT_LIGHT = (250, 250, 250) # Texto claro
COLOR_TEXT_DARK = (20, 20, 20) # Texto escuro
COLOR_BUTTON_NORMAL = (70, 70, 70) # Botões em cinza médio
COLOR_BUTTON_HOVER = (90, 90, 90) # Hover dos botões
COLOR_BUTTON_ACTIVE = (120, 120, 120) # Botões clicados
COLOR_SELECTION = (255, 200, 0) # Amarelo vibrante para seleção
COLOR_SUCCESS = (50, 205, 50) # Verde para sucesso (ex: voto)
COLOR_ERROR = (220, 20, 60) # Vermelho para erro
COLOR_BORDER = (100, 100, 100) # Cor da borda geral
DARK_GRAY = (64, 64, 64) # Adicionado: Cor DARK_GRAY que estava faltando

# Fontes (usando uma fonte padrão mais moderna, se disponível, ou fallback)
try:
    # Prioriza Bahnschrift, Arial, senão None (fallback Pygame)
    font_path = pygame.font.match_font('bahnschrift') or pygame.font.match_font('arial') or None
    font_xlarge = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.08)) # ~60px
    font_large = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.06))  # ~45px
    font_medium = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.04)) # ~30px
    font_small = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.03))  # ~20px
    font_card_text = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.025)) # ~18px
except Exception:
    # Fallback para fontes padrão do Pygame
    print("Aviso: Não foi possível carregar fontes customizadas. Usando fontes padrão do Pygame.")
    font_xlarge = pygame.font.Font(None, 60)
    font_large = pygame.font.Font(None, 45)
    font_medium = pygame.font.Font(None, 30)
    font_small = pygame.font.Font(None, 20)
    font_card_text = pygame.font.Font(None, 18)

# Tamanhos de cartas e margens (proporcionais à tela)
CARD_ASPECT_RATIO = 0.7 # Largura / Altura (Ex: 0.7 para 70% da altura)
CARD_HEIGHT_REGULAR = int(SCREEN_HEIGHT * 0.30) # ~230px
CARD_WIDTH_REGULAR = int(CARD_HEIGHT_REGULAR * CARD_ASPECT_RATIO)

CARD_HEIGHT_HAND = int(SCREEN_HEIGHT * 0.25) # ~190px
CARD_WIDTH_HAND = int(CARD_HEIGHT_HAND * CARD_ASPECT_RATIO)

CARD_HEIGHT_VOTE = int(SCREEN_HEIGHT * 0.28) # ~215px
CARD_WIDTH_VOTE = int(CARD_HEIGHT_VOTE * CARD_ASPECT_RATIO)

CARD_MARGIN = int(SCREEN_WIDTH * 0.015) # Margem entre cartas proporcional

# Sombra para as cartas (melhora o 3D)
SHADOW_OFFSET = 5
SHADOW_COLOR = (10, 10, 10, 150) # Quase preto, semi-transparente

# Animação de mensagem
MESSAGE_DISPLAY_TIME = 3.0 # Segundos
MESSAGE_FADE_DURATION = 0.5 # Segundos de fade

class AnimatedMessage:
    def __init__(self, text: str, color: Tuple[int, int, int], font: pygame.font.Font, duration: float, fade_duration: float):
        self.text = text
        self.color = color
        self.font = font
        self.start_time = time.time()
        self.duration = duration
        self.fade_duration = fade_duration
        self.alpha = 255 # Opacidade inicial (começa totalmente visível, pode adicionar fade-in inicial se desejar)

    def update(self):
        elapsed = time.time() - self.start_time
        if elapsed > self.duration - self.fade_duration:
            # Fase de fade-out
            progress = (elapsed - (self.duration - self.fade_duration)) / self.fade_duration
            self.alpha = max(0, 255 - int(255 * progress))
        elif elapsed < self.fade_duration:
            # Fase de fade-in (opcional, pode começar no 255)
            progress = elapsed / self.fade_duration
            self.alpha = min(255, int(255 * progress))
        else:
            self.alpha = 255 # Totalmente visível

    def draw(self, surface, center_pos: Tuple[int, int]):
        if self.alpha > 0: # Desenha apenas se for visível
            text_surface = self.font.render(self.text, True, self.color)
            text_surface.set_alpha(self.alpha) # Aplica a opacidade
            text_rect = text_surface.get_rect(center=center_pos)
            surface.blit(text_surface, text_rect)

    def is_finished(self) -> bool:
        return time.time() - self.start_time > self.duration

class GameClient:
    def __init__(self):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = True
        self.connected = False
        
        # Estado do jogo
        self.game_state = "disconnected" # "disconnected", "waiting_for_players", "starting_countdown", "in_game", "round_result", "game_over"
        self.player_name = ""
        self.room_code = ""
        self.hand = [] # Cartas brancas na mão do jogador
        self.current_black_card = "" # Carta preta atual
        self.scores = {} # {player_name: score}
        self.countdown = 0 # Tempo restante para o countdown
        self.submitted_count = 0 # Quantas cartas já foram submetidas
        self.voting_cards = [] # Cartas brancas para votação
        self.selected_card_index = -1 # Índice da carta branca selecionada na mão
        self.selected_vote_index = -1 # Índice da carta branca selecionada para votar
        self.round_result = {} # Resultado da rodada (vencedor, carta)
        
        # Flags para controlar ações por rodada
        self.has_submitted_this_round = False
        self.has_voted_this_round = False
        
        # Animação de cartas
        self.card_animations: List[Dict[str, Any]] = [] # [{"card": text, "start_pos": (x,y), "end_pos": (x,y), "start_time": time, "duration": float}]
        self.selected_card_anim_scale = 1.0 # Escala para animação de seleção
        self.vote_card_anim_scale = 1.0 # Escala para animação de seleção de voto
        
        # UI
        self.input_text = ""
        self.input_active = False
        self.input_type = "name"  # "name", "room"
        
        # Mensagens temporárias
        self.current_message: Optional[AnimatedMessage] = None
        
        # Thread para WebSocket
        self.ws_thread = None
        self.websocket_loop: Optional[asyncio.AbstractEventLoop] = None # Armazena o loop de eventos da thread do WebSocket
        
        # Botões para interatividade
        self.buttons: Dict[str, pygame.Rect] = {} # Dicionário para armazenar Rects dos botões
        
        # Posições e tamanhos relativos
        self.header_height = int(SCREEN_HEIGHT * 0.13) # Altura do cabeçalho
        self.scoreboard_width = int(SCREEN_WIDTH * 0.18) # Largura do placar
    
    def set_message(self, text: str, color: Tuple[int, int, int] = COLOR_TEXT_LIGHT, 
                    duration: float = MESSAGE_DISPLAY_TIME, fade_duration: float = MESSAGE_FADE_DURATION):
        self.current_message = AnimatedMessage(text, color, font_medium, duration, fade_duration)

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Quebra texto em múltiplas linhas para caber na largura máxima."""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            # Adiciona a palavra com um espaço para testar a largura
            test_line = current_line + word + " "
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                # Se a linha atual não couber, adicione-a e comece uma nova
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
        
        # Adiciona a última linha
        if current_line:
            lines.append(current_line.strip())
            
        return lines
    
    def draw_text_multiline(self, surface, text, color, rect, font, align_x="center", align_y="center"):
        """Desenha texto multi-linha com alinhamento."""
        lines = self.wrap_text(text, font, rect.width - 20) # 20px de padding interno
        line_height = font.get_height()
        
        total_text_height = len(lines) * line_height
        
        start_y = rect.top + 10 # Default padding
        if align_y == "center":
            start_y = rect.centery - total_text_height // 2
        elif align_y == "bottom":
            start_y = rect.bottom - total_text_height - 10 # Default padding
        
        for i, line in enumerate(lines):
            text_surface = font.render(line, True, color)
            text_rect = text_surface.get_rect()
            
            if align_x == "center":
                text_rect.centerx = rect.centerx
            elif align_x == "left":
                text_rect.left = rect.left + 10 # 10px padding
            elif align_x == "right":
                text_rect.right = rect.right - 10 # 10px padding
            
            text_rect.y = start_y + i * line_height
            surface.blit(text_surface, text_rect)

    def draw_card(self, text: str, x: int, y: int, width: int, height: int, 
                  is_black: bool, selected: bool = False, current_scale: float = 1.0):
        """Desenha uma carta na tela com sombra e bordas arredondadas."""
        card_color = COLOR_CARD_BLACK if is_black else COLOR_CARD_WHITE
        text_color = COLOR_TEXT_LIGHT if is_black else COLOR_TEXT_DARK
        border_color = COLOR_SELECTION if selected else COLOR_BORDER
        
        # Aplica a escala para animação de seleção
        scaled_width = int(width * current_scale)
        scaled_height = int(height * current_scale)
        scaled_x = x + (width - scaled_width) // 2
        scaled_y = y + (height - scaled_height) // 2

        # Desenha a sombra
        shadow_surface = pygame.Surface((scaled_width, scaled_height), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surface, SHADOW_COLOR, (0, 0, scaled_width, scaled_height), 0, 10) # Arredondamento
        screen.blit(shadow_surface, (scaled_x + SHADOW_OFFSET, scaled_y + SHADOW_OFFSET))
        
        # Desenha o corpo da carta
        card_rect = pygame.Rect(scaled_x, scaled_y, scaled_width, scaled_height)
        pygame.draw.rect(screen, card_color, card_rect, 0, 10) # Arredondamento
        
        # Desenha a borda
        pygame.draw.rect(screen, border_color, card_rect, 3, 10) # Espessura 3, arredondamento
        
        # Desenha o texto da carta (ajusta para a escala atual da carta)
        self.draw_text_multiline(screen, text, text_color, card_rect, font_card_text)
    
    def draw_button(self, text: str, x: int, y: int, width: int, height: int, 
                   color: tuple = COLOR_BUTTON_NORMAL, text_color: tuple = COLOR_TEXT_LIGHT, 
                   hover_color: tuple = COLOR_BUTTON_HOVER, disabled: bool = False) -> pygame.Rect:
        """Desenha um botão e retorna seu rect. Lida com hover e estado desabilitado."""
        button_rect = pygame.Rect(x, y, width, height)
        current_color = color
        
        if disabled:
            current_color = (current_color[0] // 2, current_color[1] // 2, current_color[2] // 2) # Escurece a cor
            text_color = (text_color[0] // 2, text_color[1] // 2, text_color[2] // 2) # Escurece o texto
        else:
            mouse_pos = pygame.mouse.get_pos()
            if button_rect.collidepoint(mouse_pos):
                current_color = hover_color
        
        pygame.draw.rect(screen, current_color, button_rect, 0, 5) # Arredondamento
        pygame.draw.rect(screen, COLOR_BORDER, button_rect, 2, 5) # Borda
        
        text_surface = font_medium.render(text, True, text_color)
        text_rect = text_surface.get_rect(center=button_rect.center)
        screen.blit(text_surface, text_rect)
        
        return button_rect
    
    def draw_input_box(self, x: int, y: int, width: int, height: int, 
                      text: str, active: bool) -> pygame.Rect:
        """Desenha uma caixa de input com estilo moderno."""
        input_rect = pygame.Rect(x, y, width, height)
        color = COLOR_BUTTON_ACTIVE if active else COLOR_BUTTON_NORMAL
        border_color = COLOR_SELECTION if active else COLOR_BORDER
        
        pygame.draw.rect(screen, color, input_rect, 0, 5) # Arredondamento
        pygame.draw.rect(screen, border_color, input_rect, 2, 5) # Borda
        
        text_surface = font_medium.render(text, True, COLOR_TEXT_LIGHT)
        screen.blit(text_surface, (x + int(width * 0.02), y + (height - text_surface.get_height()) // 2))
        
        if active:
            cursor_x = x + int(width * 0.02) + text_surface.get_width()
            pygame.draw.line(screen, COLOR_TEXT_LIGHT, (cursor_x, y + 5), (cursor_x, y + height - 5), 2)
        
        return input_rect
    
    def draw_score_board(self, x: int, y: int, width: int, height: int):
        """Desenha um placar com nomes e pontuações."""
        board_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(screen, COLOR_BUTTON_NORMAL, board_rect, 0, 10)
        pygame.draw.rect(screen, COLOR_BORDER, board_rect, 2, 10)
        
        title_surface = font_small.render("PLACAR", True, COLOR_TEXT_LIGHT)
        title_rect = title_surface.get_rect(centerx=board_rect.centerx, top=y + int(height * 0.03))
        screen.blit(title_surface, title_rect)
        
        y_offset = y + int(height * 0.15)
        # Ordenar jogadores por score (maior para menor)
        sorted_scores = sorted(self.scores.items(), key=lambda item: item[1], reverse=True)

        for name, score in sorted_scores:
            if name:
                score_text = font_small.render(f"{name}: {score}", True, COLOR_TEXT_LIGHT)
                score_rect = score_text.get_rect(left=x + int(width * 0.05), centery=y_offset)
                screen.blit(score_text, score_rect)
                y_offset += int(height * 0.05) # Espaçamento
    
    def draw_header(self, title: str):
        """Desenha um cabeçalho para as telas."""
        header_rect = pygame.Rect(0, 0, SCREEN_WIDTH, self.header_height)
        pygame.draw.rect(screen, DARK_GRAY, header_rect)
        pygame.draw.line(screen, COLOR_BORDER, (0, self.header_height), (SCREEN_WIDTH, self.header_height), 2)
        
        title_surface = font_xlarge.render(title, True, COLOR_TEXT_LIGHT)
        title_rect = title_surface.get_rect(center=(SCREEN_WIDTH//2, self.header_height // 2))
        screen.blit(title_surface, title_rect)

        player_name_surface = font_small.render(f"Você: {self.player_name}", True, COLOR_TEXT_LIGHT)
        screen.blit(player_name_surface, (int(SCREEN_WIDTH * 0.015), int(SCREEN_HEIGHT * 0.02)))

        if self.room_code:
            room_code_surface = font_small.render(f"Sala: {self.room_code}", True, COLOR_TEXT_LIGHT)
            room_code_rect = room_code_surface.get_rect(right=SCREEN_WIDTH - int(SCREEN_WIDTH * 0.015), top=int(SCREEN_HEIGHT * 0.02))
            screen.blit(room_code_surface, room_code_rect)


    def draw_connection_screen(self):
        """Tela de conexão inicial"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Conectar ao Jogo")
        
        center_x = SCREEN_WIDTH // 2
        input_box_width = int(SCREEN_WIDTH * 0.25)
        input_box_height = int(SCREEN_HEIGHT * 0.06)
        button_width = int(SCREEN_WIDTH * 0.12)
        button_height = int(SCREEN_HEIGHT * 0.06)
        
        if self.input_type == "name":
            prompt = font_medium.render("Digite seu nome:", True, COLOR_TEXT_LIGHT)
            prompt_rect = prompt.get_rect(center=(center_x, int(SCREEN_HEIGHT * 0.3)))
            screen.blit(prompt, prompt_rect)
            
            self.input_rect = self.draw_input_box(center_x - input_box_width//2, int(SCREEN_HEIGHT * 0.38), 
                                                 input_box_width, input_box_height, self.input_text, self.input_active)
            
            self.buttons["confirm"] = self.draw_button("Confirmar", center_x - button_width//2, int(SCREEN_HEIGHT * 0.48), 
                                                      button_width, button_height)
            
        elif self.input_type == "room":
            prompt = font_medium.render("Digite o código da sala:", True, COLOR_TEXT_LIGHT)
            prompt_rect = prompt.get_rect(center=(center_x, int(SCREEN_HEIGHT * 0.3)))
            screen.blit(prompt, prompt_rect)
            
            self.input_rect = self.draw_input_box(center_x - input_box_width//2, int(SCREEN_HEIGHT * 0.38), 
                                                 input_box_width, input_box_height, self.input_text, self.input_active)
            
            self.buttons["connect"] = self.draw_button("Conectar", center_x - button_width//2, int(SCREEN_HEIGHT * 0.48), 
                                                      button_width, button_height)
            
        # Mensagem de estado (conexão/erro)
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.6)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_waiting_screen(self):
        """Tela de espera por jogadores"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Aguardando Jogadores")
        
        center_x = SCREEN_WIDTH // 2
        
        # Mensagem do jogo
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (center_x, int(SCREEN_HEIGHT * 0.25)))
            if self.current_message.is_finished():
                self.current_message = None
        
        # Placar (canto direito)
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        # Informação sobre a sala e jogadores (esquerda)
        info_x = int(SCREEN_WIDTH * 0.03)
        y_offset = self.header_height + int(SCREEN_HEIGHT * 0.05)
        
        player_count_text = font_medium.render(f"Jogadores conectados: {len(self.scores)}", True, COLOR_TEXT_LIGHT)
        screen.blit(player_count_text, (info_x, y_offset))
        y_offset += int(SCREEN_HEIGHT * 0.05)
        
        current_players_title = font_medium.render("Jogadores na Sala:", True, COLOR_TEXT_LIGHT)
        screen.blit(current_players_title, (info_x, y_offset))
        y_offset += int(SCREEN_HEIGHT * 0.05)
        
        for name in self.scores.keys():
            if name:
                player_text = font_small.render(f"- {name}", True, COLOR_TEXT_LIGHT)
                screen.blit(player_text, (info_x + int(SCREEN_WIDTH * 0.02), y_offset))
                y_offset += int(SCREEN_HEIGHT * 0.04)

    def draw_countdown_screen(self):
        """Tela de countdown"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Jogo Começando!")
        
        center_x = SCREEN_WIDTH // 2
        center_y = SCREEN_HEIGHT // 2
        
        countdown_text = font_xlarge.render(f"Começando em: {self.countdown}", True, COLOR_SELECTION)
        countdown_rect = countdown_text.get_rect(center=(center_x, center_y))
        screen.blit(countdown_text, countdown_rect)
        
        # Placar
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))
    
    def draw_game_screen(self):
        """Tela principal do jogo (fase de submissão de cartas)"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Sua Vez de Jogar!")
        
        # Placar (canto direito)
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        # Carta preta no centro superior esquerdo
        black_card_x = int(SCREEN_WIDTH * 0.05) # Mais à esquerda
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.03)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_REGULAR * 1.5, CARD_HEIGHT_REGULAR * 1.2, True) # Tamanho maior para a preta
        
        # Contador de cartas submetidas (à direita da carta preta)
        submitted_text = font_medium.render(f"Cartas submetidas: {self.submitted_count}/{len(self.scores) - 1 if len(self.scores) > 0 else 0}", True, COLOR_TEXT_LIGHT)
        submitted_text_rect = submitted_text.get_rect(left=black_card_x + CARD_WIDTH_REGULAR * 1.5 + int(SCREEN_WIDTH * 0.03), 
                                                      centery=black_card_y + (CARD_HEIGHT_REGULAR * 1.2) // 2)
        screen.blit(submitted_text, submitted_text_rect)

        # Mão do jogador (cartas brancas)
        if self.hand:
            cards_in_row = 6 # Ajustado para 16:9
            max_hand_area_width = SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.05) # Largura disponível para mão
            
            # Recalcula quantas cartas cabem em uma linha baseada na largura disponível
            # E garante que não divida por zero se CARD_WIDTH_HAND ou CARD_MARGIN for 0 (embora não deva ser)
            if (CARD_WIDTH_HAND + CARD_MARGIN) > 0:
                cards_in_row = min(len(self.hand), int((max_hand_area_width + CARD_MARGIN) / (CARD_WIDTH_HAND + CARD_MARGIN)))
            if cards_in_row == 0: cards_in_row = 1 # Garante pelo menos 1 carta por linha

            # Calcula a largura total da linha de cartas para centralizar
            total_cards_width_line = (cards_in_row * CARD_WIDTH_HAND) + ((cards_in_row - 1) * CARD_MARGIN)
            start_x = (max_hand_area_width - total_cards_width_line) // 2 + int(SCREEN_WIDTH * 0.03)
                 
            start_y = SCREEN_HEIGHT - CARD_HEIGHT_HAND - int(SCREEN_HEIGHT * 0.03) # Perto da base

            # Para animação: armazenar posições alvo
            target_positions = {}
            for i, card_text in enumerate(self.hand):
                col = i % cards_in_row
                row = i // cards_in_row
                target_positions[card_text] = (start_x + col * (CARD_WIDTH_HAND + CARD_MARGIN), 
                                              start_y - row * (CARD_HEIGHT_HAND + CARD_MARGIN))

            # Atualizar animações
            new_card_animations = []
            for anim in self.card_animations:
                if anim["card"] in target_positions:
                    anim["end_pos"] = target_positions[anim["card"]] # Atualiza a posição final
                    progress = (time.time() - anim["start_time"]) / anim["duration"]
                    if progress < 1:
                        anim["current_pos"] = (
                            anim["start_pos"][0] + (anim["end_pos"][0] - anim["start_pos"][0]) * progress,
                            anim["start_pos"][1] + (anim["end_pos"][1] - anim["start_pos"][1]) * progress
                        )
                        new_card_animations.append(anim)
                    # else: remove a animação
            self.card_animations = new_card_animations
            
            # Desenha as cartas, priorizando as animadas
            drawn_animated_cards = set()
            for anim in self.card_animations:
                card_text = anim["card"]
                x, y = anim["current_pos"]
                is_selected = (self.selected_card_index != -1 and self.hand[self.selected_card_index] == card_text)
                
                current_scale = 1.0
                if is_selected:
                    self.selected_card_anim_scale += (1.05 - self.selected_card_anim_scale) * 0.1
                    if abs(1.05 - self.selected_card_anim_scale) < 0.01: self.selected_card_anim_scale = 1.05
                    current_scale = self.selected_card_anim_scale
                else:
                    self.selected_card_anim_scale = 1.0
                
                self.draw_card(card_text, int(x), int(y), CARD_WIDTH_HAND, CARD_HEIGHT_HAND, False, is_selected, current_scale)
                drawn_animated_cards.add(card_text)

            # Desenha as cartas não animadas ou já finalizadas
            for i, card_text in enumerate(self.hand):
                if card_text not in drawn_animated_cards:
                    x, y = target_positions[card_text] # Usa a posição final
                    is_selected = (self.selected_card_index == i)
                    current_scale = 1.0
                    if is_selected:
                        self.selected_card_anim_scale += (1.05 - self.selected_card_anim_scale) * 0.1
                        if abs(1.05 - self.selected_card_anim_scale) < 0.01: self.selected_card_anim_scale = 1.05
                        current_scale = self.selected_card_anim_scale
                    else:
                        self.selected_card_anim_scale = 1.0
                    self.draw_card(card_text, int(x), int(y), CARD_WIDTH_HAND, CARD_HEIGHT_HAND, False, is_selected, current_scale)
        
        # Botão de submeter carta
        submit_button_width = int(SCREEN_WIDTH * 0.15)
        submit_button_height = int(SCREEN_HEIGHT * 0.07)
        submit_button_x = SCREEN_WIDTH // 2 - submit_button_width // 2
        submit_button_y = SCREEN_HEIGHT - submit_button_height - int(SCREEN_HEIGHT * 0.02)
        
        # Desabilita o botão se já submeteu
        self.buttons["submit"] = self.draw_button("Submeter Carta", submit_button_x, 
                                                 submit_button_y, submit_button_width, submit_button_height, 
                                                 COLOR_SUCCESS, disabled=self.has_submitted_this_round)
        
        # Mensagem temporária
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.5)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_voting_screen(self):
        """Tela de votação"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Hora de Votar!")
        
        # Placar (canto direito)
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        # Carta preta
        black_card_x = int(SCREEN_WIDTH * 0.05)
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.03)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_REGULAR * 1.5, CARD_HEIGHT_REGULAR * 1.2, True)
        
        # Título da votação
        vote_title = font_medium.render("Vote na melhor resposta:", True, COLOR_TEXT_LIGHT)
        vote_rect = vote_title.get_rect(centerx=SCREEN_WIDTH//2, top=self.header_height + int(SCREEN_HEIGHT * 0.05))
        screen.blit(vote_title, vote_rect)
        
        # Cartas para votação
        if self.voting_cards:
            cards_in_row = 4 # Ajustado para 16:9
            # Ajuste dinâmico para caber mais cartas se necessário
            max_vote_area_width = SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.05)
            if (CARD_WIDTH_VOTE + CARD_MARGIN) > 0:
                cards_in_row = min(len(self.voting_cards), int((max_vote_area_width + CARD_MARGIN) / (CARD_WIDTH_VOTE + CARD_MARGIN)))
            if cards_in_row == 0: cards_in_row = 1

            total_cards_width = (cards_in_row * CARD_WIDTH_VOTE) + ((cards_in_row - 1) * CARD_MARGIN)
            start_x = (SCREEN_WIDTH - total_cards_width) // 2
            start_y = int(SCREEN_HEIGHT * 0.35) # Posição inicial das cartas de votação
            
            for i, card_text in enumerate(self.voting_cards):
                col = i % cards_in_row
                row = i // cards_in_row
                
                x = start_x + col * (CARD_WIDTH_VOTE + CARD_MARGIN)
                y = start_y + row * (CARD_HEIGHT_VOTE + CARD_MARGIN)
                
                current_scale = 1.0
                if self.selected_vote_index == i: # Usa self.selected_vote_index diretamente
                    self.vote_card_anim_scale += (1.05 - self.vote_card_anim_scale) * 0.1
                    if abs(1.05 - self.vote_card_anim_scale) < 0.01: self.vote_card_anim_scale = 1.05
                    current_scale = self.vote_card_anim_scale
                else:
                    self.vote_card_anim_scale = 1.0

                self.draw_card(card_text, x, y, CARD_WIDTH_VOTE, CARD_HEIGHT_VOTE, False, self.selected_vote_index == i, current_scale)
        
        # Botão de votar
        vote_button_width = int(SCREEN_WIDTH * 0.15)
        vote_button_height = int(SCREEN_HEIGHT * 0.07)
        vote_button_x = SCREEN_WIDTH // 2 - vote_button_width // 2
        vote_button_y = SCREEN_HEIGHT - vote_button_height - int(SCREEN_HEIGHT * 0.02)
        # Desabilita o botão se já votou
        self.buttons["vote"] = self.draw_button("Votar", vote_button_x, 
                                               vote_button_y, vote_button_width, vote_button_height, 
                                               COLOR_SUCCESS, disabled=self.has_voted_this_round)
        
        # Mensagem temporária
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.5)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_result_screen(self):
        """Tela de resultado da rodada"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Resultado da Rodada!")
        
        # Placar (canto direito)
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        # Carta preta
        black_card_x = int(SCREEN_WIDTH * 0.05)
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.03)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_REGULAR * 1.5, CARD_HEIGHT_REGULAR * 1.2, True)
        
        # Informações do vencedor
        if self.round_result:
            winner_card_text = self.round_result.get("winner_card", "")
            winner_name = self.round_result.get("winner_address", "")
            
            result_title = font_medium.render("Carta Vencedora:", True, COLOR_TEXT_LIGHT)
            result_rect = result_title.get_rect(centerx=SCREEN_WIDTH//2, top=self.header_height + int(SCREEN_HEIGHT * 0.05))
            screen.blit(result_title, result_rect)
            
            # Carta vencedora destacada
            winner_card_x = (SCREEN_WIDTH // 2) - (CARD_WIDTH_VOTE // 2)
            winner_card_y = int(SCREEN_HEIGHT * 0.35)
            self.draw_card(winner_card_text, winner_card_x, winner_card_y, 
                           CARD_WIDTH_VOTE * 1.2, CARD_HEIGHT_VOTE * 1.1, False, True) # Maior e selecionada
            
            winner_text = font_medium.render(f"Vencedor da Rodada: {winner_name}", True, COLOR_SELECTION)
            winner_text_rect = winner_text.get_rect(center=(SCREEN_WIDTH//2, winner_card_y + CARD_HEIGHT_VOTE * 1.1 + int(SCREEN_HEIGHT * 0.05)))
            screen.blit(winner_text, winner_text_rect)
        else:
            no_winner_text = font_medium.render("Nenhum vencedor nesta rodada.", True, COLOR_TEXT_LIGHT)
            no_winner_rect = no_winner_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
            screen.blit(no_winner_text, no_winner_rect)

        # Mensagem temporária (se houver)
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.8)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_game_over_screen(self):
        """Tela de fim de jogo"""
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Fim de Jogo!")
        
        center_x = SCREEN_WIDTH // 2
        y_start = self.header_height + int(SCREEN_HEIGHT * 0.05)
        
        game_over_message = font_xlarge.render("FIM DE JOGO!", True, COLOR_ERROR)
        game_over_rect = game_over_message.get_rect(center=(center_x, y_start))
        screen.blit(game_over_message, game_over_rect)
        
        y_start += int(SCREEN_HEIGHT * 0.1)
        if self.round_result and self.round_result.get("winner"):
            winner_name = self.round_result.get("winner", "")
            winner_score = self.round_result.get("score", "")
            winner_text = font_large.render(f"Vencedor: {winner_name} com {winner_score} pontos!", True, COLOR_SELECTION)
            winner_rect = winner_text.get_rect(center=(center_x, y_start))
            screen.blit(winner_text, winner_rect)
            y_start += int(SCREEN_HEIGHT * 0.06)
        else:
            no_winner_text = font_large.render("O jogo terminou.", True, COLOR_TEXT_LIGHT)
            no_winner_rect = no_winner_text.get_rect(center=(center_x, y_start))
            screen.blit(no_winner_text, no_winner_rect)
            y_start += int(SCREEN_HEIGHT * 0.06)

        # Placar final
        score_title = font_medium.render("Pontuações Finais:", True, COLOR_TEXT_LIGHT)
        score_title_rect = score_title.get_rect(center=(center_x, y_start))
        screen.blit(score_title, score_title_rect)
        
        y_offset = y_start + int(SCREEN_HEIGHT * 0.05)
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        for name, score in sorted_scores:
            if name:
                score_text = font_small.render(f"{name}: {score} pontos", True, COLOR_TEXT_LIGHT)
                score_rect = score_text.get_rect(center=(center_x, y_offset))
                screen.blit(score_text, score_rect)
                y_offset += int(SCREEN_HEIGHT * 0.04)
        
        new_game_button_width = int(SCREEN_WIDTH * 0.18)
        new_game_button_height = int(SCREEN_HEIGHT * 0.08)
        new_game_button_x = center_x - new_game_button_width // 2
        new_game_button_y = SCREEN_HEIGHT - new_game_button_height - int(SCREEN_HEIGHT * 0.03)
        
        self.buttons["new_game"] = self.draw_button("Nova Partida", new_game_button_x, 
                                                   new_game_button_y, new_game_button_width, new_game_button_height, COLOR_SUCCESS)
        # Mensagem temporária (se houver)
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - int(SCREEN_HEIGHT * 0.15)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw(self):
        """Função principal de desenho, escolhe a tela a ser desenhada."""
        self.buttons.clear() # Limpa os botões para cada frame
        
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
        """Lida com cliques do mouse."""
        if self.game_state == "disconnected":
            if self.input_type == "name":
                if hasattr(self, 'input_rect') and self.input_rect.collidepoint(pos):
                    self.input_active = True
                else:
                    self.input_active = False # Desativa se clicar fora
                
                if "confirm" in self.buttons and self.buttons["confirm"].collidepoint(pos):
                    if self.input_text.strip():
                        self.player_name = self.input_text.strip()
                        self.input_text = ""
                        self.input_type = "room"
                        self.input_active = True # Ativa o input da sala automaticamente
                        self.set_message("Nome definido! Agora digite o código da sala.", COLOR_SUCCESS)
                    else:
                        self.set_message("Por favor, digite um nome.", COLOR_ERROR)
            
            elif self.input_type == "room":
                if hasattr(self, 'input_rect') and self.input_rect.collidepoint(pos):
                    self.input_active = True
                else:
                    self.input_active = False
                
                if "connect" in self.buttons and self.buttons["connect"].collidepoint(pos):
                    if self.input_text.strip():
                        self.room_code = self.input_text.strip()
                        self.connect_to_server()
                        self.set_message(f"Tentando conectar à sala '{self.room_code}'...", COLOR_TEXT_LIGHT)
                    else:
                        self.set_message("Por favor, digite o código da sala.", COLOR_ERROR)
        
        elif self.game_state == "in_game":
            if not self.voting_cards:  # Fase de submissão
                # Clique nas cartas da mão
                if not self.has_submitted_this_round and self.hand: # Só permite selecionar se ainda não submeteu
                    cards_in_row = 6
                    card_width = CARD_WIDTH_HAND
                    card_height = CARD_HEIGHT_HAND
                    card_spacing = CARD_MARGIN
                    
                    max_hand_area_width = SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.05)
                    if (card_width + card_spacing) > 0:
                        cards_in_row = min(len(self.hand), int((max_hand_area_width + card_spacing) / (card_width + card_spacing)))
                    if cards_in_row == 0: cards_in_row = 1
                    
                    total_cards_width_line = (cards_in_row * card_width) + ((cards_in_row - 1) * card_spacing)
                    start_x = (max_hand_area_width - total_cards_width_line) // 2 + int(SCREEN_WIDTH * 0.03)
                    start_y = SCREEN_HEIGHT - card_height - int(SCREEN_HEIGHT * 0.03)
                    
                    for i, _ in enumerate(self.hand):
                        col = i % cards_in_row
                        row = i // cards_in_row
                        x = start_x + col * (card_width + card_spacing)
                        y = start_y - row * (card_height + card_spacing)
                        
                        card_rect = pygame.Rect(x, y, card_width, card_height)
                        if card_rect.collidepoint(pos):
                            if self.selected_card_index == i: # Deseleciona se clicar na mesma
                                self.selected_card_index = -1
                            else:
                                self.selected_card_index = i
                            self.selected_card_anim_scale = 1.0 # Reset para nova animação
                            break
                
                # Botão de submeter
                if "submit" in self.buttons and self.buttons["submit"].collidepoint(pos):
                    if not self.has_submitted_this_round: # Garante que só submeta uma vez
                        if self.selected_card_index != -1:
                            self.submit_card()
                            self.set_message("Carta submetida!", COLOR_SUCCESS)
                            self.has_submitted_this_round = True # Marca como submetida
                        else:
                            self.set_message("Selecione uma carta para submeter.", COLOR_ERROR)
                    else:
                        self.set_message("Você já submeteu sua carta nesta rodada.", COLOR_ERROR)
            
            else:  # Fase de votação
                # Clique nas cartas de votação
                if not self.has_voted_this_round and self.voting_cards: # Só permite selecionar se ainda não votou
                    cards_in_row = 4
                    card_width = CARD_WIDTH_VOTE
                    card_height = CARD_HEIGHT_VOTE
                    card_spacing = CARD_MARGIN
                    
                    max_vote_area_width = SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.05)
                    if (card_width + card_spacing) > 0:
                        cards_in_row = min(len(self.voting_cards), int((max_vote_area_width + card_spacing) / (card_width + card_spacing)))
                    if cards_in_row == 0: cards_in_row = 1

                    total_cards_width = (cards_in_row * card_width) + ((cards_in_row - 1) * card_spacing)
                    start_x = (SCREEN_WIDTH - total_cards_width) // 2
                    start_y = int(SCREEN_HEIGHT * 0.35)
                    
                    for i, _ in enumerate(self.voting_cards):
                        col = i % cards_in_row
                        row = i // cards_in_row
                        x = start_x + col * (card_width + card_spacing)
                        y = start_y + row * (card_height + card_spacing)
                        
                        card_rect = pygame.Rect(x, y, card_width, card_height)
                        if card_rect.collidepoint(pos):
                            if self.selected_vote_index == i: # Deseleciona se clicar na mesma
                                self.selected_vote_index = -1
                            else:
                                self.selected_vote_index = i
                            self.vote_card_anim_scale = 1.0 # Reset para nova animação
                            break
                
                # Botão de votar
                if "vote" in self.buttons and self.buttons["vote"].collidepoint(pos):
                    if not self.has_voted_this_round: # Garante que só vote uma vez
                        if self.selected_vote_index != -1:
                            self.vote_card()
                            self.set_message("Voto enviado!", COLOR_SUCCESS)
                            self.has_voted_this_round = True # Marca como votado
                        else:
                            self.set_message("Selecione uma carta para votar.", COLOR_ERROR)
                    else:
                        self.set_message("Você já votou nesta rodada.", COLOR_ERROR)
        
        elif self.game_state == "game_over":
            if "new_game" in self.buttons and self.buttons["new_game"].collidepoint(pos):
                self.restart_game()
                self.set_message("Iniciando nova partida...", COLOR_TEXT_LIGHT)
    
    def handle_keydown(self, event):
        """Lida com teclas pressionadas."""
        if self.input_active:
            if event.key == pygame.K_RETURN:
                if self.input_type == "name" and self.input_text.strip():
                    self.player_name = self.input_text.strip()
                    self.input_text = ""
                    self.input_type = "room"
                    self.input_active = True
                    self.set_message("Nome definido! Agora digite o código da sala.", COLOR_SUCCESS)
                elif self.input_type == "room" and self.input_text.strip():
                    self.room_code = self.input_text.strip()
                    self.connect_to_server()
                    self.set_message(f"Tentando conectar à sala '{self.room_code}'...", COLOR_TEXT_LIGHT)
                else: # Se apertar ENTER sem texto, mostra erro
                    self.set_message("Por favor, digite algo.", COLOR_ERROR)

            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            else:
                self.input_text += event.unicode
    
    def connect_to_server(self):
        """Inicia a thread WebSocket para conexão."""
        if self.ws_thread is None or not self.ws_thread.is_alive():
            print(f"Tentando conectar ao servidor com nome '{self.player_name}' e sala '{self.room_code}'")
            self.set_message("Conectando ao servidor...", COLOR_TEXT_LIGHT)
            self.ws_thread = threading.Thread(target=self.run_websocket, daemon=True)
            self.ws_thread.start()
        else:
            self.set_message("Já conectado ou tentando conectar.", COLOR_ERROR)
    
    def run_websocket(self):
        """Executa o cliente WebSocket em thread separada."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.websocket_loop = loop # Armazena o loop de eventos
        
        try:
            loop.run_until_complete(self.websocket_client())
        except Exception as e:
            print(f"Erro no loop da thread WebSocket: {e}")
            self.set_message(f"Erro interno de conexão: {e}", COLOR_ERROR)
        finally:
            if loop.is_running(): # Só fecha se ainda estiver rodando
                loop.close()
    
    async def websocket_client(self):
        """Cliente WebSocket principal."""
        port = int(os.environ.get("PORT", 10000))
        uri = f"ws://localhost:{port}"  # ou ajuste para o IP do seu servidor
        
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                self.connected = True
                print("Conectado ao servidor WebSocket.")
                self.set_message("Conectado! Aguardando o jogo começar.", COLOR_SUCCESS)
                
                # Envia o nome do jogador e código da sala
                await websocket.send(json.dumps({
                    "action": "nome",
                    "nome": self.player_name
                }))
                await websocket.send(json.dumps({
                    "action": "entrar_sala",
                    "sala": self.room_code
                }))
                
                # Loop para receber mensagens
                async for message in websocket:
                    data = json.loads(message)
                    await self.handle_server_message(data)
                    
        except websockets.exceptions.ConnectionClosedOK:
            print("Conexão WebSocket fechada normalmente.")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message("Desconectado do servidor.", COLOR_ERROR)
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"Conexão WebSocket fechada com erro: {e}")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message(f"Erro de conexão: {e}. Tente novamente.", COLOR_ERROR)
        except Exception as e:
            print(f"Erro na conexão WebSocket: {e}")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message(f"Erro inesperado de conexão: {e}. Tente novamente.", COLOR_ERROR)
        finally:
            self.websocket = None # Garante que o objeto websocket seja limpo
    
    async def handle_server_message(self, data):
        """Lida com mensagens do servidor."""
        action = data.get("action")
        print(f"Received: {action} - {data}") # Para debug
        
        if action == "game_state_update":
            old_state = self.game_state
            self.game_state = data.get("state", "disconnected")
            if self.game_state == "waiting_for_players" and old_state != "waiting_for_players":
                self.set_message("Aguardando mais jogadores...", COLOR_TEXT_LIGHT)
            elif self.game_state == "in_game" and old_state != "in_game":
                self.set_message("O jogo começou!", COLOR_SUCCESS)
            elif self.game_state == "round_result" and old_state == "in_game":
                # Limpa flags de submissão/voto para a próxima rodada
                self.has_submitted_this_round = False
                self.has_voted_this_round = False


        elif action == "nova_mao":
            # Guarda as posições ATUAIS das cartas ANTES de atualizar self.hand
            old_hand_coords = {} 
            cards_in_row = 6
            max_hand_area_width = SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.05)
            if (CARD_WIDTH_HAND + CARD_MARGIN) > 0:
                cards_in_row = min(len(self.hand), int((max_hand_area_width + CARD_MARGIN) / (CARD_WIDTH_HAND + CARD_MARGIN)))
            if cards_in_row == 0: cards_in_row = 1
            
            total_cards_width_line = (cards_in_row * CARD_WIDTH_HAND) + ((cards_in_row - 1) * CARD_MARGIN)
            start_x = (max_hand_area_width - total_cards_width_line) // 2 + int(SCREEN_WIDTH * 0.03)
            start_y = SCREEN_HEIGHT - CARD_HEIGHT_HAND - int(SCREEN_HEIGHT * 0.03)

            for i, card_text in enumerate(self.hand):
                col = i % cards_in_row
                row = i // cards_in_row
                current_card_x = start_x + col * (CARD_WIDTH_HAND + CARD_MARGIN)
                current_card_y = start_y - row * (CARD_HEIGHT_HAND + CARD_MARGIN)
                old_hand_coords[card_text] = (current_card_x, current_card_y)

            new_hand_list = data.get("cartas", [])
            
            # Inicializa animações para cartas que permanecem mas mudam de posição, ou novas cartas
            self.card_animations = []
            for new_card_text in new_hand_list:
                if new_card_text in old_hand_coords:
                    # Carta que já estava na mão, mas pode mudar de posição
                    self.card_animations.append({
                        "card": new_card_text,
                        "start_pos": old_hand_coords[new_card_text],
                        "end_pos": (0,0), # Será atualizado na função draw_game_screen
                        "current_pos": old_hand_coords[new_card_text], # Posição inicial para a animação
                        "start_time": time.time(),
                        "duration": 0.3 # Animação mais rápida
                    })
                else: # É uma carta nova, anima de baixo para cima
                    self.card_animations.append({
                        "card": new_card_text,
                        "start_pos": (SCREEN_WIDTH // 2, SCREEN_HEIGHT + CARD_HEIGHT_HAND), # Vem de baixo
                        "end_pos": (0,0), # Será atualizado na função draw_game_screen
                        "current_pos": (SCREEN_WIDTH // 2, SCREEN_HEIGHT + CARD_HEIGHT_HAND),
                        "start_time": time.time(),
                        "duration": 0.5
                    })
            
            self.hand = new_hand_list
            self.selected_card_index = -1
            self.set_message("Você recebeu uma nova mão!", COLOR_TEXT_LIGHT)
            self.has_submitted_this_round = False # Resetar para nova rodada
        
        elif action == "scores_update":
            self.scores = data.get("scores", {})
        
        elif action == "codigo_sala":
            self.room_code = data.get("sala", "")
            self.set_message(f"Você está na sala: {self.room_code}", COLOR_TEXT_LIGHT)
        
        elif action == "countdown":
            self.countdown = data.get("seconds", 0)
            self.set_message(f"Jogo começando em: {self.countdown}", COLOR_SELECTION)
        
        elif action == "black_card":
            self.current_black_card = data.get("card", "")
            self.submitted_count = 0 
            self.voting_cards = [] 
            self.selected_vote_index = -1
            self.has_submitted_this_round = False # Garante que pode submeter na nova rodada
            self.has_voted_this_round = False # Garante que pode votar na nova rodada
            self.set_message("Nova carta preta! Escolha sua melhor resposta.", COLOR_TEXT_LIGHT)
        
        elif action == "white_card_submitted":
            self.submitted_count = data.get("count", 0)
            self.set_message(f"{self.submitted_count} cartas submetidas.", COLOR_TEXT_LIGHT)
        
        elif action == "start_vote":
            self.voting_cards = data.get("cards", [])
            self.selected_vote_index = -1
            self.game_state = "in_game" # Para usar a tela de jogo, mas com voting_cards
            self.set_message("Hora de votar!", COLOR_SELECTION)
            self.has_voted_this_round = False # Garante que pode votar na rodada de votação
        
        elif action == "round_result":
            self.round_result = {
                "winner_card": data.get("winner_card", ""),
                "winner_address": data.get("winner_address", "")
            }
            self.game_state = "round_result"
            self.set_message(f"Vencedor da rodada: {self.round_result['winner_address']}!", COLOR_SUCCESS)
            # As flags de submissão/voto serão resetadas com a chegada da "nova_mao" ou "black_card"
        
        elif action == "game_over":
            self.round_result = {
                "winner": data.get("winner", ""),
                "score": data.get("score", "")
            }
            self.game_state = "game_over"
            self.set_message(f"Fim de Jogo! Vencedor: {self.round_result['winner']}.", COLOR_ERROR)
            self.has_submitted_this_round = False # Resetar para nova partida
            self.has_voted_this_round = False # Resetar para nova partida
        
        elif action == "next_round":
            self.voting_cards = []
            self.selected_card_index = -1
            self.selected_vote_index = -1
            self.submitted_count = 0
            self.has_submitted_this_round = False # Resetar para a próxima rodada
            self.has_voted_this_round = False # Resetar para a próxima rodada
            # O estado será ajustado quando a nova black_card chegar ou game_state_update
        
        elif action == "get_nome": # Bugfix que você mencionou
            if self.websocket:
                await self.websocket.send(json.dumps({
                    "action": "nome",
                    "nome": self.player_name
                }))
        
        elif action == "error":
            self.set_message(f"Erro do Servidor: {data.get('reason', 'Desconhecido')}", COLOR_ERROR)
            print(f"Server Error: {data.get('reason', 'Desconhecido')}")

    def submit_card(self):
        """Submete a carta selecionada."""
        if (self.selected_card_index != -1 and 
            self.selected_card_index < len(self.hand) and 
            self.websocket and
            self.websocket_loop):
            
            card = self.hand[self.selected_card_index]
            
            async def send_submit():
                try:
                    await self.websocket.send(json.dumps({
                        "action": "submit_white_card",
                        "card": card
                    }))
                    print(f"Carta '{card}' submetida.")
                except Exception as e:
                    print(f"Erro ao enviar submit_white_card: {e}")
            
            # Correção: Passar self.websocket_loop para run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(send_submit(), self.websocket_loop)
            self.selected_card_index = -1 # Limpa a seleção após submeter
            self.has_submitted_this_round = True # Garante que não submeta novamente

    def vote_card(self):
        """Vota na carta selecionada."""
        if (self.selected_vote_index != -1 and 
            self.selected_vote_index < len(self.voting_cards) and 
            self.websocket and
            self.websocket_loop):
            
            card = self.voting_cards[self.selected_vote_index]
            
            async def send_vote():
                try:
                    await self.websocket.send(json.dumps({
                        "action": "vote",
                        "card": card
                    }))
                    print(f"Voto em '{card}' enviado.")
                except Exception as e:
                    print(f"Erro ao enviar vote: {e}")
            
            # Correção: Passar self.websocket_loop para run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(send_vote(), self.websocket_loop)
            self.selected_vote_index = -1 # Limpa a seleção após votar
            self.has_voted_this_round = True # Garante que não vote novamente
    
    def restart_game(self):
        """Reinicia o estado local do cliente para uma nova partida."""
        # Fecha a conexão WebSocket antiga se existir
        if self.websocket and self.websocket_loop:
            # Precisa ser agendado no loop do WebSocket se a thread ainda estiver viva
            try:
                # Cria uma Future para o fechamento do websocket
                close_task = asyncio.run_coroutine_threadsafe(self.websocket.close(), self.websocket_loop)
                # Espera pelo resultado da Future com um timeout
                close_task.result(timeout=1.0)
            except asyncio.TimeoutError:
                print("Timeout ao tentar fechar WebSocket na reinicialização.")
            except Exception as e:
                print(f"Erro ao tentar fechar WebSocket na reinicialização: {e}")
            finally:
                self.websocket = None
                self.websocket_loop = None # Garante que um novo loop seja criado
                # Não há um bom jeito de "matar" uma thread em Python.
                # O daemon=True faz com que ela termine com o programa principal.
                # Se ws_thread ainda estiver ativa, ela eventualmente vai terminar.
                self.ws_thread = None 

        # Reinicia o estado do jogo
        self.game_state = "disconnected" # Volta para a tela de conexão/entrada de sala
        self.round_result = {}
        self.voting_cards = []
        self.selected_card_index = -1
        self.selected_vote_index = -1
        self.hand = []
        self.current_black_card = ""
        self.scores = {}
        self.submitted_count = 0
        self.countdown = 0
        self.player_name = "" # Limpa nome e sala para novo input
        self.room_code = ""
        self.input_text = ""
        self.input_active = True # Ativa o input de nome
        self.input_type = "name" # Reinicia o fluxo de nome/sala
        self.has_submitted_this_round = False # Reset flags
        self.has_voted_this_round = False # Reset flags
        self.card_animations = [] # Limpa animações pendentes
        self.set_message("Bem-vindo! Digite seu nome para começar.", COLOR_TEXT_LIGHT)


    def run(self):
        """Loop principal do jogo."""
        clock = pygame.time.Clock()
        
        # Define o input ativo inicialmente para o nome
        self.input_active = True 
        self.set_message("Bem-vindo! Digite seu nome para começar.", COLOR_TEXT_LIGHT)

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
            clock.tick(60) # Limita a 60 FPS
        
        # Cleanup final ao sair do loop principal
        if self.websocket and self.websocket_loop:
            try:
                # Tenta fechar o WebSocket de forma assíncrona na thread do WebSocket
                future = asyncio.run_coroutine_threadsafe(self.websocket.close(), self.websocket_loop)
                future.result(timeout=1.0) # Espera um pouco para garantir o fechamento
            except asyncio.TimeoutError:
                print("Timeout ao tentar fechar WebSocket no cleanup.")
            except Exception as e:
                print(f"Erro no cleanup ao fechar WebSocket: {e}")
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    client = GameClient()
    client.run()