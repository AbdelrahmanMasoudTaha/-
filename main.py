import ttkbootstrap as ttk
from audio_looper import AudioLooperApp

def main():
    app_window = ttk.Window(themename="darkly") # Clean, dark-mode scheme
    app = AudioLooperApp(app_window)
    app_window.mainloop()

if __name__ == "__main__":
    main()