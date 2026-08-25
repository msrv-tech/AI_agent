# -*- coding: utf-8 -*-
"""Capture screenshots and an MP4 demo of supplier invoice recognition in BP."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import websocket

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_skill_e2e import (
    click_label,
    close_font_dialog,
    focus_prompt,
    replace_focused_text,
)
from automation.ui.web_document_recognition_e2e import (
    activate_agent_tab,
    attach_image_to_latest_recognition_dialog,
    click_created_link_and_verify,
    create_recognition_dialog,
    dismiss_bp_update_info,
    inspect_dialog,
    set_visible_prompt_text,
    switch_mode,
    visible_prompt_value,
    wait_for_agent_state,
    wait_for_created_links_panel,
    wait_for_final_agent_ui,
)
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-bp-demo"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-bp-demo";'
DEFAULT_PDF = REPO_ROOT / "temp" / "Счет на оплату № 6 от 26 августа 2025 г.pdf"
DEFAULT_MEDIA_DIR = REPO_ROOT / "docs" / "articles" / "product_0_9_0_skills" / "media"
DEFAULT_DIAGNOSTICS_DIR = REPO_ROOT / "automation" / "logs" / "supplier_invoice_demo"


def capture_png(test: BrowserQuery1CTest, path: Path) -> None:
    response = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    path.write_bytes(base64.b64decode(response["result"]["data"]))


def show_overlay(test: BrowserQuery1CTest, title: str, subtitle: str = "") -> None:
    payload = json.dumps({"title": title, "subtitle": subtitle}, ensure_ascii=False)
    test._evaluate(
        """
((data) => {
  let box = document.getElementById('ai-agent-demo-overlay');
  if (!box) {
    box = document.createElement('div');
    box.id = 'ai-agent-demo-overlay';
    Object.assign(box.style, {
      position: 'fixed', inset: '0', zIndex: '2147483647', display: 'flex',
      flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(24, 28, 34, 0.94)', color: '#fff', fontFamily: 'Arial, sans-serif',
      pointerEvents: 'none', textAlign: 'center', padding: '48px'
    });
    document.body.appendChild(box);
  }
  box.innerHTML = '<div style="font-size:44px;font-weight:600;line-height:1.2">' + data.title +
    '</div><div style="font-size:24px;margin-top:18px;color:#cfd8e3">' + data.subtitle + '</div>';
  return true;
})(""" + payload + ")"
    )


def hide_overlay(test: BrowserQuery1CTest) -> None:
    test._evaluate("document.getElementById('ai-agent-demo-overlay')?.remove(); true")


def dismiss_demo_guide(test: BrowserQuery1CTest) -> bool:
    geometry = test._evaluate(
        r"""
(()=> {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 5 && r.height > 5 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const titles = Array.from(document.querySelectorAll('div,span')).filter(visible)
    .filter((el) => (el.innerText || '').trim() === 'Путеводитель по демонстрационной базе')
    .sort((a, b) => a.getBoundingClientRect().width - b.getBoundingClientRect().width);
  if (!titles.length) return JSON.stringify({visible:false});
  let owner = titles[0];
  for (let depth = 0; owner && depth < 12; depth++, owner = owner.parentElement) {
    const r = owner.getBoundingClientRect();
    if (r.width > 500 && r.height > 300 && r.width < innerWidth && r.height < innerHeight) {
      return JSON.stringify({visible:true, x:Math.round(r.right - 27), y:Math.round(r.top + 25)});
    }
  }
  return JSON.stringify({visible:true, x:Math.round(innerWidth * 0.885), y:Math.round(innerHeight * 0.49)});
})()
"""
    )
    data = json.loads(geometry)
    if not data.get("visible"):
        return False
    x = int(data["x"])
    y = int(data["y"])
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
    )
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
    )
    time.sleep(2)
    visible_after = test._evaluate(
        r"""
(()=> Array.from(document.querySelectorAll('div,span')).some((el) => {
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return (el.innerText || '').trim() === 'Путеводитель по демонстрационной базе'
    && r.width > 5 && r.height > 5 && s.display !== 'none' && s.visibility !== 'hidden';
}))()
"""
    )
    return visible_after != "True" and visible_after != "true"


def wait_for_demo_guide_and_dismiss(test: BrowserQuery1CTest, timeout_sec: int = 15) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if dismiss_demo_guide(test):
            return True
        time.sleep(1)
    viewport = json.loads(
        test._evaluate("JSON.stringify({width:innerWidth,height:innerHeight})")
    )
    x = int(viewport["width"] * 0.763)
    y = int(viewport["height"] * 0.407)
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
    )
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
    )
    time.sleep(2)
    return True


def wait_for_update_recommendation_and_dismiss(
    test: BrowserQuery1CTest,
    timeout_sec: int = 10,
) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        body = test._safe_body_text()
        if "Рекомендуется обновить версию конфигура" in body:
            clicked = click_label(test, "Закрыть")
            time.sleep(2)
            return clicked.startswith("clicked")
        time.sleep(1)
    return False


def dismiss_delayed_startup_windows(
    test: BrowserQuery1CTest,
    timeout_sec: int = 30,
) -> list[str]:
    closed: list[str] = []
    deadline = time.time() + timeout_sec
    quiet_since: float | None = None
    while time.time() < deadline:
        button_id = test._evaluate(
            r"""
(()=> {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 5 && r.height > 5 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const button = Array.from(document.querySelectorAll('[id$="headerTopLine_cmd_CloseButton"]'))
    .find((el) => visible(el) && el.closest('.cloud'));
  if (!button) return '';
  button.click();
  return button.id;
})()
"""
        )
        if button_id:
            closed.append(button_id)
            quiet_since = None
            time.sleep(2)
            continue
        if closed:
            quiet_since = quiet_since or time.time()
            if time.time() - quiet_since >= 4:
                break
        time.sleep(1)
    return closed


def agent_layout_metrics(test: BrowserQuery1CTest) -> dict[str, object]:
    raw = test._evaluate(
        r"""
(()=> {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 100 && r.height > 100 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const groups = Array.from(document.querySelectorAll('[id$="_mainGroup"]')).filter(visible)
    .sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width);
  if (!groups.length) return JSON.stringify({ok:false, reason:'main group not found'});
  const r = groups[0].getBoundingClientRect();
  return JSON.stringify({
    ok: true,
    viewportWidth: innerWidth,
    viewportHeight: innerHeight,
    x: Math.round(r.x),
    y: Math.round(r.y),
    width: Math.round(r.width),
    height: Math.round(r.height),
    widthRatio: Math.round(r.width / innerWidth * 1000) / 1000
  });
})()
"""
    )
    return json.loads(raw)


def reopen_agent_full_page(test: BrowserQuery1CTest, web_url: str) -> dict[str, object]:
    test._session_call("Page.navigate", {"url": web_url})
    time.sleep(5)
    test._login()
    test._open_agent_command()
    activate_agent_tab(test, 30)
    dismiss_delayed_startup_windows(test)
    if not test._agent_form_visible():
        raise RuntimeError("Agent form was closed while dismissing startup windows")
    metrics = agent_layout_metrics(test)
    if not metrics.get("ok") or float(metrics.get("widthRatio", 0)) < 0.8:
        raise RuntimeError(f"Agent form did not open full-page: {metrics}")
    return metrics


def resolve_ffmpeg() -> Path:
    try:
        import imageio_ffmpeg

        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as exc:
        raise RuntimeError("ffmpeg is required for demo recording") from exc


class BrowserViewportRecorder:
    """Record the active CDP page, independent of monitors and window focus."""

    def __init__(self, debug_port: int, path: Path, ffmpeg_path: Path, fps: int = 15) -> None:
        self.debug_port = debug_port
        self.path = path
        self.ffmpeg_path = ffmpeg_path
        self.fps = fps
        self.ws: websocket.WebSocket | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.latest_frame: bytes | None = None
        self.stop_event = threading.Event()
        self.receiver: threading.Thread | None = None
        self.writer: threading.Thread | None = None
        self.message_id = 10
        self.error = ""
        self.started_at: float | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{self.debug_port}/json/list", timeout=5) as response:
            pages = json.load(response)
        page = next((item for item in pages if item.get("type") == "page" and "fresh-bp-demo" in item.get("url", "")), None)
        if page is None:
            raise RuntimeError("BP browser page was not found for recording")

        self.ws = websocket.create_connection(
            page["webSocketDebuggerUrl"],
            timeout=2,
            http_proxy_host=None,
            http_proxy_port=None,
            origin="http://127.0.0.1",
        )
        self._send("Page.enable")
        self._send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": 100, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1},
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [
                str(self.ffmpeg_path), "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg",
                "-framerate", str(self.fps), "-i", "-", "-vf",
                "scale=1920:-2:flags=lanczos,setsar=1,unsharp=5:5:0.3:3:3:0,pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage",
                "-crf", "14", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(self.path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=flags,
        )
        self.receiver = threading.Thread(target=self._receive_frames, name="cdp-screencast", daemon=True)
        self.writer = threading.Thread(target=self._write_frames, name="video-writer", daemon=True)
        self.receiver.start()
        self.writer.start()
        self.started_at = time.perf_counter()

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        return time.perf_counter() - self.started_at

    def _send(self, method: str, params: dict | None = None) -> None:
        if self.ws is None:
            return
        self.message_id += 1
        self.ws.send(json.dumps({"id": self.message_id, "method": method, "params": params or {}}))

    def _receive_frames(self) -> None:
        assert self.ws is not None
        while not self.stop_event.is_set():
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.error = str(exc)
                return
            if message.get("method") != "Page.screencastFrame":
                continue
            params = message.get("params") or {}
            self.latest_frame = base64.b64decode(params.get("data", ""))
            self._send("Page.screencastFrameAck", {"sessionId": params.get("sessionId")})

    def _write_frames(self) -> None:
        assert self.process is not None and self.process.stdin is not None
        interval = 1 / self.fps
        while not self.stop_event.is_set():
            started = time.perf_counter()
            frame = self.latest_frame
            if frame:
                try:
                    self.process.stdin.write(frame)
                    self.process.stdin.flush()
                except Exception as exc:
                    self.error = str(exc)
                    return
            delay = interval - (time.perf_counter() - started)
            if delay > 0:
                self.stop_event.wait(delay)

    def stop(self, timeout_sec: int = 20) -> str:
        if self.process is None:
            return "not_started"
        self.stop_event.set()
        try:
            self._send("Page.stopScreencast")
        except Exception:
            pass
        if self.receiver is not None:
            self.receiver.join(timeout=3)
        if self.writer is not None:
            self.writer.join(timeout=3)
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except Exception:
                pass
        try:
            self.process.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.process.returncode != 0:
            stderr = self.process.stderr.read() if self.process.stderr is not None else b""
            return stderr.decode("utf-8", errors="replace")[-2000:]
        return self.error or "ok"


def focus_demo_video(
    raw_path: Path,
    output_path: Path,
    ffmpeg_path: Path,
    document_start_sec: float,
) -> dict[str, object]:
    """Reframe the browser recording so 1C form text remains readable in article players."""
    temp_path = output_path.with_suffix(".focused.mp4")
    document_start_sec = max(6.0, document_start_sec)
    filter_graph = (
        "[0:v]split=3[v0][v1][v2];"
        "[v0]trim=start=0:end=5,setpts=PTS-STARTPTS,"
        "scale=1920:-2:flags=lanczos,pad=1920:1080:0:(oh-ih)/2:color=black,setsar=1[intro];"
        f"[v1]trim=start=5:end={document_start_sec:.3f},setpts=PTS-STARTPTS,"
        "crop=iw*0.878:ih*0.922:iw*0.1214:ih*0.078,"
        "scale=1920:-2:flags=lanczos,pad=1920:1080:0:(oh-ih)/2:color=black,setsar=1[agent];"
        f"[v2]trim=start={document_start_sec:.3f},setpts=PTS-STARTPTS,"
        "crop=iw*0.878:ih*0.922:iw*0.1214:ih*0.078,"
        "scale=1920:-2:flags=lanczos,pad=1920:1080:0:(oh-ih)/2:color=black,setsar=1[document];"
        "[intro][agent][document]concat=n=3:v=1:a=0,fps=15,format=yuv420p[outv]"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    encode = subprocess.run(
        [
            str(ffmpeg_path), "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path),
            "-filter_complex", filter_graph, "-map", "[outv]", "-c:v", "libx264",
            "-preset", "slow", "-tune", "stillimage", "-crf", "14", "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    decode = subprocess.run(
        [str(ffmpeg_path), "-v", "error", "-i", str(temp_path), "-f", "null", "-"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    ) if encode.returncode == 0 and temp_path.exists() else None
    ok = encode.returncode == 0 and decode is not None and decode.returncode == 0
    if ok:
        temp_path.replace(output_path)
        raw_path.unlink(missing_ok=True)
    else:
        temp_path.unlink(missing_ok=True)
    return {
        "ok": ok,
        "documentStartSec": round(document_start_sec, 3),
        "error": (decode.stderr if decode is not None else encode.stderr).strip()[-2000:],
    }


def run(args: argparse.Namespace) -> dict:
    media_dir = Path(args.media_dir).resolve()
    media_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir = Path(args.diagnostics_dir).resolve()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(args.pdf).resolve()
    video_path = media_dir / "supplier_invoice_recognition_demo.mp4"
    raw_video_path = media_dir / "supplier_invoice_recognition_demo.raw.mp4"
    result: dict[str, object] = {
        "pdf": str(pdf_path),
        "video": str(video_path),
        "prompt": args.prompt,
    }
    config = WebUiConfig(
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        base_path=DEFAULT_CONNECTION_STRING,
        user=args.user,
        password=args.password,
        query_text="",
        query_params_json="",
        expected_text="",
        timeout_sec=args.timeout_sec,
        log_file=str(diagnostics_dir / "capture_supplier_invoice_demo.log"),
        artifact_dir=str(diagnostics_dir),
        headless=True,
        skip_com_prepare=True,
        window_width=1600,
        window_height=900,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    recording: BrowserViewportRecorder | None = None
    document_start_sec = 0.0
    marker = "создай счет поставщика"
    try:
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        test._login()
        test._open_agent_command()
        result["agentTabActivated"] = activate_agent_tab(test, 30)
        dismiss_bp_update_info(test)
        result["modeSwitch"] = switch_mode(test, "РаспознаваниеДокументов")
        result["newDialogClick"] = click_label(test, "Новый диалог")
        time.sleep(2)
        result["dialog"] = create_recognition_dialog(args.bridge_url)
        result["attachment"] = attach_image_to_latest_recognition_dialog(args.bridge_url, str(pdf_path))
        result["agentFullPage"] = reopen_agent_full_page(test, args.web_url)
        dismiss_bp_update_info(test)
        time.sleep(2)
        result["promptFocus"] = focus_prompt(test)
        replace_focused_text(test, args.prompt)
        if marker not in visible_prompt_value(test).lower():
            result["promptDomSet"] = set_visible_prompt_text(test, args.prompt)
        capture_png(test, media_dir / "supplier_invoice_01_ready.png")

        if not args.skip_video:
            raw_video_path.unlink(missing_ok=True)
            recording = BrowserViewportRecorder(test.debug_port, raw_video_path, resolve_ffmpeg())
            recording.start()
            time.sleep(1)
            show_overlay(test, "Счет поставщика из PDF", "1C AI Agent 0.9.3 · Бухгалтерия предприятия")
            time.sleep(3)
            hide_overlay(test)
            time.sleep(1)

        result["sendClick"] = click_label(test, "Отправить")
        result["agentState"] = wait_for_agent_state(test, args.agent_wait_sec, auto_confirm=True)
        dismiss_bp_update_info(test)
        result["startupWindowsClosed"] = dismiss_delayed_startup_windows(test, 6)
        result.update(
            inspect_dialog(
                args.bridge_url,
                marker,
                "recognize-bp-supplier-invoice",
                "СчетНаОплатуПоставщика",
                pdf_path.name,
            )
        )
        presentations = list(result.get("changedObjectPresentations") or [])
        if not presentations:
            deadline = time.time() + 60
            while time.time() < deadline and not presentations:
                time.sleep(3)
                result.update(
                    inspect_dialog(
                        args.bridge_url,
                        marker,
                        "recognize-bp-supplier-invoice",
                        "СчетНаОплатуПоставщика",
                        pdf_path.name,
                    )
                )
                presentations = list(result.get("changedObjectPresentations") or [])

        result["createdLinksPanel"] = wait_for_created_links_panel(test, presentations, 40)
        result["finalAgentUi"] = wait_for_final_agent_ui(test, presentations, 40)
        capture_png(test, media_dir / "supplier_invoice_02_result.png")
        time.sleep(3)

        presentation = presentations[-1] if presentations else "Счет от поставщика"
        document_start_sec = recording.elapsed() + 0.8 if recording is not None else 0.0
        result["createdLinkClick"] = click_created_link_and_verify(test, presentation, 30)
        time.sleep(4)
        capture_png(test, media_dir / "supplier_invoice_03_document.png")
        if recording is not None:
            show_overlay(test, "Черновик создан", "Документ заполнен и открыт по ссылке из результата агента")
            time.sleep(3)
            hide_overlay(test)
            time.sleep(1)

        result["success"] = bool(
            result.get("docFound")
            and presentations
            and result.get("createdLinksPanel", {}).get("matchedCount", 0) > 0
            and result.get("createdLinkClick", {}).get("opened")
        )
        return result
    finally:
        try:
            hide_overlay(test)
        except Exception:
            pass
        result["recordingStop"] = recording.stop() if recording is not None else "skipped"
        if result["recordingStop"] == "ok" and raw_video_path.exists():
            result["videoFocus"] = focus_demo_video(
                raw_video_path,
                video_path,
                resolve_ffmpeg(),
                document_start_sec,
            )
        elif not args.skip_video:
            result["videoFocus"] = {"ok": False, "error": "raw recording is unavailable"}
        else:
            result["videoFocus"] = {"ok": True, "skipped": True}
        result["videoBytes"] = video_path.stat().st_size if video_path.exists() else 0
        decode = subprocess.run(
            [str(resolve_ffmpeg()), "-v", "error", "-i", str(video_path), "-f", "null", "-"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) if video_path.exists() else None
        result["videoDecode"] = {
            "ok": decode is not None and decode.returncode == 0,
            "error": decode.stderr.strip()[-2000:] if decode is not None else "video file is missing",
        }
        if not args.skip_video and (
            result["recordingStop"] != "ok"
            or not result["videoFocus"]["ok"]
            or result["videoBytes"] <= 0
            or not result["videoDecode"]["ok"]
        ):
            result["success"] = False
        test._close()
        (diagnostics_dir / "capture_supplier_invoice_demo_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture supplier invoice recognition media")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--prompt", default="создай счет поставщика по приложенному PDF")
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--agent-wait-sec", type=int, default=180)
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--media-dir", default=str(DEFAULT_MEDIA_DIR))
    parser.add_argument("--diagnostics-dir", default=str(DEFAULT_DIAGNOSTICS_DIR))
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    result = run(parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
