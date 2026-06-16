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
        self.start_ms = 0 # Tracks the bounds of the active interval for the monitor
        self.end_ms = 0   
        self.marks = [] # Stores all user-defined timestamp marks (ms)
        self._effective_marks_cache = [] # Cached sorted list for interval lookups
        # internal debounce to avoid immediate re-trigger after restarting loop
        self._last_draw_timeline_time = 0.0
        self._draw_timeline_min_interval = 0.1 # seconds, roughly 10 FPS for timeline redraw
        self._last_loop_restart = 0.0
        # track mouse position for context menu
        self._menu_click_pos = (0, 0)
        
        # Build the User Interface
        self._playhead_id = None
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
        # Updated context menu for defining multiple loops
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Add Mark Here", command=self._add_mark_at_click)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Clear All Marks", command=self._clear_all_marks)
        self.context_menu.add_command(label="Delete Nearest Mark", command=self._delete_nearest_mark)
        self.timeline_canvas.bind('<Button-3>', self._show_context_menu)
        self.timeline_canvas.bind('<Button-1>', self._on_timeline_click)

        # Canvas interaction settings
        self._canvas_left_margin = 60
        self._canvas_right_margin = 80
        self._row_height = 28
        self._row_seconds = 90
        self._pixels_per_second = 4.5
        self._dragging_tag = None

        # Keyboard shortcuts
        self.root.bind('<space>', self.toggle_pause)
        self.root.bind('<Control-m>', lambda e: self._add_mark_at_current_pos())
        self.root.bind('<Control-M>', lambda e: self._add_mark_at_current_pos())
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

        self.btn_add_mark = ttk.Button(control_frame, text="+ Add Mark", bootstyle=INFO, width=12, command=self._add_mark_at_current_pos, state=DISABLED)
        self.btn_add_mark.pack(side=LEFT, padx=(0, 10))

        # Checkbutton for global looping control
        self.chk_loop_between_marks = ttk.Checkbutton(control_frame, text="Loop Between Marks", variable=self.is_looping_enabled, command=self.draw_timeline, bootstyle="round-toggle")
        self.chk_loop_between_marks.pack(side=LEFT, padx=(0, 10))

        self.btn_pause = ttk.Button(control_frame, text="▶ Start", bootstyle=SUCCESS, width=12, command=self.toggle_pause, state=DISABLED)
        self.btn_pause.pack(side=LEFT, padx=(0, 10))

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
                
                # Reset states
                self.start_ms = 0
                self.end_ms = self.audio_duration_ms
                self.marks = []
                self._effective_marks_cache = sorted([0, self.audio_duration_ms])
                self.lbl_file_name.config(text=f"{os.path.basename(path)} — {self.ms_to_hhmmss(self.audio_duration_ms)}")
                
                pygame.mixer.music.load(self.audio_path)

                # Draw timeline (which now handles markers internally)
                self.draw_timeline()

                # Enable playback
                self.btn_restart.config(state=NORMAL)
                self.btn_add_mark.config(state=NORMAL)
                self.btn_pause.config(state=NORMAL)
                self.stop_audio()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load audio file:\n{str(e)}")

    # --- New timeline helpers (canvas-based) ---
    def ms_to_hhmmss(self, ms: int) -> str:
        total_s = int(ms // 1000)
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _update_time_readouts(self):
        pass # No longer needed for specific top-bar labels

    def draw_timeline(self):
        """Draw stacked rows, each up to self._row_seconds seconds."""
        self.timeline_canvas.delete('all')
        # The playhead was deleted by 'all', so reset the ID to recreate it
        self._playhead_id = None
        self._last_draw_timeline_time = time.time()

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
        """Converts canvas (x, y) coordinates to a millisecond timestamp."""
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
        """Draws all defined loop intervals, the active loop markers, and the pending start marker."""
        self.timeline_canvas.delete('marks_visual') # Delete previous visuals
        if self.audio_duration_ms <= 0:
            return

        row_h = self._row_height
        canvas_w = max(400, self.timeline_canvas.winfo_width() or 400)
        left_margin = self._canvas_left_margin
        right_margin = canvas_w - self._canvas_right_margin

        # Draw all defined marks as grey lines
        for m_ms in self.marks:
            mx, my = self._time_to_canvas(m_ms)
            # Draw mark line
            self.timeline_canvas.create_line(mx, my - row_h//2, mx, my + row_h//2, fill='#888888', width=2, tags=('marks_visual',))

        # Draw the currently active loop markers (self.start_ms, self.end_ms)
        # These are the ones that will be used for actual looping and are more prominent.
        # Only draw if looping is active and a valid active loop exists that is not the full file duration
        if self.is_looping_enabled.get() and self.start_ms < self.end_ms and (self.start_ms != 0 or self.end_ms != self.audio_duration_ms):
            sx, sy = self._time_to_canvas(self.start_ms)
            ex, ey = self._time_to_canvas(self.end_ms)
            
            # Draw a semi-transparent rectangle for the active loop
            current_s_ms = self.start_ms
            while current_s_ms < self.end_ms:
                rect_sx, rect_sy = self._time_to_canvas(current_s_ms)
                
                row_start_ms = int(rect_sy / row_h) * self._row_seconds * 1000
                row_end_ms = row_start_ms + (self._row_seconds * 1000)
                
                rect_end_ms_for_row = min(self.end_ms, row_end_ms)
                rect_ex, rect_ey = self._time_to_canvas(rect_end_ms_for_row)

                draw_sx = max(left_margin, rect_sx)
                draw_ex = min(right_margin, rect_ex)
                
                if draw_ex > draw_sx:
                    self.timeline_canvas.create_rectangle(draw_sx, rect_sy - row_h//2, draw_ex, rect_sy + row_h//2,
                                                        fill='#2a2a4a', outline='', 
                                                        tags='marks_visual')

                current_s_ms = row_end_ms
                if current_s_ms <= self.start_ms: # Safeguard against infinite loop if row_end_ms doesn't advance
                    current_s_ms = self.start_ms + 1 # Small increment to ensure progress

    def _update_playhead(self):
        """Draws a vertical line at the current playback position."""
        if not self.is_playing:
            if self._playhead_id:
                self.timeline_canvas.itemconfig(self._playhead_id, state='hidden')
            return

        current_ms = self._get_current_pos_ms()
        # Clamp playhead for visual consistency
        limit = self.end_ms if self.is_looping_enabled.get() else self.audio_duration_ms
        current_ms = min(current_ms, limit)
        
        px, py = self._time_to_canvas(current_ms)
        row_h = self._row_height

        if self._playhead_id is None:
            # Create it if it was deleted or never existed
            self._playhead_id = self.timeline_canvas.create_line(px, py - row_h//2, px, py + row_h//2, fill='#ffeb3b', width=2, tags='playhead')
        else:
            # Move existing line and ensure it is visible and on top
            self.timeline_canvas.coords(self._playhead_id, px, py - row_h//2, px, py + row_h//2)
            self.timeline_canvas.itemconfig(self._playhead_id, state='normal')
            self.timeline_canvas.tag_raise(self._playhead_id)

    def _on_marker_press(self, event, which):
        pass

    def _on_marker_drag(self, event):
        pass

    def _get_loop_interval_at_ms(self, ms: int):
        """
        Finds the loop interval surrounding the given millisecond position.
        Includes the file start (0ms) and end (audio_duration_ms) as implicit marks.
        """
        if self.audio_duration_ms <= 0:
            return None
            
        # Use cached marks to avoid sorting every 30ms
        effective_marks = self._effective_marks_cache
        if not effective_marks:
            effective_marks = sorted(list(set([0] + self.marks + [self.audio_duration_ms])))
            
        for i in range(len(effective_marks) - 1):
            if effective_marks[i] <= ms < effective_marks[i+1]:
                return (effective_marks[i], effective_marks[i+1])
        
        # Handle case where playback is exactly at or past the end
        if ms >= self.audio_duration_ms:
            return (effective_marks[-2], effective_marks[-1])

        return None

    def _add_mark_at_click(self):
        """Adds a mark at the context menu click position."""
        ms = self._canvas_to_time_ms(*self._menu_click_pos)
        self._add_mark(ms)

    def _add_mark_at_current_pos(self):
        """Adds a mark at the current playback position."""
        if not self.audio_path: return
        ms = self._get_current_pos_ms()
        self._add_mark(ms)

    def _add_mark(self, ms):
        """Internal logic to add a mark and sort the list."""
        if ms not in self.marks:
            self.marks.append(ms)
            self.marks.sort()
            self._effective_marks_cache = sorted(list(set([0] + self.marks + [self.audio_duration_ms])))
            self.draw_timeline()

    def _delete_nearest_mark(self):
        """Deletes the mark closest to the right-click position."""
        ms = self._canvas_to_time_ms(*self._menu_click_pos)
        if not self.marks: return
        
        # Find the mark with the smallest delta to click position
        closest = min(self.marks, key=lambda x: abs(x - ms))
        if abs(closest - ms) < 2000: # Only delete if within 2 seconds of click
            self.marks.remove(closest)
            self._effective_marks_cache = sorted(list(set([0] + self.marks + [self.audio_duration_ms])))
            self.draw_timeline()

    def _clear_all_marks(self):
        """Clears all user-defined marks."""
        self.marks = []
        self._effective_marks_cache = sorted([0, self.audio_duration_ms])
        self.draw_timeline()

    def _on_timeline_click(self, event):
        """Jumps playback to the clicked position unless a marker is being clicked."""
        if not self.audio_path or self._dragging_tag:
            return
            
        try:
            cx = self.timeline_canvas.canvasx(event.x)
            cy = self.timeline_canvas.canvasy(event.y)
            new_ms = self._canvas_to_time_ms(cx, cy)

            # Determine the active loop interval based on click position
            active_loop = self._get_loop_interval_at_ms(new_ms)
            if active_loop:
                self.start_ms, self.end_ms = active_loop
            else:
                self.start_ms = 0 
                self.end_ms = self.audio_duration_ms
                
            pygame.mixer.music.play(loops=0, start=new_ms/1000.0)
            self.play_offset_ms = new_ms
            self.is_playing = True
            self.is_paused = False
            self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
            self._last_loop_restart = time.time() # Stabilize mixer state
            self._update_time_readouts() 
            self._update_playhead() # Update visual position immediately
        except Exception as e:
            print(f"Seek error: {e}")

    def _show_context_menu(self, event):
        if not self.audio_path:
            return
        # Convert screen coordinates to canvas coordinates
        cx = self.timeline_canvas.canvasx(event.x)
        cy = self.timeline_canvas.canvasy(event.y)
        self._menu_click_pos = (cx, cy)
        self.context_menu.post(event.x_root, event.y_root)

    def _get_current_pos_ms(self):
        """Helper to get absolute playback position in ms."""
        if not self.is_playing:
            return self.start_ms
            
        # If we just started or seeked, get_pos() might still report the old position.
        # We assume 0 elapsed time until the stabilization period (100ms) passes.
        if time.time() - self._last_loop_restart < 0.1:
            return self.play_offset_ms

        pos = pygame.mixer.music.get_pos()
        return self.play_offset_ms + (pos if pos != -1 else 0)

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
        if not self.audio_path: return

        play_from_ms = self.start_ms # Default to current start_ms (which might be 0)
        loop_end_ms = self.end_ms # Default to current end_ms (which might be audio_duration_ms)

        # Determine the active interval to highlight based on the current position
        current_pos = self._get_current_pos_ms()
        active_loop = self._get_loop_interval_at_ms(current_pos)
        
        if active_loop:
            play_from_ms, loop_end_ms = active_loop
            self.start_ms, self.end_ms = active_loop
        else:
            self.start_ms = 0
            self.end_ms = self.audio_duration_ms
            play_from_ms = current_pos

        # play() takes loops (-1 for infinite loop logic handled by our monitor), and start time in seconds
        pygame.mixer.music.play(loops=0, start=(play_from_ms / 1000.0))
        self.play_offset_ms = play_from_ms
        
        self._last_loop_restart = time.time() # record restart time to debounce
        self.is_playing = True
        self.is_paused = False
        
        self.btn_pause.config(text="⏸ Pause", bootstyle=WARNING)
        self._update_time_readouts()
        # Removed draw_timeline() here to prevent unnecessary expensive redraws during looping

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
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.btn_pause.config(text="▶ Resume", bootstyle=INFO)

    def stop_audio(self):
        """Halts playback resetting state flags."""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self.btn_pause.config(text="▶ Start", bootstyle=SUCCESS)
        # Clean up playhead when stopped
        self.timeline_canvas.delete('playhead')

    def monitor_playback(self):
        """Runs continuously in the background to enforce the loop end marker."""
        if not self.is_playing or self.is_paused:
            self.root.after(30, self.monitor_playback)
            return

        # Stability guard: Skip monitoring for 150ms after a seek or loop restart.
        # This prevents the app from reacting to stale data from the Pygame mixer.
        if time.time() - self._last_loop_restart < 0.15:
            self.root.after(30, self.monitor_playback)
            return

        try:
            # pygame.mixer.music.get_pos() returns elapsed ms *since play() was called*
            elapsed = pygame.mixer.music.get_pos()
            current_abs_ms = self.play_offset_ms + (elapsed if elapsed != -1 else 0)

            # Store previous active loop boundaries to detect changes for redrawing
            prev_start_ms = self.start_ms
            prev_end_ms = self.end_ms

            # Determine the current active loop based on playback position.
            # We check 5ms behind the current head to ensure that when we hit a mark 
            # (the end of a loop), we stay associated with the interval we just finished 
            # visually until the actual restart occurs.
            check_ms = max(0, current_abs_ms - 5)
            active_loop_at_current_pos = self._get_loop_interval_at_ms(check_ms)
            
            # Always update boundaries for visual highlight if inside an interval
            if active_loop_at_current_pos:
                loop_start, loop_end = active_loop_at_current_pos
                self.start_ms = loop_start
                self.end_ms = loop_end
            else:
                self.start_ms = 0
                self.end_ms = self.audio_duration_ms

            # Perform looping logic if enabled
            if self.is_looping_enabled.get() and active_loop_at_current_pos:
                if (elapsed == -1 or current_abs_ms >= (self.end_ms - 30)):
                    if time.time() - self._last_loop_restart > 0.2:
                        self.play_loop()
            elif elapsed == -1:
                # If music stopped naturally and we aren't looping, stop fully
                self.stop_audio()
            
            # Update playhead position visually
            self._update_playhead()

            # Only redraw timeline (to update active loop highlight) if the active loop boundaries changed
            if (prev_start_ms != self.start_ms or prev_end_ms != self.end_ms) and \
               (time.time() - self._last_draw_timeline_time > self._draw_timeline_min_interval):
                self.draw_timeline()
                self._last_draw_timeline_time = time.time()
        except Exception as e:
            print(f"Monitor error: {e}")
                    
        # Relaxed polling interval (30ms) to reduce CPU churn while maintaining smoothness
        self.root.after(30, self.monitor_playback)