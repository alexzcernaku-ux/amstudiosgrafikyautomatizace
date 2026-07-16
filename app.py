"""
Vstupní bod. Naslouchá zprávám v kanálu #grafika, prochází cyklem
sbírat data → doptat se → vyrenderovat → poslat zpět do vlákna.

Proměnné prostředí (nastav v Railway):
  SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
  ANTHROPIC_API_KEY
  SUPABASE_URL, SUPABASE_SERVICE_KEY
  GRAFIKA_CHANNEL_ID (volitelné — když chybí, bot reaguje ve všech kanálech, kam ho pozveš)
"""
import os
import uuid
import requests
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

import ai_router
import content_generator
import state
import renderer

slack_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
)
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)

GRAFIKA_CHANNEL_ID = os.environ.get("GRAFIKA_CHANNEL_ID")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
ASSETS_DIR = os.path.join(TEMPLATES_DIR, "assets")


def _read_reference(name):
    path = os.path.join(TEMPLATES_DIR, "_vtipne_reference", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def download_slack_files(files: list, bot_token: str) -> list:
    """Stáhne přílohy ze Slacku (potřebují auth hlavičku, jinak vrátí HTML login stránku
    místo obrázku) a uloží je do templates/assets/, ať na ně šablony můžou odkazovat
    stejně jako na logo/texturu. Vrátí seznam uložených jmen souborů."""
    saved = []
    for f in files:
        if not f.get("mimetype", "").startswith("image/"):
            continue
        ext = f["mimetype"].split("/")[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"
        resp = requests.get(f["url_private"], headers={"Authorization": f"Bearer {bot_token}"})
        resp.raise_for_status()
        with open(os.path.join(ASSETS_DIR, filename), "wb") as out:
            out.write(resp.content)
        saved.append(filename)
    return saved


def _render_slide_list(slides: list, name_prefix: str) -> list:
    """Vezme seznam {'type': ..., ...pole} a vyrenderuje každý slide přes odpovídající
    šablonu v templates/slides/, s doplněným slide_number/total_slides pro page indikátor."""
    total = len(slides)
    out = []
    for i, slide in enumerate(slides):
        slide_type = slide["type"]
        template_path = f"slides/{slide_type}.html"
        render_data = {**slide, "slide_number": i + 1, "total_slides": total}
        png = renderer.render(template_path, render_data)
        out.append((f"{name_prefix}_{i+1}_{slide_type}.png", png))
    return out


def render_pillar(pillar: str, data: dict) -> list:
    """Vrátí seznam (filename, png_bytes) pro daný pilíř. Každý pilíř má vlastní logiku,
    protože každý funguje trochu jinak (pevná data / generovaný text / volné HTML)."""

    if pillar == "yt_nahled":
        data = {**data, "photo_filename": data["foto"]}
        out = []
        formats = data.get("format") or ["16:9"]
        if "16:9" in formats:
            out.append(("yt_nahled.png", renderer.render("yt_nahled.html", data)))
        if "9:16" in formats:
            out.append(("yt_shorts.png", renderer.render("yt_shorts.html", data)))
        return out

    if pillar == "z_nemovitosti":
        data = {**data, "photo_filename": data["foto"], "tagy": data.get("tagy", [])}
        names = ["z_nemovitosti_cover", "z_nemovitosti_2", "z_nemovitosti_3",
                 "z_nemovitosti_4", "z_nemovitosti_5", "z_nemovitosti_6"]
        return [(f"{n}.png", renderer.render(f"{n}.html", data)) for n in names]

    if pillar == "edukativni":
        slides = content_generator.generate_edukativni(data["tema"])
        return _render_slide_list(slides, "edukativni")

    if pillar == "myty_srovnani":
        slides = content_generator.generate_myty(data["tvrzeni"])
        return _render_slide_list(slides, "myty")

    if pillar == "bts":
        fotky = data["fotky"]
        total = len(fotky) + 2  # cover + fotky + cta
        out = [("bts_1_cover.png", renderer.render("bts_cover.html", {
            "photo_filenames": fotky, "headline": data.get("headline"), "total_slides": total,
        }))]
        for i, foto in enumerate(fotky):
            out.append((f"bts_{i+2}.png", renderer.render("bts_photo.html", {
                "photo_filename": foto,
                "caption": data.get("captions", [None] * len(fotky))[i] if data.get("captions") else None,
                "slide_number": i + 2,
                "total_slides": total,
            })))
        out.append((f"bts_{total}_cta.png", renderer.render("bts_cta.html", {})))
        return out

    if pillar == "vtipne":
        example1 = _read_reference("bingo.html")
        example2 = _read_reference("tabloid.html")
        html = content_generator.generate_vtipne(data.get("tema", ""), example1, example2)
        return [("vtipne.png", renderer.render_raw_html(html))]

    raise ValueError(f"Neznámý pilíř: {pillar}")


@slack_app.event("message")
def handle_message(event, client):
    if event.get("bot_id"):
        return
    if GRAFIKA_CHANNEL_ID and event.get("channel") != GRAFIKA_CHANNEL_ID:
        return

    thread_ts = event.get("thread_ts") or event["ts"]
    channel_id = event["channel"]
    text = event.get("text", "")
    files = event.get("files", [])

    req = state.get_or_create(thread_ts, channel_id)
    collected = req["collected_data"]

    if files:
        saved_filenames = download_slack_files(files, os.environ["SLACK_BOT_TOKEN"])
        if saved_filenames:
            # foto pro pilíře s jednou fotkou, fotky pro BTS (víc fotek) — necháme obojí
            # v datech, render_pillar si vezme jen to, co jeho pilíř potřebuje
            collected["foto"] = saved_filenames[0]
            collected["fotky"] = collected.get("fotky", []) + saved_filenames

    result = ai_router.analyze(
        message_text=text,
        has_photo=bool(files),
        previously_collected=collected,
    )

    state.update_request(
        thread_ts,
        pillar=result["pillar"],
        collected_data=result["extracted_data"],
        status="hotovo" if result["ready_to_render"] else "sbírání_dat",
    )

    if not result["ready_to_render"]:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=result.get("clarifying_question") or "Můžeš mi ještě doplnit pár detailů?",
        )
        return

    client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="Dík, mám vše — dělám grafiku...")

    try:
        files_out = render_pillar(result["pillar"], result["extracted_data"])
    except Exception as e:
        client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts,
            text=f"Nepovedlo se to vyrenderovat, tohle je chyba: `{e}`. Zkontroluj prosím logy v Railway.",
        )
        raise

    failed = []
    for filename, png_bytes in files_out:
        for attempt in range(2):  # jeden pokus o opakování, Slack API umí občas krátce zakolísat
            try:
                client.files_upload_v2(channel=channel_id, thread_ts=thread_ts, file=png_bytes, filename=filename)
                break
            except Exception as e:
                if attempt == 1:
                    failed.append((filename, str(e)))

    if failed:
        names = ", ".join(f for f, _ in failed)
        client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts,
            text=f"Zbytek se povedl, ale tohle se nepodařilo nahrát ani na druhý pokus: {names}. Zkus prosím zopakovat celý požadavek.",
        )


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    flask_app.run(port=int(os.environ.get("PORT", 8080)))
