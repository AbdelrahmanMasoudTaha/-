import os
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import math
import time
import pygame

# Hello there, This Abdelrhman Masoud @7/15/2026
# I made this app to help me recite and memorize the Holy Quran. 
# If you need to change any thing for yourself or for athers you are free 

class AudioLooperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Custom Audio Looper")
        self.root.geometry("900x500")
        self.root.resizable(True, True)

        # Force the window to the front and focus it (useful when launched from CMD)
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        self.root.focus_force()

        # Initialize Pygame Mixer for high-quality audio handling
        pygame.mixer.init()
        pygame.mixer.music.set_volume(0.7)
        
        # Audio State Variables
        self.audio_path = None
        self.is_playing = False
        self.is_paused = False        
        self.is_looping_enabled = tk.BooleanVar(value=True) # Controls global looping state
        self.play_offset_ms = 0 # tracks the timestamp where playback last started
        self.audio_duration_ms = 0  # Total duration in milliseconds
        
        # Loop Points (in milliseconds)
        self.start_ms = 0
        self.end_ms = 0
        # internal debounce to avoid immediate re-trigger after restarting loop
        self._last_loop_restart = 0.0
        # track mouse position for context menu
        self._menu_click_pos = (0, 0)
        
        # Build the User Interface
        self.create_widgets()
        
        # Start the background loop monitor
        self.monitor_playback()

    def create_widgets(self):
        """Creates a clean, descriptive layout for file selection, timeline, and controls."""
        
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=True)
        
        # --- Section 1: File Selection ---
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=X, pady=(0, 20))

        self.btn_browse = ttk.Button(file_frame, text="Open Audio File", bootstyle=PRIMARY, command=self.load_file)
        self.btn_browse.pack(side=LEFT, padx=(0, 10))
        
        self.lbl_file_name = ttk.Label(file_frame, text="No file loaded. Supported: MP3, WAV, OGG", font=("Helvetica", 10, "italic"))
        self.lbl_file_name.pack(side=LEFT, fill=X, expand=True)
        # --- Section 2: Timeline Canvas (stacked rows, 90s per row) ---
        timeline_frame = ttk.LabelFrame(main_frame, text=" Timeline & Loop Points (hh:MM:SS) ")
        timeline_frame.pack(fill=X, pady=(0, 20), padx=8)

        # Top bar of timeline: Readouts and Row selector combined
        top_bar = ttk.Frame(timeline_frame, padding=5)
        top_bar.pack(fill=X)
        
        ttk.Label(top_bar, text="Loop START:").pack(side=LEFT)
        self.lbl_start_time = ttk.Label(top_bar, text="00:00:00", font=("Helvetica", 9, "bold"), foreground="#00c853")
        self.lbl_start_time.pack(side=LEFT, padx=(6, 20))
        
        ttk.Label(top_bar, text="Loop END:").pack(side=LEFT)
        self.lbl_end_time = ttk.Label(top_bar, text="00:00:00", font=("Helvetica", 9, "bold"), foreground="#ff5252")
        self.lbl_end_time.pack(side=LEFT, padx=6)

        # Right-aligned Row selector
        self.combo_rows = ttk.Combobox(top_bar, values=[1, 2, 3, 4, 5, 7, 10, 15, 20], width=5, state="readonly")
        self.combo_rows.set("7")
        self.combo_rows.pack(side=RIGHT, padx=5)
        ttk.Label(top_bar, text="Rows:").pack(side=RIGHT)

        # Canvas where stacked timeline rows are drawn (90s per row)
        # Use a container with a vertical scrollbar for long files
        canvas_container = ttk.Frame(timeline_frame)
        canvas_container.pack(fill=BOTH, expand=True, pady=(8, 2))

        self.timeline_canvas = tk.Canvas(canvas_container, bg="#222222", highlightthickness=0)
        self.timeline_canvas.pack(fill=X, expand=True)

        # redraw timeline when canvas (or window) size changes
        self.timeline_canvas.bind('<Configure>', lambda e: self.draw_timeline())
        self.combo_rows.bind("<<ComboboxSelected>>", lambda e: self.draw_timeline())

        # Context menu for right-click functionality
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Set Start Here", command=self._set_start_at_click)
        self.context_menu.add_command(label="Set End Here", command=self._set_end_at_click)
        self.timeline_canvas.bind('<Button-3>', self._show_context_menu)
        self.timeline_canvas.bind('<Button-1>', self._on_timeline_click)

        # Canvas interaction settings
        self._canvas_left_margin = 60
        self._canvas_right_margin = 80
        self._row_height = 28
        self._row_seconds = 90
        self._pixels_per_second = 4.5
        self._dragging_tag = None

        # Bindings for marker interaction
        self.timeline_canvas.tag_bind('start_marker', '<ButtonPress-1>', lambda e: self._on_marker_press(e, 'start'))
        self.timeline_canvas.tag_bind('end_marker', '<ButtonPress-1>', lambda e: self._on_marker_press(e, 'end'))
        self.timeline_canvas.bind('<B1-Motion>', self._on_marker_drag)
        self.timeline_canvas.bind('<ButtonRelease-1>', self._on_marker_release)

        # Keyboard shortcuts
        self.root.bind('<space>', self.toggle_pause)
        self.root.bind('<Control-s>', self._handle_mark_start)
        self.root.bind('<Control-S>', self._handle_mark_start)
        self.root.bind('<Control-e>', self._handle_mark_end)
        self.root.bind('<Control-E>', self._handle_mark_end)
        self.root.bind('<Up>', self._handle_volume_up)
        self.root.bind('<Down>', self._handle_volume_down)
        self.root.bind('<Left>', lambda e: self._seek(-5000))
        self.root.bind('<Right>', lambda e: self._seek(5000))
        self.root.bind('<Control-i>', lambda e: self.load_file())
        self.root.bind('<Control-I>', lambda e: self.load_file())

        # Separator for visual clarity
        ttk.Separator(main_frame, orient=HORIZONTAL).pack(fill=X, pady=(0, 20))

        # --- Section 3: Playback Controls ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=X)

        self.btn_restart = ttk.Button(control_frame, text="↺ Restart Loop", bootstyle=SUCCESS, width=15, command=self.play_loop, state=DISABLED)
        self.btn_restart.pack(side=LEFT, padx=(0, 10))

        # Radio buttons for global looping control
        self.chk_loop_between_marks = ttk.Checkbutton(control_frame, text="Loop Between Marks", variable=self.is_looping_enabled, command=self._update_status_label_on_loop_toggle, bootstyle="round-toggle")
        self.chk_loop_between_marks.pack(side=LEFT, padx=(0, 10))


        self.btn_pause = ttk.Button(control_frame, text="▶ Start", bootstyle=SUCCESS, width=12, command=self.toggle_pause, state=DISABLED)
        self.btn_pause.pack(side=LEFT, padx=(0, 10))

        self.lbl_status = ttk.Label(control_frame, text="Status: Stopped", font=("Helvetica", 10))
        self._update_status_label_on_loop_toggle()
        self.lbl_status.pack(side=LEFT, padx=10)

        # Volume Control
        volume_frame = ttk.Frame(control_frame)
        volume_frame.pack(side=RIGHT, padx=10)
        ttk.Label(volume_frame, text="Volume:").pack(side=LEFT, padx=(0, 5))
        
        self.volume_var = tk.DoubleVar(value=0.7)
        self.slider_volume = ttk.Scale(volume_frame, from_=0.0, to=1.0, variable=self.volume_var, command=self.update_volume, length=120)
        self.slider_volume.pack(side=LEFT, padx=5)
        self.slider_volume.bind("<Button-1>", self._on_volume_click)
        
        self.lbl_vol_percent = ttk.Label(volume_frame, text="70%", width=4)
        self.lbl_vol_percent.pack(side=LEFT)

    # --- Logic & Audio Event Handlers ---

    def load_file(self):
        """Opens a file dialog, loads the sound properties, and sets timeline boundaries."""
        file_types = [("Audio Files", "*.mp3 *.wav *.ogg")]
        path = filedialog.askopenfilename(title="Select Audio File", filetypes=file_types)
        
        if path:
            try:
                self.audio_path = path
                self.lbl_file_name.config(text=os.path.basename(path), font=("Helvetica", 10, "normal"))
                
                # Load sound data to determine length
                sound = pygame.mixer.Sound(self.audio_path)
                self.audio_duration_ms = int(sound.get_length() * 1000)
                # Set default loop to full file
                self.start_ms = 0
                self.end_ms = self.audio_duration_ms
                # show duration in filename label for quick verification
                self.lbl_file_name.config(text=f"{os.path.basename(path)} — {self.ms_to_hhmmss(self.audio_duration_ms)}")

                # Update text readouts (hh:MM:SS)
                self._update_time_readouts()

                # Draw timeline (which now handles markers internally)
                self.draw_timeline()

                # Enable playback
                self.btn_restart.config(state=NORMAL)
                self.btn_pause.config(state=NORMAL)
                self.stop_audio()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load audio file:\n{str(e)}")

    def on_start_slider_move(self, val):
        """Handles user adjusting the Loop Start slider."""
        self.start_ms = int(float(val))
        self.lbl_start_time.config(text=f"{(self.start_ms / 1000):.2f}s")
        
        # Safety constraint: Prevent start point from surpassing end point
        if self.start_ms >= self.end_ms:
            self.end_ms = min(self.start_ms + 100, self.audio_duration_ms)
            self.slider_end.set(self.end_ms)
            self.lbl_end_time.config(text=f"{(self.end_ms / 1000):.2f}s")

    def on_end_slider_move(self, val):
        """Handles user adjusting the Loop End slider."""
        self.end_ms = int(float(val))
        self.lbl_end_time.config(text=f"{(self.end_ms / 1000):.2f}s")
        
        # Safety constraint: Prevent end point from falling behind start point
        if self.end_ms <= self.start_ms:
            self.start_ms = max(0, self.end_ms - 100)
            self.slider_start.set(self.start_ms)
            self.lbl_start_time.config(text=f"{(self.start_ms / 1000):.2f}s")

    # --- New timeline helpers (canvas-based) ---
    def ms_to_hhmmss(self, ms: int) -> str:
        total_s = int(ms // 1000)
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _update_time_readouts(self):
        self.lbl_start_time.config(text=self.ms_to_hhmmss(self.start_ms))
        self.lbl_end_time.config(text=self.ms_to_hhmmss(self.end_ms))

    def draw_timeline(self):
        """Draw stacked rows, each up to self._row_seconds seconds."""
        self.timeline_canvas.delete('all')
        # use integer seconds to avoid fractional-second artifacts
        total_seconds = max(1, int(math.ceil(self.audio_duration_ms / 1000.0)))

        # Get desired number of rows from UI
        try:
            requested_rows = int(self.combo_rows.get())
        except:
            requested_rows = 7

        if self.audio_duration_ms > 0:
            self._row_seconds = total_seconds / requested_rows

        rows = math.ceil(total_seconds / self._row_seconds)
        canvas_w = max(400, self.timeline_canvas.winfo_width() or 400)
        left = self._canvas_left_margin
        right = canvas_w - self._canvas_right_margin
        self._pixels_per_second = max(1.0, (right - left) / float(self._row_seconds))

        for r in range(rows):
            y0 = r * self._row_height
            y1 = y0 + self._row_height
            # alternating background
            if r % 2 == 0:
                self.timeline_canvas.create_rectangle(0, y0, canvas_w, y1, fill='#101010', outline='')
            # center line
            self.timeline_canvas.create_line(left, y0 + self._row_height//2, right, y0 + self._row_height//2, fill='#404040')

            row_start = r * self._row_seconds
            row_end = min((r + 1) * self._row_seconds, total_seconds)
            row_length = row_end - row_start

            # labels show actual hh:mm:ss for this row's start and end
            self.timeline_canvas.create_text(6, y0 + self._row_height//2, anchor='w', text=self.ms_to_hhmmss(row_start * 1000), fill='#ddd', font=('Helvetica', 9))
            self.timeline_canvas.create_text(right + 6, y0 + self._row_height//2, anchor='w', text=self.ms_to_hhmmss(row_end * 1000), fill='#ddd', font=('Helvetica', 9))

            # ticks every 10s across the actual row_length
            if row_length <= 0:
                continue
            
            # Adjust tick intervals based on row density
            tick_interval = 10 if self._row_seconds > 30 else 5 if self._row_seconds > 10 else 1
            for t in range(0, int(row_length) + 1, tick_interval):
                x = left + t * self._pixels_per_second
                self.timeline_canvas.create_line(x, y0 + 4, x, y1 - 4, fill='#303030')

        total_h = rows * self._row_height
        self.timeline_canvas.config(height=total_h)

        # Ensure markers are redrawn whenever the timeline is refreshed
        if self.audio_path:
            self._draw_markers()

    def _time_to_canvas(self, ms: int):
        seconds = ms / 1000.0
        row = int(seconds // self._row_seconds)
        sec_into_row = seconds - row * self._row_seconds
        canvas_w = max(400, self.timeline_canvas.winfo_width() or 400)
        left = self._canvas_left_margin
        x = left + sec_into_row * self._pixels_per_second
        y = row * self._row_height + self._row_height // 2
        return x, y

    def _canvas_to_time_ms(self, x, y):
        canvas_w = max(400, self.timeline_canvas.winfo_width() or 400)
        left = self._canvas_left_margin
        right = canvas_w - self._canvas_right_margin
        x = max(left, min(right, x))
        row = int(max(0, y // self._row_height))
        sec_into_row = (x - left) / max(1.0, self._pixels_per_second)
        seconds = row * self._row_seconds + sec_into_row
        ms = int(max(0, min(self.audio_duration_ms, seconds * 1000)))
        return ms

    def _draw_markers(self):
        self.timeline_canvas.delete('start_marker')
        self.timeline_canvas.delete('end_marker')
        if self.audio_duration_ms <= 0:
            return

        sx, sy = self._time_to_canvas(self.start_ms)
        ex, ey = self._time_to_canvas(self.end_ms)
        
        row_h = self._row_height
        
        # Start Marker (Green Line + Pointer)
        self.timeline_canvas.create_line(sx, sy - row_h//2, sx, sy + row_h//2, fill='#00c853', width=2, tags=('start_marker',))
        self.timeline_canvas.create_polygon(sx-6, sy-row_h//2, sx+6, sy-row_h//2, sx, sy-row_h//2+8, fill='#00c853', tags=('start_marker',))

        # End Marker (Red Line + Pointer)
        self.timeline_canvas.create_line(ex, ey - row_h//2, ex, ey + row_h//2, fill='#ff5252', width=2, tags=('end_marker',))
        self.timeline_canvas.create_polygon(ex-6, ey-row_h//2, ex+6, ey-row_h//2, ex, ey-row_h//2+8, fill='#ff5252', tags=('end_marker',))

    def _update_playhead(self):
        """Draws a vertical line at the current playback position."""
        self.timeline_canvas.delete('playhead')
        if not self.is_playing:
            return

        current_ms = self._get_current_pos_ms()
        if self.is_looping_enabled.get():
            # Clamp playhead to end_ms for visual consistency during loop
            current_ms = min(current_ms, self.end_ms)
        else:
            # Otherwise clamp to total duration
            current_ms = min(current_ms, self.audio_duration_ms)
        
        px, py = self._time_to_canvas(current_ms)
        row_h = self._row_height
        # Yellow playhead line
        self.timeline_canvas.create_line(px, py - row_h//2, px, py + row_h//2, fill='#ffeb3b', width=2, tags='playhead')

    def _on_marker_press(self, event, which):
        self._dragging_tag = which

    def _on_marker_drag(self, event):
        if not self._dragging_tag:
            return
        canvas_x = self.timeline_canvas.canvasx(event.x)
        canvas_y = self.timeline_canvas.canvasy(event.y)
        new_ms = self._canvas_to_time_ms(canvas_x, canvas_y)
        if self._dragging_tag == 'start':
            self.start_ms = min(new_ms, max(0, self.end_ms - 100))
        else:
            self.end_ms = max(new_ms, min(self.audio_duration_ms, self.start_ms + 100))
        self._update_time_readouts()
        self._draw_markers()

    def _on_marker_release(self, event):
        self._dragging_tag = None

    def _on_timeline_click(self, event):
        """Jumps playback to the clicked position unless a marker is being clicked."""
        if not self.audio_path or self._dragging_tag:
            return
            
        cx = self.timeline_canvas.canvasx(event.x)
        cy = self.timeline_canvas.canvasy(event.y)
        new_ms = self._canvas_to_time_ms(cx, cy)
        
        # Update status label based on global looping setting
        if self.is_looping_enabled.get():
            self.lbl_status.config(text=f"Status: Playing (Loop ON) from {self.ms_to_hhmmss(new_ms)}")
        else:
            self.lbl_status.config(text=f"Status: Playing (Loop OFF) from {self.ms_to_hhmmss(new_ms)}")
            
        # Load (if not already) and restart playback at the clicked absolute position
        pygame.mixer.music.load(self.audio_path)
        pygame.mixer.music.play(loops=0, start=new_ms/1000.0)
        self.play_offset_ms = new_ms
        self.is_playing = True
        self.is_paused = False
        self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
        self._last_loop_restart = time.time()

    def _show_context_menu(self, event):
        if not self.audio_path:
            return
        # Convert screen coordinates to canvas coordinates
        cx = self.timeline_canvas.canvasx(event.x)
        cy = self.timeline_canvas.canvasy(event.y)
        self._menu_click_pos = (cx, cy)
        self.context_menu.post(event.x_root, event.y_root)

    def _set_start_at_click(self):
        new_ms = self._canvas_to_time_ms(*self._menu_click_pos)
        # If the new start point is at or after the current end, reset end to the file's duration
        if new_ms >= self.end_ms:
            self.end_ms = self.audio_duration_ms
        self.start_ms = min(new_ms, max(0, self.end_ms - 100))
        self._update_time_readouts()
        self._draw_markers()

    def _set_end_at_click(self):
        new_ms = self._canvas_to_time_ms(*self._menu_click_pos)
        self.end_ms = max(new_ms, min(self.audio_duration_ms, self.start_ms + 100))
        self._update_time_readouts()
        self._draw_markers()

    def _get_current_pos_ms(self):
        """Helper to get absolute playback position in ms."""
        if not self.is_playing:
            return self.start_ms
        pos = pygame.mixer.music.get_pos()
        return self.play_offset_ms + (pos if pos != -1 else 0)

    def _handle_mark_start(self, event=None):
        if not self.audio_path: return
        curr = self._get_current_pos_ms()
        if curr >= self.end_ms:
            self.end_ms = self.audio_duration_ms
        self.start_ms = min(curr, max(0, self.end_ms - 100))
        self._update_time_readouts()
        self._draw_markers()

    def _handle_mark_end(self, event=None):
        if not self.audio_path: return
        curr = self._get_current_pos_ms()
        self.end_ms = max(curr, min(self.audio_duration_ms, self.start_ms + 100))
        self._update_time_readouts()
        self._draw_markers()

    def _handle_volume_up(self, event=None):
        new_v = min(1.0, self.volume_var.get() + 0.05)
        self.slider_volume.set(new_v)
        self.update_volume(new_v)

    def _handle_volume_down(self, event=None):
        new_v = max(0.0, self.volume_var.get() - 0.05)
        self.slider_volume.set(new_v)
        self.update_volume(new_v)

    def _seek(self, delta_ms):
        """Seek backward or forward by restarting playback at new offset."""
        if not self.audio_path or not self.is_playing:
            return
        curr = self._get_current_pos_ms()
        new_p = max(0, min(self.audio_duration_ms, curr + delta_ms))
        
        # restart playback at seek point
        pygame.mixer.music.play(loops=0, start=new_p/1000.0)
        self.play_offset_ms = new_p
        self.is_paused = False
        self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
        self._last_loop_restart = time.time()

    def _on_volume_click(self, event):
        """Forces the volume slider to jump directly to the clicked position."""
        width = self.slider_volume.winfo_width()
        if width > 0:
            new_val = max(0.0, min(1.0, event.x / width))
            self.slider_volume.set(new_val)
            # Manually trigger update since .set() doesn't fire the widget command
            self.update_volume(new_val)
            return "break"

    def update_volume(self, val):
        """Updates the playback volume (0.0 to 1.0)."""
        vol = float(val)
        pygame.mixer.music.set_volume(vol)
        self.lbl_vol_percent.config(text=f"{int(vol * 100)}%")

    def play_loop(self):
        """Loads and starts audio precisely at the defined starting millisecond."""
        pygame.mixer.music.load(self.audio_path)
        # play() takes loops (-1 for infinite loop logic handled by our monitor), and start time in seconds
        pygame.mixer.music.play(loops=0, start=(self.start_ms / 1000.0))
        self.play_offset_ms = self.start_ms
        
        # record restart time to debounce immediate retriggers
        self._last_loop_restart = time.time()
        self.is_playing = True
        self.is_paused = False
        
        self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
        if self.is_looping_enabled.get():
            self.lbl_status.config(text=f"Status: Looping ({ self.ms_to_hhmmss(self.start_ms)} 🔁 {self.ms_to_hhmmss(self.end_ms)})")
        else:
            self.lbl_status.config(text=f"Status: Playing (Loop OFF) from {self.ms_to_hhmmss(self.start_ms)}")

    def toggle_pause(self, event=None):
        """Toggles the pause state without resetting the playhead. Accepts optional event for spacebar binding."""
        if not self.is_playing:
            # If stopped and user clicks Pause/Play, just start the loop
            self.play_loop()
            return

        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
            self.lbl_status.config(text="Status: Resumed")
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.btn_pause.config(text="▶ Resume", bootstyle=INFO)
            self.lbl_status.config(text="Status: Paused")

    def stop_audio(self):
        """Halts playback resetting state flags."""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self.btn_pause.config(text="▶ Start", bootstyle=SUCCESS)
        self.lbl_status.config(text="Status: Stopped")
        # Clean up playhead when stopped
        self.timeline_canvas.delete('playhead')

    def monitor_playback(self):
        """Runs continuously in the background to enforce the loop end marker."""
        if self.is_playing and not self.is_paused:
            # pygame.mixer.music.get_pos() returns elapsed ms *since play() was called*
            elapsed = pygame.mixer.music.get_pos()

            # If get_pos() returns -1 the music stopped
            if elapsed == -1: # Music stopped (reached end of file or was stopped externally)
                if self.is_looping_enabled.get(): # Only restart if global looping is ON
                    # small debounce to avoid rapid reloading
                    if time.time() - self._last_loop_restart > 0.02:
                        self.play_loop()
                else:
                    # If looping is disabled, stop the state naturally at the end of the file
                    self.stop_audio()
            else: # Music is still playing
                current_abs_ms = self.play_offset_ms + elapsed
                # trigger loop restart only if global looping is ON and we hit the end marker
                if self.is_looping_enabled.get() and current_abs_ms >= (self.end_ms - 20):
                    # avoid immediate retrigger due to timing granularity
                    if time.time() - self._last_loop_restart > 0.02:
                        self.play_loop()
            
            # Update playhead position visually
            self._update_playhead()
                    
        # Check again in 15 milliseconds for near-gapless looping performance
        self.root.after(15, self.monitor_playback)

    def _update_status_label_on_loop_toggle(self):
        """Updates the status label to reflect the global looping state if no audio is playing."""
        if not self.is_playing:
            if self.is_looping_enabled.get():
                self.lbl_status.config(text="Status: Looping ON (Global)")
            else:
                self.lbl_status.config(text="Status: Looping OFF (Global)")

# Window initialization
if __name__ == "__main__":
    app_window = ttk.Window(themename="darkly") # Clean, dark-mode scheme
    app = AudioLooperApp(app_window)
    app_window.mainloop()