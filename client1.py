import pygame
import asyncio
import websockets
import json
import threading
import sys
import os
import time
from typing import Optional, List, Dict, Any, Tuple

# Inicialização do Pygame
pygame.init()

# Configurações da tela
SCREEN_WIDTH = 1366
SCREEN_HEIGHT = 768
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Cards Against Humanity")
# pygame.display.toggle_fullscreen() # Descomente para iniciar em fullscreen

# Paleta de Cores
COLOR_BACKGROUND = (30, 30, 30)
COLOR_CARD_WHITE = (240, 240, 240)
COLOR_CARD_BLACK = (40, 40, 40)
COLOR_TEXT_LIGHT = (250, 250, 250)
COLOR_TEXT_DARK = (20, 20, 20)
COLOR_BUTTON_NORMAL = (70, 70, 70)
COLOR_BUTTON_HOVER = (90, 90, 90)
COLOR_BUTTON_ACTIVE = (120, 120, 120)
COLOR_SELECTION = (255, 200, 0)
COLOR_SUCCESS = (50, 205, 50)
COLOR_ERROR = (220, 20, 60)
COLOR_BORDER = (100, 100, 100)
DARK_GRAY = (64, 64, 64)

# Fontes
try:
    font_path = pygame.font.match_font('bahnschrift') or pygame.font.match_font('arial') or None
    font_xlarge = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.08))
    font_large = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.06))
    font_medium = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.04))
    font_small = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.03))
    font_card_text = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.027))
    font_card_text_hover = pygame.font.Font(font_path, int(SCREEN_HEIGHT * 0.032))
except Exception:
    print("Aviso: Não foi possível carregar fontes customizadas. Usando fontes padrão do Pygame.")
    font_xlarge = pygame.font.Font(None, 60)
    font_large = pygame.font.Font(None, 45)
    font_medium = pygame.font.Font(None, 30)
    font_small = pygame.font.Font(None, 20)
    font_card_text = pygame.font.Font(None, 20)
    font_card_text_hover = pygame.font.Font(None, 24)

# Tamanhos de cartas e margens
CARD_ASPECT_RATIO = 0.7

CARD_HEIGHT_BLACK = int(SCREEN_HEIGHT * 0.35)
CARD_WIDTH_BLACK = int(CARD_HEIGHT_BLACK * CARD_ASPECT_RATIO)

CARD_HEIGHT_HAND = int(SCREEN_HEIGHT * 0.28)
CARD_WIDTH_HAND = int(CARD_HEIGHT_HAND * CARD_ASPECT_RATIO)

CARD_HEIGHT_VOTE = int(SCREEN_HEIGHT * 0.28)
CARD_WIDTH_VOTE = int(CARD_HEIGHT_VOTE * CARD_ASPECT_RATIO)

CARD_MARGIN = int(SCREEN_WIDTH * 0.015)

# Sombra para as cartas
SHADOW_OFFSET = 5
SHADOW_COLOR = (10, 10, 10, 150)

# Animação de mensagem
MESSAGE_DISPLAY_TIME = 3.0
MESSAGE_FADE_DURATION = 0.5

# Configurações da Mão de Cartas (Estilo UNO)
CARD_OVERLAP_FACTOR = 0.35
CARD_HOVER_OFFSET_Y = 20
CARD_SELECT_OFFSET_Y = 40
CARD_TEXT_PADDING = 15

class AnimatedMessage:
    def __init__(self, text: str, color: Tuple[int, int, int], font: pygame.font.Font, duration: float, fade_duration: float):
        self.text = text
        self.color = color
        self.font = font
        self.start_time = time.time()
        self.duration = duration
        self.fade_duration = fade_duration
        self.alpha = 255

    def update(self):
        elapsed = time.time() - self.start_time
        if elapsed > self.duration - self.fade_duration:
            progress = (elapsed - (self.duration - self.fade_duration)) / self.fade_duration
            self.alpha = max(0, 255 - int(255 * progress))
        elif elapsed < self.fade_duration:
            progress = elapsed / self.fade_duration
            self.alpha = min(255, int(255 * progress))
        else:
            self.alpha = 255

    def draw(self, surface, center_pos: Tuple[int, int]):
        if self.alpha > 0:
            text_surface = self.font.render(self.text, True, self.color)
            text_surface.set_alpha(self.alpha)
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
        
        # Flags para controlar ações por rodada
        self.has_submitted_this_round = False
        self.has_voted_this_round = False
        
        # UI
        self.input_text = ""
        self.input_active = False
        self.input_type = "name"
        
        # Mensagens temporárias
        self.current_message: Optional[AnimatedMessage] = None
        
        # Thread para WebSocket
        self.ws_thread = None
        self.websocket_loop: Optional[asyncio.AbstractEventLoop] = None # Definido como Optional
        
        # Botões para interatividade
        self.buttons: Dict[str, pygame.Rect] = {}
        
        # Posições e tamanhos relativos
        self.header_height = int(SCREEN_HEIGHT * 0.13)
        self.scoreboard_width = int(SCREEN_WIDTH * 0.18)

        # Para hover das cartas na mão
        self.hover_card_index = -1
    
    def set_message(self, text: str, color: Tuple[int, int, int] = COLOR_TEXT_LIGHT, 
                    duration: float = MESSAGE_DISPLAY_TIME, fade_duration: float = MESSAGE_FADE_DURATION):
        self.current_message = AnimatedMessage(text, color, font_medium, duration, fade_duration)

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Quebra texto em múltiplas linhas para caber na largura máxima."""
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
    
    def draw_text_multiline(self, surface, text, color, rect, font, align_x="center", align_y="center"):
        """Desenha texto multi-linha com alinhamento, considerando padding."""
        text_rect_padded = rect.inflate(-2 * CARD_TEXT_PADDING, -2 * CARD_TEXT_PADDING)

        lines = self.wrap_text(text, font, text_rect_padded.width)
        line_height = font.get_height()
        
        total_text_height = len(lines) * line_height
        
        start_y = text_rect_padded.top
        if align_y == "center":
            start_y = text_rect_padded.centery - total_text_height // 2
        elif align_y == "bottom":
            start_y = text_rect_padded.bottom - total_text_height
        
        for i, line in enumerate(lines):
            text_surface = font.render(line, True, color)
            text_rect = text_surface.get_rect()
            
            if align_x == "center":
                text_rect.centerx = text_rect_padded.centerx
            elif align_x == "left":
                text_rect.left = text_rect_padded.left
            elif align_x == "right":
                text_rect.right = text_rect_padded.right
            
            text_rect.y = start_y + i * line_height
            surface.blit(text_surface, text_rect)

    def draw_card(self, text: str, x: int, y: int, width: int, height: int, 
                  is_black: bool, selected: bool = False, hovered: bool = False):
        """Desenha uma carta na tela com sombra e bordas arredondadas.
           'hovered' agora controla o offset para cima.
        """
        card_color = COLOR_CARD_BLACK if is_black else COLOR_CARD_WHITE
        text_color = COLOR_TEXT_LIGHT if is_black else COLOR_TEXT_DARK
        border_color = COLOR_SELECTION if selected else COLOR_BORDER
        
        offset_y = 0
        if selected:
            offset_y = -CARD_SELECT_OFFSET_Y
        elif hovered and not is_black:
            offset_y = -CARD_HOVER_OFFSET_Y
        
        final_y = y + offset_y

        shadow_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surface, SHADOW_COLOR, (0, 0, width, height), 0, 10)
        screen.blit(shadow_surface, (x + SHADOW_OFFSET, final_y + SHADOW_OFFSET))
        
        card_rect = pygame.Rect(x, final_y, width, height)
        pygame.draw.rect(screen, card_color, card_rect, 0, 10)
        
        pygame.draw.rect(screen, border_color, card_rect, 3, 10)
        
        text_font = font_card_text
        if (hovered or selected) and not is_black:
            text_font = font_card_text_hover
        elif is_black:
            text_font = font_medium

        self.draw_text_multiline(screen, text, text_color, card_rect, text_font)
    
    def draw_button(self, text: str, x: int, y: int, width: int, height: int, 
                   color: tuple = COLOR_BUTTON_NORMAL, text_color: tuple = COLOR_TEXT_LIGHT, 
                   hover_color: tuple = COLOR_BUTTON_HOVER, disabled: bool = False) -> pygame.Rect:
        """Desenha um botão e retorna seu rect. Lida com hover e estado desabilitado."""
        button_rect = pygame.Rect(x, y, width, height)
        current_color = color
        
        if disabled:
            current_color = (current_color[0] // 2, current_color[1] // 2, current_color[2] // 2)
            text_color = (text_color[0] // 2, text_color[1] // 2, text_color[2] // 2)
        else:
            mouse_pos = pygame.mouse.get_pos()
            if button_rect.collidepoint(mouse_pos):
                current_color = hover_color
        
        pygame.draw.rect(screen, current_color, button_rect, 0, 5)
        pygame.draw.rect(screen, COLOR_BORDER, button_rect, 2, 5)
        
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
        
        pygame.draw.rect(screen, color, input_rect, 0, 5)
        pygame.draw.rect(screen, border_color, input_rect, 2, 5)
        
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
        sorted_scores = sorted(self.scores.items(), key=lambda item: item[1], reverse=True)

        for name, score in sorted_scores:
            if name:
                score_text = font_small.render(f"{name}: {score}", True, COLOR_TEXT_LIGHT)
                score_rect = score_text.get_rect(left=x + int(width * 0.05), centery=y_offset)
                screen.blit(score_text, score_rect)
                y_offset += int(height * 0.05)
    
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
            
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.6)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_waiting_screen(self):
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Aguardando Jogadores")
        
        center_x = SCREEN_WIDTH // 2
        
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (center_x, int(SCREEN_HEIGHT * 0.25)))
            if self.current_message.is_finished():
                self.current_message = None
        
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

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
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Jogo Começando!")
        
        center_x = SCREEN_WIDTH // 2
        center_y = SCREEN_HEIGHT // 2
        
        countdown_text = font_xlarge.render(f"Começando em: {self.countdown}", True, COLOR_SELECTION)
        countdown_rect = countdown_text.get_rect(center=(center_x, center_y))
        screen.blit(countdown_text, countdown_rect)
        
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))
    
    def draw_game_screen(self):
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Sua Vez de Jogar!")
        
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        black_card_x = int(SCREEN_WIDTH * 0.05)
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.05)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_BLACK, CARD_HEIGHT_BLACK, True)
        
        submitted_text = font_medium.render(f"Cartas submetidas: {self.submitted_count}/{len(self.scores) - 1 if len(self.scores) > 0 else 0}", True, COLOR_TEXT_LIGHT)
        submitted_text_rect = submitted_text.get_rect(left=black_card_x + CARD_WIDTH_BLACK + int(SCREEN_WIDTH * 0.03), 
                                                      centery=black_card_y + CARD_HEIGHT_BLACK // 2)
        screen.blit(submitted_text, submitted_text_rect)

        if self.hand:
            available_hand_width = SCREEN_WIDTH - self.scoreboard_width - (2 * int(SCREEN_WIDTH * 0.03))
            base_hand_y = SCREEN_HEIGHT - CARD_HEIGHT_HAND - int(SCREEN_HEIGHT * 0.03)

            if len(self.hand) > 1:
                full_width_no_overlap = len(self.hand) * CARD_WIDTH_HAND
                
                if full_width_no_overlap > available_hand_width:
                    card_horizontal_spacing = (available_hand_width - CARD_WIDTH_HAND) / (len(self.hand) - 1)
                else:
                    card_horizontal_spacing = CARD_WIDTH_HAND - (CARD_WIDTH_HAND * CARD_OVERLAP_FACTOR)
                    
            else:
                card_horizontal_spacing = 0 
            
            card_horizontal_spacing = max(0, card_horizontal_spacing)

            hand_display_width = CARD_WIDTH_HAND + (len(self.hand) - 1) * card_horizontal_spacing

            start_x = (SCREEN_WIDTH - hand_display_width) // 2 

            self.card_rects_in_hand = []

            for i, card_text in enumerate(self.hand):
                x = int(start_x + i * card_horizontal_spacing)
                y = base_hand_y

                is_selected = (self.selected_card_index == i)
                is_hovered = (self.hover_card_index == i)

                self.draw_card(card_text, x, y, CARD_WIDTH_HAND, CARD_HEIGHT_HAND, False, is_selected, is_hovered)
                
                current_card_rect = pygame.Rect(x, y, CARD_WIDTH_HAND, CARD_HEIGHT_HAND)
                if is_selected:
                    current_card_rect.y -= CARD_SELECT_OFFSET_Y
                elif is_hovered:
                    current_card_rect.y -= CARD_HOVER_OFFSET_Y

                hover_width = CARD_WIDTH_HAND
                if i < len(self.hand) - 1:
                    hover_width = int(card_horizontal_spacing + (CARD_WIDTH_HAND * CARD_OVERLAP_FACTOR * 0.5))

                hover_rect = pygame.Rect(x, current_card_rect.y, hover_width, CARD_HEIGHT_HAND)
                self.card_rects_in_hand.append(hover_rect)
        
        submit_button_width = int(SCREEN_WIDTH * 0.15)
        submit_button_height = int(SCREEN_HEIGHT * 0.07)
        submit_button_x = SCREEN_WIDTH // 2 - submit_button_width // 2
        submit_button_y = SCREEN_HEIGHT - submit_button_height - int(SCREEN_HEIGHT * 0.02)
        
        self.buttons["submit"] = self.draw_button("Submeter Carta", submit_button_x, 
                                                 submit_button_y, submit_button_width, submit_button_height, 
                                                 COLOR_SUCCESS, disabled=self.has_submitted_this_round or self.selected_card_index == -1)
        
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.5)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_voting_screen(self):
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Hora de Votar!")
        
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        black_card_x = int(SCREEN_WIDTH * 0.05)
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.05)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_BLACK, CARD_HEIGHT_BLACK, True)
        
        vote_title = font_medium.render("Vote na melhor resposta:", True, COLOR_TEXT_LIGHT)
        vote_rect = vote_title.get_rect(centerx=SCREEN_WIDTH//2, top=self.header_height + int(SCREEN_HEIGHT * 0.05))
        screen.blit(vote_title, vote_rect)
        
        if self.voting_cards:
            cards_in_row = 3
            
            max_vote_area_width = SCREEN_WIDTH - self.scoreboard_width - (2 * int(SCREEN_WIDTH * 0.03)) 
            
            card_total_width = CARD_WIDTH_VOTE + CARD_MARGIN
            
            actual_cards_in_row = min(len(self.voting_cards), cards_in_row)

            total_cards_width = (actual_cards_in_row * CARD_WIDTH_VOTE) + ((actual_cards_in_row - 1) * CARD_MARGIN)
            
            start_x = (SCREEN_WIDTH - total_cards_width) // 2
            start_y = int(SCREEN_HEIGHT * 0.35)
            
            for i, card_text in enumerate(self.voting_cards):
                col = i % actual_cards_in_row
                row = i // actual_cards_in_row
                
                x = start_x + col * (CARD_WIDTH_VOTE + CARD_MARGIN)
                y = start_y + row * (CARD_HEIGHT_VOTE + CARD_MARGIN)
                
                self.draw_card(card_text, x, y, CARD_WIDTH_VOTE, CARD_HEIGHT_VOTE, False, self.selected_vote_index == i)
        
        vote_button_width = int(SCREEN_WIDTH * 0.15)
        vote_button_height = int(SCREEN_HEIGHT * 0.07)
        vote_button_x = SCREEN_WIDTH // 2 - vote_button_width // 2
        vote_button_y = SCREEN_HEIGHT - vote_button_height - int(SCREEN_HEIGHT * 0.02)
        
        self.buttons["vote"] = self.draw_button("Votar", vote_button_x, 
                                               vote_button_y, vote_button_width, vote_button_height, 
                                               COLOR_SUCCESS, disabled=self.has_voted_this_round or self.selected_vote_index == -1)
        
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.5)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_result_screen(self):
        screen.fill(COLOR_BACKGROUND)
        self.draw_header("Resultado da Rodada!")
        
        self.draw_score_board(SCREEN_WIDTH - self.scoreboard_width - int(SCREEN_WIDTH * 0.015), self.header_height + int(SCREEN_HEIGHT * 0.02), 
                              self.scoreboard_width, SCREEN_HEIGHT - self.header_height - int(SCREEN_HEIGHT * 0.04))

        black_card_x = int(SCREEN_WIDTH * 0.05)
        black_card_y = self.header_height + int(SCREEN_HEIGHT * 0.05)
        if self.current_black_card:
            self.draw_card(self.current_black_card, black_card_x, black_card_y, 
                           CARD_WIDTH_BLACK, CARD_HEIGHT_BLACK, True)
        
        if self.round_result:
            winner_card_text = self.round_result.get("winner_card", "")
            winner_name = self.round_result.get("winner_address", "")
            
            result_title = font_medium.render("Carta Vencedora:", True, COLOR_TEXT_LIGHT)
            result_rect = result_title.get_rect(centerx=SCREEN_WIDTH//2, top=self.header_height + int(SCREEN_HEIGHT * 0.05))
            screen.blit(result_title, result_rect)
            
            WINNER_CARD_HEIGHT = int(SCREEN_HEIGHT * 0.35)
            WINNER_CARD_WIDTH = int(WINNER_CARD_HEIGHT * CARD_ASPECT_RATIO)

            winner_card_x = (SCREEN_WIDTH // 2) - (WINNER_CARD_WIDTH // 2)
            winner_card_y = int(SCREEN_HEIGHT * 0.35)
            self.draw_card(winner_card_text, winner_card_x, winner_card_y, 
                           WINNER_CARD_WIDTH, WINNER_CARD_HEIGHT, False, True)
            
            winner_text = font_medium.render(f"Vencedor da Rodada: {winner_name}", True, COLOR_SELECTION)
            winner_text_rect = winner_text.get_rect(center=(SCREEN_WIDTH//2, winner_card_y + WINNER_CARD_HEIGHT + int(SCREEN_HEIGHT * 0.05)))
            screen.blit(winner_text, winner_text_rect)
        else:
            no_winner_text = font_medium.render("Nenhum vencedor nesta rodada.", True, COLOR_TEXT_LIGHT)
            no_winner_rect = no_winner_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
            screen.blit(no_winner_text, no_winner_rect)

        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.8)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw_game_over_screen(self):
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
        if self.current_message:
            self.current_message.update()
            self.current_message.draw(screen, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - int(SCREEN_HEIGHT * 0.15)))
            if self.current_message.is_finished():
                self.current_message = None

    def draw(self):
        self.buttons.clear()
        
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
        if self.game_state == "disconnected":
            if self.input_type == "name":
                if hasattr(self, 'input_rect') and self.input_rect.collidepoint(pos):
                    self.input_active = True
                else:
                    self.input_active = False
                
                if "confirm" in self.buttons and self.buttons["confirm"].collidepoint(pos):
                    if self.input_text.strip():
                        self.player_name = self.input_text.strip()
                        self.input_text = ""
                        self.input_type = "room"
                        self.input_active = True
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
                if not self.has_submitted_this_round and self.hand and hasattr(self, 'card_rects_in_hand'):
                    for i in reversed(range(len(self.card_rects_in_hand))):
                        card_rect = self.card_rects_in_hand[i]
                        if card_rect.collidepoint(pos):
                            if self.selected_card_index == i:
                                self.selected_card_index = -1
                            else:
                                self.selected_card_index = i
                            break
                
                if "submit" in self.buttons and self.buttons["submit"].collidepoint(pos):
                    if not self.has_submitted_this_round:
                        if self.selected_card_index != -1:
                            self.submit_card()
                            self.set_message("Carta submetida!", COLOR_SUCCESS)
                        else:
                            self.set_message("Selecione uma carta para submeter.", COLOR_ERROR)
                    else:
                        self.set_message("Você já submeteu sua carta nesta rodada.", COLOR_ERROR)
            
            else:  # Fase de votação
                if not self.has_voted_this_round and self.voting_cards:
                    cards_in_row = 3
                    card_width = CARD_WIDTH_VOTE
                    card_height = CARD_HEIGHT_VOTE
                    card_spacing = CARD_MARGIN
                    
                    max_vote_area_width = SCREEN_WIDTH - self.scoreboard_width - (2 * int(SCREEN_WIDTH * 0.03)) 
                    actual_cards_in_row = min(len(self.voting_cards), cards_in_row)
                    total_cards_width = (actual_cards_in_row * card_width) + ((actual_cards_in_row - 1) * card_spacing)
                    
                    start_x = (SCREEN_WIDTH - total_cards_width) // 2
                    start_y = int(SCREEN_HEIGHT * 0.35)
                    
                    for i, _ in enumerate(self.voting_cards):
                        col = i % actual_cards_in_row
                        row = i // actual_cards_in_row
                        x = start_x + col * (card_width + card_spacing)
                        y = start_y + row * (card_height + card_spacing)
                        
                        card_rect = pygame.Rect(x, y, card_width, card_height)
                        if card_rect.collidepoint(pos):
                            if self.selected_vote_index == i:
                                self.selected_vote_index = -1
                            else:
                                self.selected_vote_index = i
                            break
                
                if "vote" in self.buttons and self.buttons["vote"].collidepoint(pos):
                    if not self.has_voted_this_round:
                        if self.selected_vote_index != -1:
                            self.vote_card()
                            self.set_message("Voto enviado!", COLOR_SUCCESS)
                        else:
                            self.set_message("Selecione uma carta para votar.", COLOR_ERROR)
                    else:
                        self.set_message("Você já votou nesta rodada.", COLOR_ERROR)
        
        elif self.game_state == "game_over":
            if "new_game" in self.buttons and self.buttons["new_game"].collidepoint(pos):
                self.restart_game()
                self.set_message("Iniciando nova partida...", COLOR_TEXT_LIGHT)
    
    def handle_mouse_motion(self, pos):
        if self.game_state == "in_game" and not self.voting_cards and self.hand and hasattr(self, 'card_rects_in_hand'):
            new_hover_index = -1
            for i in reversed(range(len(self.card_rects_in_hand))):
                card_rect = self.card_rects_in_hand[i]
                if card_rect.collidepoint(pos):
                    new_hover_index = i
                    break
            self.hover_card_index = new_hover_index
        else:
            self.hover_card_index = -1

    def handle_keydown(self, event):
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
                else:
                    self.set_message("Por favor, digite algo.", COLOR_ERROR)

            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            else:
                self.input_text += event.unicode
    
    def connect_to_server(self):
        if self.ws_thread is None or not self.ws_thread.is_alive():
            print(f"[CLIENT] Tentando conectar ao servidor com nome '{self.player_name}' e sala '{self.room_code}'")
            self.set_message("Conectando ao servidor...", COLOR_TEXT_LIGHT)
            # Cria um novo loop de eventos para a thread do websocket
            self.websocket_loop = asyncio.new_event_loop()
            self.ws_thread = threading.Thread(target=self._run_websocket_in_thread, daemon=True)
            self.ws_thread.start()
        else:
            self.set_message("Já conectado ou tentando conectar.", COLOR_ERROR)
    
    def _run_websocket_in_thread(self):
        """Função a ser executada na thread separada para o WebSocket."""
        asyncio.set_event_loop(self.websocket_loop)
        try:
            self.websocket_loop.run_until_complete(self.websocket_client())
        except Exception as e:
            print(f"[CLIENT ERROR] Erro no loop da thread WebSocket: {e}")
            self.set_message(f"Erro interno de conexão: {e}", COLOR_ERROR)
        finally:
            if not self.websocket_loop.is_closed():
                # self.websocket_loop.close() # Não fechar aqui, pode ser necessário para outras corrotinas
                print("[CLIENT] Loop WebSocket thread finalizado.")

    async def websocket_client(self):
        port = int(os.environ.get("PORT", 10000))
        uri = f"ws://localhost:{port}"
        
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                self.connected = True
                print("[CLIENT] Conectado ao servidor WebSocket.")
                self.set_message("Conectado! Aguardando o jogo começar.", COLOR_SUCCESS)
                
                await websocket.send(json.dumps({
                    "action": "nome",
                    "nome": self.player_name
                }))
                await websocket.send(json.dumps({
                    "action": "entrar_sala",
                    "sala": self.room_code
                }))
                
                async for message in websocket:
                    data = json.loads(message)
                    await self.handle_server_message(data)
                    
        except websockets.exceptions.ConnectionClosedOK:
            print("[CLIENT] Conexão WebSocket fechada normalmente.")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message("Desconectado do servidor.", COLOR_ERROR)
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"[CLIENT ERROR] Conexão WebSocket fechada com erro: {e}")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message(f"Erro de conexão: {e}. Tente novamente.", COLOR_ERROR)
        except Exception as e:
            print(f"[CLIENT ERROR] Erro na conexão WebSocket: {e}")
            self.connected = False
            self.game_state = "disconnected"
            self.set_message(f"Erro inesperado de conexão: {e}. Tente novamente.", COLOR_ERROR)
        finally:
            self.websocket = None # Garante que o websocket está limpo
            print("[CLIENT] WebSocket instance set to None.")


    async def handle_server_message(self, data):
        action = data.get("action")
        print(f"[CLIENT] Received action: {action} - Data: {data}")
        
        if action == "game_state_update":
            old_state = self.game_state
            self.game_state = data.get("state", "disconnected")
            if self.game_state == "waiting_for_players" and old_state != "waiting_for_players":
                self.set_message("Aguardando mais jogadores...", COLOR_TEXT_LIGHT)
            elif self.game_state == "in_game" and old_state != "in_game":
                self.set_message("O jogo começou!", COLOR_SUCCESS)
            
            # **CORREÇÃO CRÍTICA 1:** Resetar flags quando o estado de jogo transiciona para um estado final/de rodada
            if self.game_state in ["round_result", "game_over"]:
                self.has_submitted_this_round = False
                self.has_voted_this_round = False
                self.selected_card_index = -1 # Limpa seleção da mão
                self.selected_vote_index = -1 # Limpa seleção de voto
                print(f"[CLIENT] Flags de submissão/voto resetadas no state_update para '{self.game_state}'.")


        elif action == "nova_mao":
            new_hand_list = data.get("cartas", [])
            self.hand = new_hand_list
            self.selected_card_index = -1
            self.hover_card_index = -1
            self.set_message("Você recebeu uma nova mão!", COLOR_TEXT_LIGHT)
        
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
            # **CORREÇÃO CRÍTICA 1.1:** Resetar flags aqui também para garantir, caso o state_update falhe.
            self.has_submitted_this_round = False 
            self.has_voted_this_round = False 
            self.set_message("Nova carta preta! Escolha sua melhor resposta.", COLOR_TEXT_LIGHT)
        
        elif action == "white_card_submitted":
            self.submitted_count = data.get("count", 0)
            self.set_message(f"{self.submitted_count} cartas submetidas.", COLOR_TEXT_LIGHT)
        
        elif action == "start_vote":
            self.voting_cards = data.get("cards", [])
            self.selected_vote_index = -1
            self.game_state = "in_game" # Votação é uma sub-fase do in_game
            self.set_message("Hora de votar!", COLOR_SELECTION)
            self.has_voted_this_round = False # Garante que pode votar na rodada de votação
        
        elif action == "round_result":
            self.round_result = {
                "winner_card": data.get("winner_card", ""),
                "winner_address": data.get("winner_address", "")
            }
            self.game_state = "round_result"
            self.set_message(f"Vencedor da Rodada: {self.round_result['winner_address']}!", COLOR_SUCCESS)
            # As flags já devem ter sido resetadas pelo game_state_update para 'round_result'
            # Mas, para garantir, vamos resetar aqui também se o 'game_state_update' for perdido
            self.has_submitted_this_round = False
            self.has_voted_this_round = False

        elif action == "game_over":
            self.round_result = {
                "winner": data.get("winner", ""),
                "score": data.get("score", "")
            }
            self.game_state = "game_over"
            self.set_message(f"Fim de Jogo! Vencedor: {self.round_result['winner']}.", COLOR_ERROR)
            self.has_submitted_this_round = False
            self.has_voted_this_round = False
        
        elif action == "next_round":
            # **CORREÇÃO CRÍTICA 2:** Limpar o estado do cliente para a próxima rodada
            print("[CLIENT] Recebido 'next_round'. Preparando para a nova rodada.")
            self.voting_cards = [] # Limpa as cartas de votação da rodada anterior
            self.selected_card_index = -1
            self.selected_vote_index = -1
            self.submitted_count = 0
            self.set_message("Iniciando próxima rodada...", COLOR_TEXT_LIGHT)
            # As flags de submissão/voto já foram resetadas quando entrou em "round_result" ou "game_over"
        
        elif action == "get_nome":
            if self.websocket:
                await self.websocket.send(json.dumps({
                    "action": "nome",
                    "nome": self.player_name
                }))
        
        elif action == "error":
            self.set_message(f"Erro do Servidor: {data.get('reason', 'Desconhecido')}", COLOR_ERROR)
            print(f"[CLIENT ERROR] Server Error: {data.get('reason', 'Desconhecido')}")

    def submit_card(self):
        if (self.selected_card_index != -1 and 
            self.selected_card_index < len(self.hand) and 
            self.websocket and
            self.websocket_loop and
            not self.has_submitted_this_round): 
            
            card = self.hand[self.selected_card_index]
            
            async def send_submit():
                try:
                    await self.websocket.send(json.dumps({
                        "action": "submit_white_card",
                        "card": card
                    }))
                    print(f"[CLIENT] Carta '{card}' submetida.")
                except Exception as e:
                    print(f"[CLIENT ERROR] Erro ao enviar submit_white_card: {e}")
            
            asyncio.run_coroutine_threadsafe(send_submit(), self.websocket_loop)
            self.selected_card_index = -1
            self.has_submitted_this_round = True

    def vote_card(self):
        if (self.selected_vote_index != -1 and 
            self.selected_vote_index < len(self.voting_cards) and 
            self.websocket and
            self.websocket_loop and
            not self.has_voted_this_round): 
            
            card = self.voting_cards[self.selected_vote_index]
            
            async def send_vote():
                try:
                    await self.websocket.send(json.dumps({
                        "action": "vote",
                        "card": card
                    }))
                    print(f"[CLIENT] Voto em '{card}' enviado.")
                except Exception as e:
                    print(f"[CLIENT ERROR] Erro ao enviar vote: {e}")
            
            asyncio.run_coroutine_threadsafe(send_vote(), self.websocket_loop)
            self.selected_vote_index = -1
            self.has_voted_this_round = True
    
    def restart_game(self):
        print("[CLIENT] Reiniciando estado do cliente para nova partida.")
        # **CORREÇÃO CRÍTICA 3:** Gerenciamento da thread do WebSocket ao reiniciar o jogo
        if self.websocket and self.websocket_loop and not self.websocket_loop.is_closed():
            async def _close_websocket():
                try:
                    await self.websocket.close()
                    print("[CLIENT] WebSocket fechado com sucesso durante reinício.")
                except Exception as e:
                    print(f"[CLIENT ERROR] Erro ao tentar fechar WebSocket na reinicialização: {e}")
            
            # Executa o fechamento no loop do WebSocket se ele ainda estiver rodando
            if self.websocket_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_close_websocket(), self.websocket_loop)
                try:
                    future.result(timeout=1.0) # Espera um pouco
                except asyncio.TimeoutError:
                    print("[CLIENT WARNING] Timeout ao tentar fechar WebSocket na reinicialização.")
            else:
                # Se o loop não está rodando, podemos tentar fechar diretamente se o websocket existir
                # Embora seja menos comum, adicionamos essa segurança
                if self.websocket:
                    try:
                        self.websocket_loop.run_until_complete(_close_websocket())
                    except Exception as e:
                        print(f"[CLIENT ERROR] Erro ao tentar fechar WebSocket diretamente na reinicialização: {e}")

        # Garante que a thread é parada e o loop é fechado, se necessário
        if self.ws_thread and self.ws_thread.is_alive():
            # Não é recomendado matar threads diretamente, a flag `self.running = False`
            # no `run()` principal do Pygame e o tratamento no `websocket_client()`
            # já devem lidar com a saída elegante.
            # Aqui, apenas garantimos que referências são limpas para uma nova thread.
            pass # A lógica de fechamento acima já cuida da conexão.

        if self.websocket_loop and not self.websocket_loop.is_closed():
             self.websocket_loop.stop()
             self.websocket_loop.close()
             print("[CLIENT] WebSocket loop fechado.")

        self.websocket = None
        self.websocket_loop = None # Força a criação de um novo loop/thread
        self.ws_thread = None # Permite que uma nova thread seja criada
        print("[CLIENT] Variáveis de WebSocket resetadas.")

        # Reinicia o estado do jogo
        self.game_state = "disconnected"
        self.round_result = {}
        self.voting_cards = []
        self.selected_card_index = -1
        self.selected_vote_index = -1
        self.hand = []
        self.current_black_card = ""
        self.scores = {}
        self.submitted_count = 0
        self.countdown = 0
        self.player_name = ""
        self.room_code = ""
        self.input_text = ""
        self.input_active = True
        self.input_type = "name"
        self.has_submitted_this_round = False
        self.has_voted_this_round = False
        self.hover_card_index = -1
        self.set_message("Bem-vindo! Digite seu nome para começar.", COLOR_TEXT_LIGHT)
        print("[CLIENT] Cliente redefinido para estado inicial.")


    def run(self):
        clock = pygame.time.Clock()
        
        self.input_active = True
        self.set_message("Bem-vindo! Digite seu nome para começar.", COLOR_TEXT_LIGHT)

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event.pos)
            
            self.draw()
            clock.tick(60)
        
        # Cleanup final
        # Garante que o loop do WebSocket é parado e fechado ao sair do Pygame
        if self.websocket_loop and self.websocket_loop.is_running():
            self.websocket_loop.call_soon_threadsafe(self.websocket_loop.stop)
            # Permite que a thread termine
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=1.0) # Espera a thread terminar
        if self.websocket_loop and not self.websocket_loop.is_closed():
            self.websocket_loop.close()
            print("[CLIENT] WebSocket loop fechado durante cleanup final.")
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    client = GameClient()
    client.run()