"""Source extractors — interfaces and implementations for P5 research ingest."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExtractorResult:
    title: str
    extracted: str
    pages: Optional[int] = None
    duration: Optional[float] = None


class BaseExtractor(ABC):
    """Interface for source extractors."""

    @abstractmethod
    def supports(self, kind: str) -> bool:
        pass

    @abstractmethod
    def extract(self, content: str, url: Optional[str] = None,
                filename: Optional[str] = None, file_data: Optional[str] = None) -> ExtractorResult:
        """Extract text content from the source. Returns title + extracted text."""
        pass


class TextExtractor(BaseExtractor):
    """Extracts text/markdown as-is."""

    def supports(self, kind: str) -> bool:
        return kind in ("markdown", "text")

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        title = filename or "text"
        return ExtractorResult(title=title, extracted=content)


class WebExtractor(BaseExtractor):
    """Extracts web pages using trafilatura."""

    def supports(self, kind: str) -> bool:
        return kind == "web"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import trafilatura
            extracted = trafilatura.extract(content) or content
            title = ""
            try:
                title = trafilatura.extract_metadata(content, url=url) or ""
            except Exception:
                pass
            return ExtractorResult(title=title or url or "web page", extracted=extracted)
        except ImportError:
            return ExtractorResult(title=url or "web page", extracted=content[:4096])


class PDFExtractor(BaseExtractor):
    """Extracts PDF content using PyMuPDF."""

    def supports(self, kind: str) -> bool:
        return kind == "pdf"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=bytes.fromhex(content), filetype="pdf")
            pages = len(doc)
            text_parts = []
            for page in doc:
                text = page.get_text()
                if text:
                    text_parts.append(f"--- Page {page.number + 1} ---\n{text}")
            extracted = "\n\n".join(text_parts)
            title = filename or "pdf"
            if not extracted.strip():
                # Try OCR via tesseract if available
                try:
                    import subprocess
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                        f.write(bytes.fromhex(content))
                        tmp_path = f.name
                    result = subprocess.run(
                        ["ocrmypdf", "--force-ocr", "-l", "eng", tmp_path, "-"],
                        capture_output=True, text=True, timeout=60
                    )
                    extracted = result.stdout if result.returncode == 0 else "OCR not available"
                except Exception:
                    extracted = "PDF has no text layer and OCR is not available"
            return ExtractorResult(title=title, extracted=extracted, pages=pages)
        except ImportError:
            return ExtractorResult(title=filename or "pdf", extracted="PyMuPDF not installed")


class YouTubeExtractor(BaseExtractor):
    """Extracts YouTube video transcripts."""

    def supports(self, kind: str) -> bool:
        return kind == "youtube"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        """content is the YouTube video ID or URL."""
        try:
            import re
            video_id = content
            if "youtube.com" in content:
                m = re.search(r"v=([a-zA-Z0-9_-]{11})", content)
                if m:
                    video_id = m.group(1)
            elif "youtu.be" in content:
                m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", content)
                if m:
                    video_id = m.group(1)

            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
                text = " ".join([t["text"] for t in transcript])
                return ExtractorResult(title=f"YouTube transcript ({video_id})", extracted=text)
            except Exception:
                pass
            return ExtractorResult(title=f"YouTube ({video_id})", extracted="No transcript available. Consider downloading audio via faster-whisper.")
        except ImportError:
            return ExtractorResult(title="youtube", extracted="youtube-transcript-api not installed")


class AudioVideoExtractor(BaseExtractor):
    """Extracts speech from audio/video files using faster-whisper."""

    def supports(self, kind: str) -> bool:
        return kind in ("audio", "video")

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            from faster_whisper import WhisperModel
            import tempfile
            # For now, log that this would transcribe file_data
            return ExtractorResult(title=filename or "audio", extracted="[Audio transcription would run via faster-whisper]")
        except ImportError:
            return ExtractorResult(title=filename or "audio", extracted="faster-whisper not installed")


class GitHubExtractor(BaseExtractor):
    """Extracts content from GitHub repos."""

    def supports(self, kind: str) -> bool:
        return kind == "github"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        import re
        repo = ""
        if "github.com" in content:
            m = re.search(r"github\.com/([^/]+)/([^/]+)", content)
            if m:
                repo = f"{m.group(1)}/{m.group(2)}"
        else:
            repo = content.strip("/")

        parts = []
        parts.append(f"## Repository: {repo}\n")
        parts.append(f"URL: {url or f'https://github.com/{repo}'}\n")
        parts.append("Note: Full repo extraction requires shallow clone. Showing repo metadata only.")

        # Try to fetch README from API
        try:
            import urllib.request
            import json
            api_url = f"https://api.github.com/repos/{repo}/readme"
            req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github.v3+raw"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                readme = resp.read().decode("utf-8")
                parts.append(f"\n## README\n\n{readme[:2000]}")
        except Exception:
            parts.append("\n## README\n\n[Could not fetch README — repo may not exist or rate-limited]")

        return ExtractorResult(title=f"GitHub: {repo}", extracted="\n".join(parts))


class ArXivExtractor(BaseExtractor):
    """Extracts from arXiv via API."""

    def supports(self, kind: str) -> bool:
        return kind == "arxiv"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        import xml.etree.ElementTree as ET
        entry_ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        try:
            import urllib.request
            search_id = content.strip()
            url = f"http://export.arxiv.org/api/query?id_list={search_id}"
            with urllib.request.urlopen(url, timeout=15) as resp:
                xml_data = resp.read().decode("utf-8")
            root = ET.fromstring(xml_data)
            entry = root.find("{http://www.w3.org/2005/Atom}entry")
            if entry is None:
                return ExtractorResult(title="arxiv", extracted="No entry found for arXiv ID")
            title_el = entry.find("{http://www.w3.org/2005/Atom}title")
            summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
            title = title_el.text.strip().replace("\n", " ") if title_el is not None else "Unknown"
            summary = summary_el.text.strip() if summary_el is not None else ""
            authors = []
            for author in entry.findall("{http://www.w3.org/2005/Atom}author"):
                name = author.find("{http://www.w3.org/2005/Atom}name")
                if name is not None:
                    authors.append(name.text)
            return ExtractorResult(
                title=f"arXiv: {title}",
                extracted=f"Title: {title}\nAuthors: {', '.join(authors)}\nAbstract: {summary}"
            )
        except Exception as e:
            return ExtractorResult(title="arxiv", extracted=f"Error fetching arXiv: {e}")


class DocxExtractor(BaseExtractor):
    """Extracts DOCX content."""

    def supports(self, kind: str) -> bool:
        return kind == "docx"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import tempfile
            from docx import Document
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
                f.write(bytes.fromhex(content))
                doc = Document(f.name)
            text = "\n\n".join([p.text for p in doc.paragraphs if p.text])
            return ExtractorResult(title=filename or "docx", extracted=text[:4096])
        except ImportError:
            return ExtractorResult(title=filename or "docx", extracted="python-docx not installed")


class ImageExtractor(BaseExtractor):
    """Extracts content from images via OCR or vision."""

    def supports(self, kind: str) -> bool:
        return kind == "image"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        # For now, provide a stub — Claude vision would handle binary image data
        return ExtractorResult(title=filename or "image", extracted="[Image content — vision model would describe this]")


class EPUBExtractor(BaseExtractor):
    """Extracts EPUB content."""

    def supports(self, kind: str) -> bool:
        return kind == "epub"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import tempfile
            from ebooklib import epub
            with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
                f.write(bytes.fromhex(content))
                book = epub.read_epub(f.name)
            text_parts = []
            for item in book.get_items_of_type(epub.ITEM_DOCUMENT):
                text_parts.append(item.get_content().decode("utf-8")[:2000])
            extracted = "\n\n".join(text_parts)[:8000]
            return ExtractorResult(title=filename or "epub", extracted=extracted)
        except ImportError:
            return ExtractorResult(title=filename or "epub", extracted="ebooklib not installed")


class PPTXExtractor(BaseExtractor):
    """Extracts PPTX content."""

    def supports(self, kind: str) -> bool:
        return kind == "pptx"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import tempfile
            from pptx import Presentation
            with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
                f.write(bytes.fromhex(content))
                prs = Presentation(f.name)
            text_parts = []
            for slide in prs.slides:
                slide_text = " ".join([shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text])
                if slide_text:
                    text_parts.append(slide_text)
            return ExtractorResult(title=filename or "pptx", extracted="\n\n".join(text_parts)[:4096])
        except ImportError:
            return ExtractorResult(title=filename or "pptx", extracted="python-pptx not installed")


class XLSXExtractor(BaseExtractor):
    """Extracts XLSX content."""

    def supports(self, kind: str) -> bool:
        return kind == "xlsx"

    def extract(self, content: str, url=None, filename=None, file_data=None) -> ExtractorResult:
        try:
            import tempfile
            from openpyxl import load_workbook
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                f.write(bytes.fromhex(content))
                wb = load_workbook(f.name, read_only=True)
            text_parts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    row_text = " | ".join([str(cell) for cell in row if cell is not None])
                    if row_text:
                        text_parts.append(row_text)
            return ExtractorResult(title=filename or "xlsx", extracted="\n".join(text_parts)[:4096])
        except ImportError:
            return ExtractorResult(title=filename or "xlsx", extracted="openpyxl not installed")


# Registry mapping kind -> extractor instance
EXTRACTORS: list[BaseExtractor] = [
    TextExtractor(),
    WebExtractor(),
    PDFExtractor(),
    YouTubeExtractor(),
    AudioVideoExtractor(),
    GitHubExtractor(),
    ArXivExtractor(),
    ImageExtractor(),
    EPUBExtractor(),
    PPTXExtractor(),
    XLSXExtractor(),
    DocxExtractor(),
]


def get_extractor(kind: str) -> BaseExtractor | None:
    for ext in EXTRACTORS:
        if ext.supports(kind):
            return ext
    return None
