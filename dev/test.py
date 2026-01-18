from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

class SimpleApp(App):
    """A simple Textual application."""

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        yield Static("Hello, Textual!", id="hello")

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

if __name__ == "__main__":
    app = SimpleApp()
    app.run()
