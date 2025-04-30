import pygame
import numpy as np
import random
import platform

# Conditional import for asyncio only when needed
if platform.system() == "Emscripten":
    import asyncio

# Game Constants
WIDTH, HEIGHT = 800, 600
FPS = 60
PADDLE_WIDTH, PADDLE_HEIGHT = 18, 90
BALL_SIZE = 12
MAX_SCORE = 11

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

class BoneCrusherSound:
    def __init__(self):
        self.sample_rate = 44100
        try:
            pygame.mixer.init(frequency=self.sample_rate)
            self.channels = [pygame.mixer.Channel(i) for i in range(4)]
            self.sound_enabled = True
            print("Sound initialized successfully.")
        except pygame.error as e:
            print(f"Warning: Could not initialize sound mixer: {e}")
            print("Sound will be disabled.")
            self.channels = []
            self.sound_enabled = False

    def _raw_sound(self, wave, vol):
        if not self.sound_enabled:
            return None # Return None if sound is disabled
        # Ensure wave is 1D before reshaping
        wave = np.asarray(wave).flatten()
        # Ensure it has 2 dimensions for make_sound (samples, channels=1)
        wave = wave.reshape(-1, 1)
        # Ensure dtype is suitable for int16 conversion
        if wave.dtype != np.float64 and wave.dtype != np.float32:
             wave = wave.astype(np.float32)
        # Clamp values *after* scaling by volume
        sound_array = np.int16(np.clip(wave * vol, -1.0, 1.0) * 32767)
        return pygame.sndarray.make_sound(sound_array)

    def _pulse_wave(self, freq, duration, duty=0.3):
        t = np.linspace(
            0, duration, int(self.sample_rate * duration), endpoint=False
        )
        # More robust pulse wave generation
        phase = 2 * np.pi * freq * t
        wave = np.where(np.sin(phase) > np.sin(duty * np.pi), 1.0, -1.0)
        # Apply fade out
        wave *= np.linspace(1, 0, len(t))**2 # Exponential fade sounds better
        return wave

    def _crunch_noise(self, duration):
        samples = int(self.sample_rate * duration)
        noise = np.random.uniform(-1, 1, samples)
        # Apply fade out
        noise *= np.linspace(1, 0, samples)**2 # Exponential fade
        return noise

    def _play_on_channel(self, channel_index, sound_generator, *args, vol=0.5, **kwargs):
        """Helper to play sound on a specific channel if available and sound enabled."""
        if not self.sound_enabled or channel_index >= len(self.channels):
            return
        channel = self.channels[channel_index]
        if not channel.get_busy():
            # Generate the base wave without volume scaling
            wave = sound_generator(*args, **kwargs)
            # Apply volume in _raw_sound
            sound_obj = self._raw_sound(wave, vol=vol) # Pass volume here
            if sound_obj: # Check if sound object was created
                channel.play(sound_obj)

    def play_paddle_hit(self):
        freq = 800 + random.random() * 400
        # Pass desired volume to _play_on_channel
        self._play_on_channel(0, self._pulse_wave, freq, 0.08, duty=0.1, vol=0.4)

    def play_wall_hit(self):
         # Pass desired volume to _play_on_channel
        self._play_on_channel(1, self._crunch_noise, 0.06, vol=0.3)

    def play_score(self):
        # Generator now only creates the wave shape, volume applied later
        def score_wave_gen(duration=0.4): # Removed vol parameter
             t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)
             freq = np.linspace(1500, 200, len(t)) # Frequency sweep down
             wave = np.sign(np.sin(2 * np.pi * freq * t)) # Simple square-like wave
             wave *= np.linspace(1, 0, len(t))**2 # Fade out
             return wave # Removed volume scaling
        # Pass the generator function and its arguments, plus the desired volume
        self._play_on_channel(2, score_wave_gen, duration=0.4, vol=0.5)


    def play_victory(self):
         # Generator now only creates the wave shape, volume applied later
         def victory_wave_gen(): # Removed vol parameter
            tones = []
            # Slightly longer tones, clearer progression
            for freq, dur in zip([440, 554, 659], [0.15, 0.15, 0.25]): # A4, C#5, E5
                tone = self._pulse_wave(freq, dur, duty=0.5) # 50% duty cycle (square)
                tones.append(tone)
                tones.append(np.zeros(int(self.sample_rate * 0.05))) # Short gap
            return np.concatenate(tones) # Removed volume scaling
         # Pass the generator function and the desired volume
         self._play_on_channel(3, victory_wave_gen, vol=0.6)


class StreetPong:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("STREET PONG: ELECTRIC BOOGALOO")
        self.clock = pygame.time.Clock()
        self.sound = BoneCrusherSound()
        self.victory_sound_played = False
        self.font_big = pygame.font.Font(None, 100) # Pre-load fonts
        self.font_med = pygame.font.Font(None, 80)
        self.reset_game()

    def reset_round(self):
        """Reset paddles and ball position after a point, keeping scores."""
        self.paddles = [
            pygame.Rect(
                30, HEIGHT // 2 - PADDLE_HEIGHT // 2, PADDLE_WIDTH, PADDLE_HEIGHT
            ),
            pygame.Rect(
                WIDTH - 30 - PADDLE_WIDTH,
                HEIGHT // 2 - PADDLE_HEIGHT // 2,
                PADDLE_WIDTH,
                PADDLE_HEIGHT,
            ),
        ]
        self.ball = pygame.Rect(
            WIDTH // 2 - BALL_SIZE // 2,
            HEIGHT // 2 - BALL_SIZE // 2,
            BALL_SIZE,
            BALL_SIZE,
        )
        # Ensure initial ball speed has reasonable vertical component
        initial_vx = random.choice([-6, 6])
        initial_vy = random.uniform(-4, 4)
        while abs(initial_vy) < 1: # Avoid too horizontal initial movement
             initial_vy = random.uniform(-4, 4)
        self.ball_speed = [initial_vx, initial_vy]


    def reset_game(self):
        """Reset the entire game, including scores, for a new game."""
        self.reset_round()
        self.scores = [0, 0]
        self.victory_sound_played = False
        self.game_over = False # Add a game over flag

    def _smack_ball(self, paddle_idx):
        paddle = self.paddles[paddle_idx]
        # Normalize offset between -1 and 1
        offset = (self.ball.centery - paddle.centery) / (PADDLE_HEIGHT / 2)
        offset = np.clip(offset, -1, 1) # Clamp offset

        # Max reflection angle (e.g., 60 degrees = pi/3 radians)
        max_angle = np.pi / 3
        angle = offset * max_angle

        # Increase base speed slightly on hit, add randomness
        base_speed_x = 7.5 + random.uniform(0, 1)
        base_speed_y = 8.0 + random.uniform(0, 1)

        # Determine horizontal direction based on paddle
        direction_x = 1 if paddle_idx == 0 else -1

        self.ball_speed = [
            direction_x * base_speed_x * np.cos(angle), # Adjust x based on angle
            base_speed_y * np.sin(angle) # y speed based on angle
        ]

        # Prevent ball getting stuck inside paddle
        if paddle_idx == 0:
            self.ball.left = paddle.right
        else:
            self.ball.right = paddle.left

        self.sound.play_paddle_hit()

    def _update_physics(self):
        # Paddle movement
        keys = pygame.key.get_pressed()
        speed = 9
        # Player 1 (Left)
        if keys[pygame.K_w]:
            self.paddles[0].y -= speed
        if keys[pygame.K_s]:
            self.paddles[0].y += speed
        # Player 2 (Right)
        if keys[pygame.K_UP]:
            self.paddles[1].y -= speed
        if keys[pygame.K_DOWN]:
            self.paddles[1].y += speed

        # Clamp paddles within screen bounds
        for p in self.paddles:
            p.clamp_ip(self.screen.get_rect()) # Use pygame's clamp_ip

        # Ball movement
        self.ball.x += self.ball_speed[0]
        self.ball.y += self.ball_speed[1]

        # Wall bounces (Top/Bottom)
        if self.ball.top <= 0:
            self.ball.top = 0
            self.ball_speed[1] *= -1
            self.sound.play_wall_hit()
        elif self.ball.bottom >= HEIGHT:
            self.ball.bottom = HEIGHT
            self.ball_speed[1] *= -1
            self.sound.play_wall_hit()

        # Paddle collisions
        for i, paddle in enumerate(self.paddles):
            if self.ball.colliderect(paddle):
                # Check direction to prevent multiple hits / hitting back side
                is_hitting_p0 = i == 0 and self.ball_speed[0] < 0
                is_hitting_p1 = i == 1 and self.ball_speed[0] > 0
                if is_hitting_p0 or is_hitting_p1:
                    self._smack_ball(i)
                    # Speed cap to prevent excessive acceleration
                    speed_magnitude = np.sqrt(self.ball_speed[0]**2 + self.ball_speed[1]**2)
                    max_speed = 15 # Example max speed
                    if speed_magnitude > max_speed:
                        scale = max_speed / speed_magnitude
                        self.ball_speed[0] *= scale
                        self.ball_speed[1] *= scale
                    break # Only handle one paddle collision per frame

        # Scoring
        scored = False
        if self.ball.left <= 0: # Player 2 scores
            self.scores[1] += 1
            scored = True
        elif self.ball.right >= WIDTH: # Player 1 scores
            self.scores[0] += 1
            scored = True

        if scored:
            self.sound.play_score()
            # Check for game over condition
            if max(self.scores) >= MAX_SCORE:
                self.game_over = True
                self.victory_sound_played = False # Reset flag for next potential victory sound
            else:
                self.reset_round() # Reset for next point if game not over


    def _draw_arena(self):
        self.screen.fill(BLACK)

        # Dashed center line
        for y in range(10, HEIGHT - 10, 35): # Start/end away from edges
            pygame.draw.rect(self.screen, WHITE, (WIDTH // 2 - 2, y, 4, 20))

        # Paddles
        for p in self.paddles:
            pygame.draw.rect(self.screen, WHITE, p)

        # Ball
        pygame.draw.ellipse(self.screen, WHITE, self.ball)

        # Scores
        score_text = f"{self.scores[0]}   {self.scores[1]}"
        text_surface = self.font_big.render(score_text, True, WHITE)
        text_rect = text_surface.get_rect(center=(WIDTH // 2, 50))
        self.screen.blit(text_surface, text_rect)

    def _draw_game_over(self):
        if not self.victory_sound_played:
            self.sound.play_victory()
            self.victory_sound_played = True

        # Determine winner text
        win_diff = abs(self.scores[0] - self.scores[1])
        winner = 0 if self.scores[0] > self.scores[1] else 1
        if win_diff >= 5:
            end_text = f"PLAYER {winner + 1} FATALITY!"
        else:
             end_text = f"PLAYER {winner + 1} WINS!"

        # Render winner text
        text_surface = self.font_med.render(end_text, True, WHITE)
        text_rect = text_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40))
        self.screen.blit(text_surface, text_rect)

        # Render restart instruction
        restart_text = "Press SPACE to Play Again"
        restart_surface = self.font_med.render(restart_text, True, WHITE)
        restart_rect = restart_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40))
        self.screen.blit(restart_surface, restart_rect)


    def handle_input(self):
        """Handles events like quitting and restarting."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False  # Signal to quit the game loop

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and self.game_over:
                    self.reset_game() # Reset the game if space is pressed on game over screen

        return True # Signal to continue the game loop

    def update(self):
        """Update game state (physics)."""
        if not self.game_over:
            self._update_physics()

    def draw(self):
        """Draw everything to the screen."""
        self._draw_arena()
        if self.game_over:
            self._draw_game_over()
        pygame.display.flip()

    def run_sync(self):
        """Synchronous game loop for desktop."""
        print("Running sync mode for Desktop")
        running = True
        while running:
            # 1. Handle Input
            running = self.handle_input()
            if not running:
                break

            # 2. Update State
            self.update()

            # 3. Draw Screen
            self.draw()

            # 4. Control Frame Rate
            self.clock.tick(FPS)

        pygame.quit()
        print("Sync game loop finished.")

# === Asynchronous Main Function (for Emscripten/WebAssembly) ===
async def main_async():
    """Asynchronous game loop for Emscripten."""
    print("Running async mode for Emscripten")
    game = StreetPong()
    running = True
    while running:
        # 1. Handle Input (needs to check events without blocking)
        running = game.handle_input() # Reuse the same input handler
        if not running:
            break

        # 2. Update State
        game.update()

        # 3. Draw Screen
        game.draw()

        # 4. Control Frame Rate & Yield
        game.clock.tick(FPS) # Still use tick for pacing
        await asyncio.sleep(0) # IMPORTANT: Yield control to browser event loop

    pygame.quit()
    print("Async game loop finished.")

# === Entry Point ===
if __name__ == "__main__":
    # Check the platform system
    is_emscripten = platform.system() == "Emscripten"

    if is_emscripten:
        # We need asyncio for Emscripten (already imported conditionally at top)
        # import asyncio # Removed redundant import
        print("Platform detected as Emscripten.")
        asyncio.run(main_async())
    else:
        # Run the synchronous version for desktop
        print(f"Platform detected as {platform.system()} (Desktop).")
        game = StreetPong()
        game.run_sync()

