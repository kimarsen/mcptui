# Contributing to mcptui

First off, thank you for considering contributing to `mcptui`! Whether you're fixing a bug, adding a new feature, or improving documentation, your help is warmly welcomed.

---

## Code of Conduct & Philosophy

- **ASCII / Windows First-Class Citizen:** `mcptui` must look clean and work reliably in any terminal environment, including standard Windows PowerShell and CMD without specialized patched fonts. Avoid Unicode glyphs or emojis that degrade into question mark boxes (`?`) in non-UTF-8 or fallback codepages.
- **Type Safety & Clean Python Standards:** Statically typed Python with PEP 484 type hints throughout (`mypy` / `pyright` clean).
- **Lightweight & Fast:** Keep CLI startup fast and responsive. Built-in demo mode connects instantaneously (<50ms) using in-memory direct transport. Keep runtime RPC operations and UI frame rendering under 10ms. Do not introduce heavy dependencies (such as large web frameworks or unneeded bulky packages) that inflate startup latency or memory footprint.

---

## Development Setup

1. **Fork and Clone the Repository:**
   ```bash
   git clone https://github.com/<your-username>/mcptui.git
   cd mcptui
   ```

2. **Install `uv` (Fast Python Package Manager):**
   If you don't have `uv` installed, get it via:
   - Windows (PowerShell):
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - macOS / Linux:
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```

3. **Install Dependencies & Sync Virtual Environment:**
   ```bash
   uv sync
   ```

4. **Run the TUI in Development Mode:**
   ```bash
   uv run mcptui demo
   ```

---

## Running the Test Suite

We use Python's built-in `unittest` runner. All pull requests must pass all tests before being merged:

```bash
uv run python -m unittest discover -s tests -v
```

To run a specific test:
```bash
uv run python -m unittest tests/test_client.py
```

---

## Submitting Changes

1. **Create a topic branch:**
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. **Make your changes** and add relevant unit tests in the `tests/` directory.
3. **Run tests** and verify everything passes:
   ```bash
   uv run python -m unittest discover -s tests -v
   ```
4. **Commit your changes:**
   ```bash
   git commit -m "feat(tools): add export schema button"
   ```
5. **Push and open a Pull Request** on GitHub!
