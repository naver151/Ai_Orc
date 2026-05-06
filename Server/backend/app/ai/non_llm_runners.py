"""
Non-LLM AI 러너 모음
각 함수: async (task_text: str, **kwargs) → str

지원 provider_key:
  "search"   — DuckDuckGo 웹 검색 (duckduckgo-search)
  "crawler"  — 웹 크롤러 (requests + BeautifulSoup4)
  "runner"   — Python 코드 실행기 (subprocess)
  "ocr"      — 이미지 텍스트 추출 (easyocr)
  "whisper"  — 음성→텍스트 (openai-whisper 로컬)
"""

from __future__ import annotations
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


# ── 공통 유틸 ──────────────────────────────────────────────────────────────────

def _extract_url(text: str) -> str | None:
    """task_text에서 첫 번째 URL 추출."""
    m = re.search(r'https?://[^\s\'"<>]+', text)
    return m.group(0) if m else None


def _extract_path(text: str, exts: tuple[str, ...]) -> str | None:
    """task_text에서 특정 확장자 파일 경로 추출."""
    pattern = r'[\w./\\:\-]+\.(' + '|'.join(exts) + ')'
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(0) if m else None


def _extract_code(text: str) -> str | None:
    """```python ... ``` 또는 ```...``` 블록에서 코드 추출."""
    m = re.search(r'```(?:python)?\n?([\s\S]+?)```', text)
    if m:
        return m.group(1).strip()
    # 코드 블록 없으면 전체 텍스트를 코드로 간주
    stripped = text.strip()
    if any(kw in stripped for kw in ('import ', 'def ', 'print(', 'for ', 'if ')):
        return stripped
    return None


# ── 1. 웹 검색 ─────────────────────────────────────────────────────────────────

async def run_search(task_text: str, **kwargs) -> str:
    """
    DuckDuckGo 웹 검색.
    task_text에서 검색어를 추출하거나 전체를 쿼리로 사용.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "[웹 검색] 패키지 없음: pip install duckduckgo-search"

    # 검색어 정제: "검색:" 또는 "search:" 키워드 이후 텍스트
    query = task_text.strip()
    for prefix in ("검색:", "search:", "조사:", "찾아:", "검색해줘", "검색해"):
        if prefix in query:
            query = query.split(prefix, 1)[-1].strip()
            break

    # 너무 길면 첫 100자만 사용
    query = query[:100]

    try:
        results = await asyncio.to_thread(_ddg_search, query, max_results=6)
    except Exception as e:
        return f"[웹 검색 오류] {e}"

    if not results:
        return f"[웹 검색] '{query}'에 대한 결과를 찾지 못했습니다."

    lines = [f"🔍 웹 검색 결과: '{query}'\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "제목 없음")
        body  = r.get("body",  "")[:300]
        href  = r.get("href",  "")
        lines.append(f"[{i}] {title}")
        lines.append(f"     {body}")
        lines.append(f"     🔗 {href}\n")

    return "\n".join(lines)


def _ddg_search(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


# ── 2. 웹 크롤러 ───────────────────────────────────────────────────────────────

async def run_crawler(task_text: str, **kwargs) -> str:
    """
    URL을 task_text에서 추출하여 웹 페이지 내용 수집.
    BeautifulSoup4로 본문 텍스트만 추출.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return "[크롤러] 패키지 없음: pip install requests beautifulsoup4"

    url = _extract_url(task_text)
    if not url:
        return "[크롤러] task_text에서 URL을 찾지 못했습니다. URL을 포함해주세요."

    try:
        result = await asyncio.to_thread(_crawl, url)
        return result
    except Exception as e:
        return f"[크롤러 오류] {e}"


def _crawl(url: str) -> str:
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # 불필요한 태그 제거
    for tag in soup(["script", "style", "nav", "footer",
                     "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    # 본문 추출 (article > main > body 순으로 우선)
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", {"id": re.compile(r"content|article|main", re.I)})
        or soup.body
    )
    if body is None:
        return "[크롤러] 본문을 찾지 못했습니다."

    text = body.get_text(separator="\n", strip=True)
    # 연속 빈줄 압축
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 최대 4000자
    MAX = 4000
    if len(text) > MAX:
        text = text[:MAX] + f"\n\n... (이하 {len(text)-MAX}자 생략)"

    title = soup.title.string.strip() if soup.title else url
    return f"🌐 크롤링 결과: {title}\n🔗 {url}\n\n{text}"


# ── 3. 코드 실행기 ─────────────────────────────────────────────────────────────

async def run_code(task_text: str, **kwargs) -> str:
    """
    Python 코드를 격리된 subprocess로 실행.
    task_text에서 ```python ... ``` 블록을 추출하거나 전체를 코드로 실행.
    타임아웃: 30초 / 출력 최대 4000자
    """
    code = _extract_code(task_text)
    if not code:
        return (
            "[코드 실행기] 실행할 코드를 찾지 못했습니다.\n"
            "task에 ```python ... ``` 형식으로 코드를 포함해주세요."
        )

    try:
        result = await asyncio.to_thread(_run_code_sync, code)
        return result
    except Exception as e:
        return f"[코드 실행 오류] {e}"


def _run_code_sync(code: str) -> str:
    """임시 파일에 코드를 쓰고 subprocess로 실행."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        parts = []
        if stdout:
            parts.append(f"📤 출력:\n{stdout}")
        if stderr:
            parts.append(f"⚠️ 오류/경고:\n{stderr}")
        if proc.returncode != 0:
            parts.append(f"종료 코드: {proc.returncode}")

        result = "\n\n".join(parts) if parts else "✅ 코드 실행 완료 (출력 없음)"

        # 최대 4000자
        MAX = 4000
        if len(result) > MAX:
            result = result[:MAX] + f"\n\n... (이하 {len(result)-MAX}자 생략)"

        code_preview = textwrap.indent(code[:200], "  ")
        if len(code) > 200:
            code_preview += "\n  ..."

        return f"🐍 코드 실행 결과\n```python\n{code_preview}\n```\n\n{result}"

    except subprocess.TimeoutExpired:
        return "[코드 실행기] 30초 타임아웃 초과"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── 4. OCR ─────────────────────────────────────────────────────────────────────

_easyocr_reader = None  # 최초 1회만 로드


async def run_ocr(task_text: str, image_path: str | None = None, **kwargs) -> str:
    """
    EasyOCR로 이미지에서 텍스트 추출.
    image_path 파라미터 또는 task_text에서 이미지 경로/URL 추출.
    """
    try:
        import easyocr
    except ImportError:
        return "[OCR] 패키지 없음: pip install easyocr"

    target = image_path or _extract_path(task_text, ("jpg", "jpeg", "png", "bmp", "webp", "tiff"))
    if not target:
        # URL인 경우
        url = _extract_url(task_text)
        if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp")):
            target = url
    if not target:
        return "[OCR] 이미지 경로 또는 URL을 찾지 못했습니다."

    try:
        result = await asyncio.to_thread(_run_ocr_sync, target)
        return result
    except Exception as e:
        return f"[OCR 오류] {e}"


def _run_ocr_sync(target: str) -> str:
    global _easyocr_reader
    import easyocr

    if _easyocr_reader is None:
        _easyocr_reader = easyocr.Reader(["ko", "en"], gpu=False)

    results = _easyocr_reader.readtext(target, detail=0, paragraph=True)
    if not results:
        return "[OCR] 텍스트를 감지하지 못했습니다."

    text = "\n".join(results)
    return f"📄 OCR 결과 ({target})\n\n{text}"


# ── 5. Whisper ─────────────────────────────────────────────────────────────────

_whisper_model = None  # 최초 1회만 로드


async def run_whisper(task_text: str, audio_path: str | None = None, **kwargs) -> str:
    """
    OpenAI Whisper (로컬)로 음성 파일을 텍스트로 변환.
    audio_path 파라미터 또는 task_text에서 파일 경로 추출.
    """
    try:
        import whisper
    except ImportError:
        return "[Whisper] 패키지 없음: pip install openai-whisper"

    audio_exts = ("mp3", "wav", "m4a", "ogg", "flac", "mp4", "mov", "avi", "mkv")
    target = audio_path or _extract_path(task_text, audio_exts)
    if not target:
        return "[Whisper] 오디오/영상 파일 경로를 찾지 못했습니다."
    if not Path(target).exists():
        return f"[Whisper] 파일을 찾을 수 없습니다: {target}"

    try:
        result = await asyncio.to_thread(_run_whisper_sync, target)
        return result
    except Exception as e:
        return f"[Whisper 오류] {e}"


def _run_whisper_sync(audio_path: str) -> str:
    global _whisper_model
    import whisper

    if _whisper_model is None:
        # medium: 한국어 정확도와 속도의 균형점
        _whisper_model = whisper.load_model("medium")

    result = _whisper_model.transcribe(audio_path, language=None)  # 언어 자동 감지
    lang     = result.get("language", "unknown")
    text     = result.get("text", "").strip()
    segments = result.get("segments", [])

    if not text:
        return "[Whisper] 음성을 인식하지 못했습니다."

    # 타임스탬프 포함 버전 (선택)
    ts_lines = []
    for seg in segments[:50]:  # 최대 50 세그먼트
        start = int(seg["start"])
        end   = int(seg["end"])
        ts_lines.append(f"[{start//60:02d}:{start%60:02d} → {end//60:02d}:{end%60:02d}] {seg['text'].strip()}")

    ts_section = "\n".join(ts_lines)
    return (
        f"🎙️ Whisper 전사 결과\n"
        f"파일: {audio_path} | 감지 언어: {lang}\n\n"
        f"[전체 텍스트]\n{text}\n\n"
        f"[타임스탬프]\n{ts_section}"
    )


# ── provider_key → 러너 매핑 ────────────────────────────────────────────────────

NON_LLM_RUNNERS: dict[str, callable] = {
    "search":  run_search,   # 웹 검색
    "crawler": run_crawler,  # 웹 크롤러
    "runner":  run_code,     # Python 코드 실행
    "ocr":     run_ocr,      # 이미지 OCR
    "whisper": run_whisper,  # 음성 전사
}

NON_LLM_LABELS: dict[str, str] = {
    "search":  "🔍 웹 검색",
    "crawler": "🌐 웹 크롤러",
    "runner":  "🐍 코드 실행",
    "ocr":     "📄 OCR",
    "whisper": "🎙️ Whisper",
}
