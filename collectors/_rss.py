"""RSS/Atom parsing shared by written feeds and podcast feeds."""

import xml.etree.ElementTree as ET

from _common import date_utc


def child_text(node, names):
    for child in node:
        if child.tag.rsplit("}", 1)[-1].lower() in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def entries(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        link = child_text(entry, {"link"})
        enclosure = None
        transcript = None
        for node in entry:
            tag = node.tag.rsplit("}", 1)[-1].lower()
            if tag == "link":
                href = node.attrib.get("href")
                if href and (node.attrib.get("rel") in (None, "alternate")):
                    link = href
                if href and node.attrib.get("rel") == "enclosure":
                    enclosure = href
            elif tag == "enclosure":
                enclosure = node.attrib.get("url") or enclosure
            elif tag == "transcript":
                transcript = node.attrib.get("url") or transcript
        yield {
            "guid": child_text(entry, {"guid", "id"}),
            "title": child_text(entry, {"title"}),
            "url": link,
            "published_at": date_utc(child_text(entry, {"pubdate", "published", "updated", "date"})),
            "media_url": enclosure,
            "transcript_url": transcript,
        }
