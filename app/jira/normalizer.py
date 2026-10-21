"""
Atlassian Document Format (ADF) Normalizer
Converts Jira Cloud rich-text ADF JSON structures into clean, structured Markdown.
"""
from typing import Any, Dict, List, Union


class ADFNormalizer:
    """Normalizes Jira Atlassian Document Format (ADF) into Markdown text."""

    @classmethod
    def to_markdown(cls, doc: Union[Dict[str, Any], str, None]) -> str:
        """
        Main entry point: Converts an ADF dict, a raw markdown string, or None
        into a clean Markdown string.
        """
        if not doc:
            return ""

        if isinstance(doc, str):
            return doc.strip()

        if not isinstance(doc, dict):
            return str(doc)

        node_type = doc.get("type")
        if node_type != "doc":
            # Might be an individual node or fragment
            return cls._render_node(doc).strip()

        content = doc.get("content", [])
        rendered_blocks = [cls._render_node(child) for child in content]
        return "\n\n".join(b for b in rendered_blocks if b.strip()).strip()

    @classmethod
    def _render_node(cls, node: Dict[str, Any]) -> str:
        node_type = node.get("type", "")
        content = node.get("content", [])

        if node_type == "text":
            text = node.get("text", "")
            marks = node.get("marks", [])
            for mark in marks:
                mark_type = mark.get("type")
                if mark_type == "strong":
                    text = f"**{text}**"
                elif mark_type == "em":
                    text = f"*{text}*"
                elif mark_type == "code":
                    text = f"`{text}`"
                elif mark_type == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
            return text

        elif node_type == "paragraph":
            return "".join(cls._render_node(c) for c in content)

        elif node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            prefix = "#" * max(1, min(level, 6))
            inner = "".join(cls._render_node(c) for c in content)
            return f"{prefix} {inner}"

        elif node_type == "bulletList":
            items = []
            for item in content:
                # item is a listItem
                item_content = "".join(cls._render_node(c) for c in item.get("content", []))
                items.append(f"- {item_content.strip()}")
            return "\n".join(items)

        elif node_type == "orderedList":
            items = []
            for i, item in enumerate(content, start=1):
                item_content = "".join(cls._render_node(c) for c in item.get("content", []))
                items.append(f"{i}. {item_content.strip()}")
            return "\n".join(items)

        elif node_type == "codeBlock":
            lang = node.get("attrs", {}).get("language", "")
            code_text = "".join(cls._render_node(c) for c in content)
            return f"```{lang}\n{code_text}\n```"

        elif node_type == "blockquote":
            inner = "\n".join(cls._render_node(c) for c in content)
            return "\n".join(f"> {line}" for line in inner.splitlines())

        elif node_type == "rule":
            return "---"

        elif node_type == "table":
            rows = [cls._render_node(c) for c in content]
            return "\n".join(r for r in rows if r.strip())

        elif node_type == "tableRow":
            cells = [cls._render_node(c) for c in content]
            return "| " + " | ".join(c.strip() for c in cells) + " |"

        elif node_type in ("tableCell", "tableHeader"):
            return "".join(cls._render_node(c) for c in content).strip()

        else:
            # Fallback: render any nested children
            return "".join(cls._render_node(c) for c in content)

