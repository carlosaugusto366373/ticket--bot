import io
import html
from datetime import datetime


def build_transcript_html(ticket_row, messages, guild_name: str) -> io.BytesIO:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Ticket #{ticket_row['id']}</title>",
        "<style>",
        "body{background:#1e1f22;color:#dbdee1;font-family:Arial,sans-serif;",
        "padding:24px;max-width:900px;margin:auto}",
        "h1{color:#5865f2}",
        ".meta{background:#2b2d31;padding:12px;border-radius:8px;margin-bottom:20px}",
        ".msg{background:#313338;padding:10px 14px;border-radius:6px;",
        "margin:8px 0;white-space:pre-wrap;word-wrap:break-word}",
        ".bot{background:#2b2d31;border-left:3px solid #5865f2}",
        ".author{color:#f2f3f5;font-weight:bold;font-size:0.9em}",
        ".time{color:#949ba4;font-size:0.75em;margin-left:8px}",
        "</style></head><body>",
        f"<h1>Ticket #{ticket_row['id']} — {html.escape(ticket_row['category'])}</h1>",
        "<div class='meta'>",
        f"<p><b>Servidor:</b> {html.escape(guild_name)}</p>",
        f"<p><b>Usuário:</b> {ticket_row['user_id']}</p>",
        f"<p><b>Status:</b> {ticket_row['status']}</p>",
        f"<p><b>Criado em:</b> {ticket_row['created_at']}</p>",
        f"<p><b>Fechado em:</b> {ticket_row['closed_at'] or '—'}</p>",
        "</div>",
    ]
    for m in messages:
        cls = "msg bot" if m["is_bot"] else "msg"
        author = "🤖 IA" if m["is_bot"] else f"ID {m['author_id']}"
        parts.append(
            f"<div class='{cls}'>"
            f"<span class='author'>{author}</span>"
            f"<span class='time'>{m['created_at']}</span>"
            f"<div>{html.escape(m['content'])}</div></div>"
        )
    parts.append("</body></html>")

    buf = io.BytesIO("".join(parts).encode("utf-8"))
    buf.seek(0)
    return buf