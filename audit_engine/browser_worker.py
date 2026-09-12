"""Persistent headless-Chromium worker.

Why this exists: the original design launched a brand-new Chromium process
for every single page render (one per audit). That made `browser.launch()`
-- the single most failure-prone Playwright operation, since it involves
spawning an OS process, allocating shared memory, and opening a debug
socket -- part of the hot path for every audit. In a sandboxed/containerized
environment this launch step turned out to be intermittently flaky (see
git history / support thread: sites correctly showing full content on one
run and "render incomplete" on the very next, with no site-side change).

The fix: launch Chromium ONCE, keep it alive for the lifetime of the app
process, and reuse it across every audit by opening a fresh browser context
per render (contexts are cheap and fully isolate cookies/storage between
renders -- no cross-audit contamination). This removes the flaky operation
from the common case entirely; it only needs to happen again if the
browser process itself crashes, which this module also detects and
recovers from automatically.

Threading note: Playwright's *sync* API is explicitly not safe to call from
multiple threads against the same objects. FastAPI's sync route handlers
run in a threadpool, so we can't just stash a browser in a module global
and call into it from whatever thread happens to be handling a given
request. Instead, a single dedicated background thread owns the
`sync_playwright()` driver connection and the browser for the entire
process lifetime; other threads submit render "jobs" through a queue and
block on a per-job result queue. This serializes renders (one page load at
a time), which is a fine tradeoff for this app's traffic pattern and,
importantly, is what actually eliminates the concurrent-launch races that
contributed to the original flakiness.
"""
import os
import queue
import subprocess
import sys
import threading
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - playwright should always be installed
    sync_playwright = None

_browsers_install_attempted = False
_confirmed_remote_only = False  # set True once local launch has failed and Browserless has
# successfully filled in -- once we know this environment's OS can't run
# Chromium locally at all, skip the (pointless) 3 local-launch retries on
# every subsequent reconnect and go straight to Browserless.


def _ensure_browsers_installed():
    """Self-heal: the published/production container does not run this
    project's start.sh (which is what normally does `playwright install
    chromium` into a project-local directory for the sandbox dev server).
    Production instead runs uvicorn directly, so if nothing has ever
    downloaded the Chromium binary there, every render permanently fails
    with "Executable doesn't exist..." -- silently degrading every audit
    to raw-HTML-only (wrong scores, empty findings) with no obvious signal
    to the user beyond bad results. Rather than depend on the deploy
    pipeline running a particular shell script, make the browser worker
    itself responsible for getting a usable Chromium onto disk the first
    time it's needed, wherever it's running.
    """
    global _browsers_install_attempted
    if _browsers_install_attempted:
        return
    _browsers_install_attempted = True
    try:
        print("[browser_worker] ensuring Playwright Chromium is installed...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, capture_output=True, text=True, timeout=180,
        )
        print("[browser_worker] Playwright Chromium install check complete.")
    except Exception as e:
        print(f"[browser_worker] Playwright Chromium install attempt failed: {e}")

USER_AGENT = "NetclixVisibilityAuditBot/1.0 (+https://netclixmarketing.com)"
LAUNCH_ARGS = ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]

_job_queue: "queue.Queue" = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


class _Job:
    __slots__ = ("url", "wait_until", "timeout_ms", "settle_ms", "content_wait_ms", "result_q")

    def __init__(self, url, wait_until, timeout_ms, settle_ms, content_wait_ms=0):
        self.url = url
        self.wait_until = wait_until
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self.content_wait_ms = content_wait_ms
        self.result_q: "queue.Queue" = queue.Queue(maxsize=1)


def _launch_browser(p):
    """Launch with a couple of quick retries -- covers the case where the
    very first launch attempt on a cold container hits a transient hiccup
    (e.g. filesystem not fully settled right after the volume mounts).
    Also self-heals a missing Chromium binary (see _ensure_browsers_installed
    docstring) by installing it on the first "Executable doesn't exist"
    failure and retrying, instead of failing every render for the rest of
    the process's life.

    If local launch is fundamentally impossible (e.g. the published/
    production container's OS image is missing shared libraries Chromium
    needs -- `libglib-2.0.so.0` and friends -- which no amount of
    `playwright install` can fix, since that only downloads the browser
    binary, not OS packages, and there's no root/apt access to add them),
    falls back to a remote hosted Chromium via Browserless.io's CDP
    WebSocket endpoint when BROWSERLESS_API_KEY is set. This keeps the
    sandbox dev server on the fast local browser (the common case) while
    letting production render reliably without needing control over its
    base container image.

    Returns (browser, is_remote) -- callers use is_remote to decide whether
    to treat the connection as short-lived (see _worker_loop): a remote
    Browserless session is NOT held open for the whole process lifetime
    like a local browser is -- it's reconnected fresh after every render.
    Browserless's hosted sessions can go stale/idle-timeout under a
    day-long-lived single WebSocket connection (this is what caused renders
    to silently start timing out in production after working initially --
    confirmed via the Browserless dashboard showing a growing ratio of
    "timed out" vs "successful" requests on what was, from our side, a
    single unchanging connection), so treating it as ephemeral per-render
    avoids relying on a connection surviving indefinitely.
    """
    global _confirmed_remote_only

    if _confirmed_remote_only:
        remote = _connect_remote_browser(p)
        if remote is not None:
            return remote, True
        raise RuntimeError(
            "Browserless remote connection failed and local Chromium launch "
            "is already confirmed unavailable in this environment"
        )

    last_err = None
    installed_this_call = False
    for attempt in range(3):
        try:
            return p.chromium.launch(args=LAUNCH_ARGS), False
        except Exception as e:
            last_err = e
            print(f"[browser_worker] Chromium launch attempt {attempt + 1}/3 failed: {e}")
            if not installed_this_call and "Executable doesn't exist" in str(e):
                installed_this_call = True
                _ensure_browsers_installed()
                continue
            time.sleep(1.5)

    remote = _connect_remote_browser(p)
    if remote is not None:
        _confirmed_remote_only = True
        return remote, True
    raise last_err


def _connect_remote_browser(p):
    """Connect to a hosted Chromium via Browserless.io's CDP WebSocket
    endpoint, used only as a fallback when local launch is impossible.
    Returns None (never raises) if BROWSERLESS_API_KEY isn't configured or
    the remote connection itself fails after retries, so callers can fall
    through to their existing raw-HTML failure path exactly as before.

    Retries a couple of times with a short backoff before giving up --
    confirmed directly against Browserless's own edge (openresty) that it
    occasionally returns a bare 500 Internal Server Error / drops the
    WebSocket handshake for a few seconds/minutes at a time (their own
    status page shows a history of short multi-minute blips), independent
    of our token/quota/code. A single connect attempt would otherwise
    treat a brief edge hiccup the same as a genuinely dead account, and
    every audit landing in that short window would fail its render for no
    real reason."""
    api_key = os.environ.get("BROWSERLESS_API_KEY")
    if not api_key:
        return None
    ws_endpoint = f"wss://production-sfo.browserless.io?token={api_key}"
    last_err = None
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            print(f"[browser_worker] connecting to Browserless remote browser (attempt {attempt}/{attempts})...")
            browser = p.chromium.connect_over_cdp(ws_endpoint)
            print("[browser_worker] connected to Browserless remote browser.")
            return browser
        except Exception as e:
            last_err = e
            print(f"[browser_worker] Browserless remote connection attempt {attempt}/{attempts} failed: {e}")
            if attempt < attempts:
                time.sleep(2 * attempt)  # 2s, then 4s -- short backoff, not a long stall
    print(f"[browser_worker] Browserless remote connection failed after {attempts} attempts: {last_err}")
    return None


def _worker_loop():
    if sync_playwright is None:
        # No Playwright available at all -- drain the queue with failures
        # forever rather than crashing the thread (callers time out and
        # fall back to raw HTML, same as if rendering failed).
        while True:
            job = _job_queue.get()
            job.result_q.put((None, None))
        return

    with sync_playwright() as p:
        browser, is_remote = _launch_browser(p)
        while True:
            job = _job_queue.get()
            total_bytes = 0

            def _on_response(response):
                nonlocal total_bytes
                try:
                    cl = response.headers.get("content-length")
                    if cl:
                        total_bytes += int(cl)
                except Exception:
                    pass

            try:
                if not browser.is_connected():
                    raise RuntimeError("browser disconnected")
                context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1366, "height": 900})
                try:
                    page = context.new_page()
                    page.on("response", _on_response)
                    page.goto(job.url, wait_until=job.wait_until, timeout=job.timeout_ms)
                    if job.content_wait_ms > 0:
                        # Poll for real, visible text to actually appear in
                        # the DOM instead of trusting a network-based
                        # heuristic. This is deliberately NOT "networkidle":
                        # many real sites never go network-idle (analytics
                        # beacons, chat widgets, long-poll/websocket
                        # connections keep firing indefinitely), which makes
                        # networkidle either hang for the full timeout for
                        # no reason, or return too early on a page that
                        # hasn't actually finished rendering. Polling for
                        # content directly returns as soon as the page is
                        # actually ready (fast path) and still has a hard
                        # ceiling (content_wait_ms) so a page that genuinely
                        # never renders doesn't hang the whole job.
                        try:
                            page.wait_for_function(
                                "document.body && document.body.innerText && "
                                "document.body.innerText.trim().length > 40",
                                timeout=job.content_wait_ms,
                            )
                        except Exception:
                            pass  # timed out waiting for content -- fall through with whatever's there
                    else:
                        page.wait_for_timeout(job.settle_ms)
                    html = page.content()
                    job.result_q.put((html, total_bytes or None))
                finally:
                    context.close()
            except Exception as e:
                print(f"[browser_worker] render failed for {job.url} ({job.wait_until}, {job.timeout_ms}ms): {e}")
                # If the browser itself died (crashed, killed by OOM, etc),
                # relaunch it so subsequent jobs aren't permanently stuck
                # failing for the rest of the process's life.
                try:
                    still_ok = browser.is_connected()
                except Exception:
                    still_ok = False
                if not still_ok:
                    print("[browser_worker] browser appears dead, relaunching...")
                    try:
                        browser, is_remote = _launch_browser(p)
                    except Exception as relaunch_err:
                        print(f"[browser_worker] relaunch failed: {relaunch_err}")
                job.result_q.put((None, None))
                continue

            # Browserless sessions are meant to be short-lived per-task
            # connections, not a single WebSocket held open for the app's
            # entire lifetime -- a day-long-lived connection was going
            # stale and silently timing out (confirmed via the Browserless
            # dashboard: successful requests dropped to near-zero while
            # timed-out requests climbed, all against what was, from our
            # side, one unchanging connection). Reconnect fresh after every
            # render when remote so each render gets its own healthy
            # session; local browsers stay persistent as before (cheap and
            # reliable to keep alive).
            if is_remote:
                try:
                    browser.close()
                except Exception:
                    pass
                try:
                    browser, is_remote = _launch_browser(p)
                except Exception as reconnect_err:
                    print(f"[browser_worker] Browserless reconnect after render failed: {reconnect_err}")
                    # Next job's `browser.is_connected()` check will raise
                    # and trigger the relaunch path above.


def _ensure_worker():
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="browser-worker", daemon=True)
        _worker_thread.start()


def render_page(url: str, wait_until: str = "load", timeout_ms: int = 20000, settle_ms: int = 1000, content_wait_ms: int = 0):
    """Render `url` using the shared persistent browser and return
    (html, total_bytes). Returns (None, None) on any failure (navigation
    timeout, browser crash, no Playwright installed, etc) -- callers should
    treat that the same as before: fall back to raw HTTP HTML.

    If `content_wait_ms` > 0, after the initial navigation settles we poll
    the live DOM for real text to appear (see _worker_loop) instead of a
    flat sleep -- this returns as soon as the page is actually ready
    (often much faster than `settle_ms`) while still enforcing a hard
    ceiling so a page that never finishes rendering doesn't hang the job.
    """
    if sync_playwright is None:
        return None, None
    _ensure_worker()
    job = _Job(url, wait_until, timeout_ms, settle_ms, content_wait_ms)
    _job_queue.put(job)
    try:
        # A little headroom over the navigation timeout itself so a job
        # that's genuinely still working doesn't get abandoned right as it
        # was about to succeed.
        return job.result_q.get(timeout=(timeout_ms / 1000) + (content_wait_ms / 1000) + 20)
    except queue.Empty:
        print(f"[browser_worker] timed out waiting for worker thread on {url}")
        return None, None
