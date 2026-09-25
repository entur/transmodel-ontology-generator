from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

DATA_BASE = "https://transmodel-cen.eu/model/js/data/"
ROOT_GUID = "BCA0764C-E944-4e36-B16E-6992C963CC31"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: list[str] = []
        self.heading: list[str] = []
        self.text: list[str] = []
        self.notes: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._heading_level: str | None = None
        self._in_notes = False
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title": self._in_title = True
        if tag in {"h1", "h2", "h3"}: self._heading_level = tag
        if tag in {"script", "style", "noscript"}: self._skip = True
        if tag == "div" and "ObjectDetailsNotes" in dict(attrs).get("class", ""):
            self._in_notes = True
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title": self._in_title = False
        if tag in {"h1", "h2", "h3"}: self._heading_level = None
        if tag in {"script", "style", "noscript"}: self._skip = False
        if tag == "div" and self._in_notes: self._in_notes = False

    def handle_data(self, data: str) -> None:
        if self._skip: return
        value = re.sub(r"<[^>]+>", " ", data)
        value = " ".join(value.split())
        if not value: return
        if self._in_title: self.title.append(value)
        elif self._heading_level: self.heading.append(value)
        if self._in_notes: self.notes.append(value)
        self.text.append(value)


def fetch_page(url: str) -> tuple[str, str, list[str], str] | None:
    try:
        request = Request(url, headers={"User-Agent": "Transmodel ontology generator/0.1"})
        with urlopen(request, timeout=45) as response:
            content = response.read().decode("utf-8", errors="replace")
        parser = PageParser(); parser.feed(content)
        return (" ".join(parser.title), " ".join(parser.heading), parser.links + parser.text, " ".join(parser.notes))
    except Exception:
        return None


def fetch_data(guid: str) -> str | None:
    try:
        request = Request(DATA_BASE + guid + ".xml", headers={"User-Agent": "Transmodel ontology generator/0.1"})
        with urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def parse_entries(content: str) -> list[tuple[str, str]]:
    entries = []
    for line in content.splitlines():
        fields = re.findall(r'"((?:[^"\\]|\\.)*)"', line)
        if len(fields) >= 8 and fields[3].lower().endswith(".htm"):
            entries.append((fields[3], fields[7].strip("{}")))
    return entries


def harvest(output: Path) -> None:
    """Crawl the published Transmodel v6.0 Enterprise Architect HTML export.

    v6.0 was never published as XMI, only as EA-generated HTML pages, so this
    harvest is the only public source of v6.0 definition text. The v6.2 XMI
    extract has very sparse class-level documentation, so generate_transmodel_ttl.py
    overlays these definitions onto v6.2 concepts that share a normalized label.
    """
    queue = [ROOT_GUID]
    seen = set(queue)
    entries: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        while queue:
            batch = queue[:100]
            queue = queue[100:]
            futures = {pool.submit(fetch_data, guid): guid for guid in batch}
            for future in as_completed(futures):
                content = future.result()
                if not content: continue
                for page_path, child_guid in parse_entries(content):
                    entries[page_path] = child_guid
                    if child_guid not in seen:
                        seen.add(child_guid); queue.append(child_guid)
            print(f"toc-pages={len(entries)} queued-data={len(queue)} discovered-data={len(seen)}", flush=True)

    page_urls = [urljoin("https://transmodel-cen.eu/model/", path) for path in sorted(entries)]
    pages: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch_page, url): url for url in page_urls}
        for future in as_completed(futures):
            url = futures[future]
            result = future.result()
            if result is None: continue
            title, heading, payload, notes = result
            pages.append({
                "id": url,
                "title": title,
                "headings": heading,
                "text": " ".join(payload)[:20000],
                "notes": notes[:20000],
            })
        print(f"harvested-pages={len(pages)} discovered-pages={len(page_urls)}", flush=True)
    pages.sort(key=lambda page: page["id"])
    terms = []
    for page in pages:
        candidate = page["title"] or page["headings"]
        if candidate and not candidate.lower().startswith(("part ", "transmodel")):
            terms.append({"id": page["id"], "label": candidate, "definition": page.get("notes") or page["text"], "source": page["id"]})
    result = {"version": "Transmodel v6.0", "source": "published Enterprise Architect HTML", "terms": terms, "stats": {"pages": len(pages), "terms": len(terms)}}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["stats"], indent=2))


if __name__ == "__main__":
    harvest(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("transmodel-6.0-html-harvest.json"))
