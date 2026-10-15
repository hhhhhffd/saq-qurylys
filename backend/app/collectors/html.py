"""HTML to plain text for the collectors, keeping line breaks and link addresses."""

import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

_BLOCK_TAGS = frozenset({"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"})
_SPACES = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _is_web_url(value: str) -> bool:
    return urlsplit(value).scheme in {"http", "https"}


def _without_scheme(url: str) -> str:
    return url.split("://", 1)[-1].removeprefix("www.").rstrip("/")


def _collect(node: LexborNode, parts: list[str]) -> None:
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            parts.append(child.text_content or "")
        elif tag == "br":
            parts.append("\n")
        elif tag in {"script", "style"}:
            continue
        else:
            start = len(parts)
            _collect(child, parts)
            if tag == "a":
                href = (child.attributes.get("href") or "").strip()
                shown = "".join(parts[start:])
                # A link whose visible text is the address itself, or a relative one (hashtags), adds nothing.
                if _is_web_url(href) and _without_scheme(href) not in shown:
                    parts.append(f" ({href})")
            elif tag in _BLOCK_TAGS:
                parts.append("\n")


def clean_text(text: str) -> str:
    lines = (_SPACES.sub(" ", line).strip() for line in text.replace("\xa0", " ").split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def node_text(node: LexborNode) -> str:
    """Plain text of an element: `<br>` and block tags become line breaks, links keep their address."""
    parts: list[str] = []
    _collect(node, parts)
    return clean_text("".join(parts))


def fragment_text(html: str) -> str:
    """Plain text of an HTML fragment such as an OLX description."""
    body = LexborHTMLParser(html).body
    return node_text(body) if body is not None else ""


def link_urls(node: LexborNode) -> list[str]:
    """Web addresses of the links inside an element, without repeats."""
    urls = (anchor.attributes.get("href") or "" for anchor in node.css("a[href]"))
    return list(dict.fromkeys(url.strip() for url in urls if _is_web_url(url.strip())))
