
import pytest
from playwright.sync_api import Page, expect
import os
import time

# Default to local Vite dev server, can be overridden
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
# Short, copyright-free or permissive audio for testing
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=BaW_jenozKc" # "youtube-dl test video"

def test_load_homepage(page: Page):
    """Verify the app loads and shows the main title."""
    print(f"Navigating to {FRONTEND_URL}")
    try:
        page.goto(FRONTEND_URL)
        
        # Check for main title or key element
        expect(page.get_by_text("Music Split", exact=True)).to_be_visible(timeout=10000)
        
        # Check for mode switcher
        expect(page.get_by_role("button", name="Upload")).to_be_visible()
        expect(page.get_by_role("button", name="YouTube")).to_be_visible()
    except Exception:
        page.screenshot(path="tests/web/homepage_failure.png")
        raise

def test_youtube_separation_flow(page: Page):
    """
    Full E2E test:
    1. Switch to YouTube mode
    2. Enter URL
    3. Click Separate
    4. Wait for Processing
    5. Wait for Done
    6. Verify Stems
    """
    page.goto(FRONTEND_URL)
    
    try:
        # 1. Switch to YouTube mode
        # Use role selector for better reliability
        page.get_by_role("button", name="YouTube").click()
        
        # 2. Enter URL
        input_field = page.get_by_placeholder("https://youtube.com/watch?v=...")
        input_field.fill(TEST_YOUTUBE_URL)
        
        # 3. Click Separate
        separate_btn = page.get_by_role("button", name="Start Separation")
        expect(separate_btn).to_be_enabled()
        separate_btn.click()
        
        # 4. Wait for Processing state
        print("Waiting for processing to start...")
        expect(page.get_by_role("button", name="Processing...")).to_be_visible(timeout=10000)
        
        # 5. Wait for Done state
        print("Waiting for separation to complete (this may take a minute)...")
        # We expect at least one stem to appear (e.g., "vocals")
        expect(page.get_by_text("vocals")).to_be_visible(timeout=300000)

        print("✅ Separation complete! Stems found.")
        
        # 6. Verify Audio Players
        audio_elements = page.locator("audio")
        count = audio_elements.count()
        print(f"Found {count} audio players.")
        assert count >= 4, "Expected at least 4 audio players"
        
    except Exception:
        page.screenshot(path="tests/web/separation_failure.png")
        print("❌ Test failed! Screenshot saved to tests/web/separation_failure.png")
        raise

