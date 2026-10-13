"""
Record an animated demo GIF of mcptui in action.
"""

import asyncio
import io
import os
import sys
from pathlib import Path

from PIL import Image
import resvg_py

from mcptui.ui.app import MCPTuiApp
from mcptui.ui.server_modal import ServerSwitcherModal
from textual.widgets import TextArea, Button


async def record() -> None:
    print("Initializing headless MCPTuiApp pilot...")
    app = MCPTuiApp()

    frames = []
    durations = []

    def capture_frame(duration_ms: int = 1500) -> None:
        svg_content = app.export_screenshot()
        png_bytes = resvg_py.svg_to_bytes(svg_content)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        frames.append(img)
        durations.append(duration_ms)
        print(f"Captured frame #{len(frames)} (duration: {duration_ms}ms)")

    async with app.run_test(size=(116, 32)) as pilot:
        # 1. Allow initial connection to demo server
        print("Waiting for demo server connection...")
        for _ in range(15):
            await pilot.pause(0.2)
            if app.client.is_connected and app.client.tools:
                break

        print(f"Connected! Tools count: {len(app.client.tools)}")
        capture_frame(2000)

        # 2. Select calculate and input expression
        try:
            editor = app.query_one("#tool-params-editor", TextArea)
            editor.text = '{\n  "expression": "42 * 1337"\n}'
            await pilot.pause(0.3)
            capture_frame(1200)

            # 3. Execute tool
            await pilot.click("#btn-execute")
            await pilot.pause(0.8)
            capture_frame(2200)
        except Exception as e:
            print(f"Error in tools demo: {e}")

        # 4. Switch to Resources tab
        try:
            app.action_goto_tab("tab-resources")
            await pilot.pause(0.5)
            capture_frame(1200)

            # Read resource
            await pilot.click("#btn-read-res")
            await pilot.pause(0.8)
            capture_frame(2200)
        except Exception as e:
            print(f"Error in resources demo: {e}")

        # 5. Switch to Prompts tab
        try:
            app.action_goto_tab("tab-prompts")
            await pilot.pause(0.5)
            capture_frame(1200)

            # Get prompt
            await pilot.click("#btn-get-prompt")
            await pilot.pause(0.8)
            capture_frame(2200)
        except Exception as e:
            print(f"Error in prompts demo: {e}")

        # 6. Switch to Protocol Logs tab
        try:
            app.action_goto_tab("tab-logs")
            await pilot.pause(0.5)
            capture_frame(2500)
        except Exception as e:
            print(f"Error in logs demo: {e}")

        # 7. Open F2 Server Switcher modal
        try:
            app.push_screen(ServerSwitcherModal())
            await pilot.pause(0.6)
            capture_frame(2200)
            app.pop_screen()
            await pilot.pause(0.4)
        except Exception as e:
            print(f"Error in modal demo: {e}")

        # 8. Back to Tools tab for loop closure
        app.action_goto_tab("tab-tools")
        await pilot.pause(0.5)
        capture_frame(1500)

    print(f"Total captured frames: {len(frames)}")

    # Optimize and save as animated GIF
    out_dir = Path("assets")
    out_dir.mkdir(exist_ok=True)
    gif_path = out_dir / "demo.gif"

    print(f"Compiling animated GIF to {gif_path}...")
    frames[0].save(
        str(gif_path),
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    file_size_kb = gif_path.stat().st_size / 1024
    print(f"Successfully generated {gif_path} ({file_size_kb:.1f} KB)")


if __name__ == "__main__":
    asyncio.run(record())
