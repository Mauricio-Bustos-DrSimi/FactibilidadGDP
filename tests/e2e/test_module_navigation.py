from __future__ import annotations

from contextlib import closing
from pathlib import Path
import socket
import threading
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright
import pytest
import uvicorn

from app.main import app
from tests.characterization.support import seed_candidate, seed_user


CHROME_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="module")
def live_application_url():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("The isolated characterization server did not start")
    try:
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert thread.is_alive() is False


@pytest.fixture(scope="module")
def browser():
    executable = next((path for path in CHROME_PATHS if path.is_file()), None)
    if executable is None:
        pytest.skip("Chrome or Edge is required for browser characterization")
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            executable_path=str(executable),
            headless=True,
        )
        try:
            yield instance
        finally:
            instance.close()


def _login(page, base_url: str, email: str, password: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    page.locator("#loginScreen").wait_for(state="visible")
    page.locator("#loginEmail").fill(email)
    page.locator("#loginPassword").fill(password)
    page.locator("#loginForm button[type=submit]").click()
    page.locator("#moduleMenu").wait_for(state="visible")


def test_browser_switches_between_gdp_and_factibility_and_enter_saves_comment(
    live_application_url,
    browser,
):
    candidate = seed_candidate(projection_id=990501, group="opening")
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(5_000)
    page.set_default_navigation_timeout(5_000)
    try:
        _login(
            page,
            live_application_url,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        page.evaluate("""() => {
            const user = JSON.parse(localStorage.getItem('siteSwiper.v1.lastUser'));
            localStorage.setItem(`siteswiper.onboarding.v1.${user.id}`, 'done');
        }""")

        page.locator("#gestorModuleBtn").click()
        page.locator("#sidebar").wait_for(state="visible")
        page.locator("#funnelPanel").wait_for(state="visible")
        assert page.locator("#funnelPanel h2").inner_text() == "Embudo"
        assert page.locator("#toggleViewBtn").inner_text() == "Street View"
        assert page.locator("#tableViewBtn").is_visible()

        page.locator("#toggleViewBtn").click()
        page.wait_for_function(
            "document.querySelector('#toggleViewBtn').textContent === 'Mapa'"
        )
        assert page.locator("#toggleViewBtn").inner_text() == "Mapa"
        assert page.locator("#streetview").is_visible()

        page.locator("#tableViewBtn").click()
        page.locator("#candidateTableView").wait_for(state="visible")
        assert page.locator("#candidateTableView h2").inner_text() == "Locales candidatos"

        page.locator("#moduleBackBtn").click()
        page.locator("#moduleMenu").wait_for(state="visible")
        page.locator("#factibilityModuleBtn").click()
        page.locator("#factibilityView").wait_for(state="visible")

        location = page.locator(
            f'.factibility-location[data-candidate-id="{candidate.id}"]'
        )
        location.wait_for(state="visible")
        location.locator(".factibility-location-summary").click()
        row = location.locator(
            '.factibility-subtask[data-task-key="legal_recepcion_oportunidad"]'
        )
        row.wait_for(state="visible")
        comment = row.locator(".factibility-comment")
        comment.fill("Guardado mediante ENTER")
        with page.expect_response(
            lambda response: (
                response.request.method == "PUT"
                and response.url.endswith(
                    f"/factibilidad/locations/{candidate.id}/tasks/legal_recepcion_oportunidad"
                )
            )
        ) as saved:
            comment.press("Enter")
        assert saved.value.status == 200

        stored = page.evaluate(
            """async ({candidateId}) => {
                const response = await fetch('/factibilidad/locations');
                const locations = await response.json();
                const item = locations.find(row => row.candidate.id === candidateId);
                return item.task_groups
                    .flatMap(group => group.subtasks)
                    .find(task => task.key === 'legal_recepcion_oportunidad');
            }""",
            {"candidateId": candidate.id},
        )
        assert stored["comment"] == "Guardado mediante ENTER"
    finally:
        context.close()


def test_browser_keeps_denied_user_in_module_selector(live_application_url, browser):
    seed_user(
        "characterization-denied@example.test",
        "characterization-denied-password",
    )
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(5_000)
    page.set_default_navigation_timeout(5_000)
    try:
        _login(
            page,
            live_application_url,
            "characterization-denied@example.test",
            "characterization-denied-password",
        )
        page.locator("#factibilityModuleBtn").click()
        toast = page.locator("#toast.centered:not(.hidden)")
        toast.wait_for(state="visible")

        assert toast.inner_text() == (
            "Acceso denegado, su usuario no tiene permiso para realizar esta acción."
        )
        assert page.locator("#moduleMenu").is_visible()
        assert page.locator("#factibilityView").is_hidden()
    finally:
        context.close()
