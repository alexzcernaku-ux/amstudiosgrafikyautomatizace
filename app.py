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

# Ikony pro "co jsme natočili" — služby jsou volný text (Alex/tým je nepíše z pevného
# seznamu), takže se ikona páruje podle klíčového slova v názvu, ne podle přesné shody.
_SERVICE_ICONS = [
    (["fot"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5h3.5L8 5h8l1.5 2.5H21a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V8.5a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.5" r="3.3"/></svg>'),
    (["video", "reels", "reel"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M10 9.5l6 3.5-6 3.5z" fill="white" stroke="none"/></svg>'),
    (["vizual"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="9.5" r="1.4"/><path d="M3 16l5-4.5 4 3.5 3-2.5 6 5"/></svg>'),
    (["půdorys", "pudorys", "plán", "plan"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="8" height="8"/><rect x="13" y="3" width="8" height="5"/><rect x="13" y="10" width="8" height="11"/><rect x="3" y="13" width="8" height="8"/></svg>'),
    (["matterport", "3d", "prohlídka", "prohlidka"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 3v18M4 7.5l8 4.5 8-4.5"/></svg>'),
    (["dron", "drone"], '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.3"/><circle cx="18" cy="6" r="2.3"/><circle cx="6" cy="18" r="2.3"/><circle cx="18" cy="18" r="2.3"/><path d="M8.2 7.8L11 11M15.8 7.8L13 11M8.2 16.2L11 13M15.8 16.2L13 13"/><rect x="10" y="10" width="4" height="4" rx="1"/></svg>'),
]
_ICON_FALLBACK = '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>'


def _icon_for_service(name: str) -> str:
    lower = name.lower()
    for keywords, svg in _SERVICE_ICONS:
        if any(k in lower for k in keywords):
            return svg
    return _ICON_FALLBACK


def _read_reference(name):
    path = os.path.join(TEMPLATES_DIR, "_vtipne_reference", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def download_slack_files(files: list, bot_token: str) -> list:
    """Stáhne přílohy ze Slacku a uloží je do templates/assets/, ať na ně šablony
    můžou odkazovat stejně jako na logo/texturu. Vrátí seznam uložených jmen souborů.

    Ověřuje Content-Type SKUTEČNÉ stažené odpovědi, ne jen to, co o sobě tvrdil
    Slack v metadatech zprávy — když botovi chybí OAuth scope `files:read`, Slack
    umí na `url_private` vrátit HTML/JSON chybovou stránku se statusem 200 (ne
    chybou), takže by se bez týhle kontroly tiše uložilo něco, co vůbec není obrázek."""
    saved = []
    for f in files:
        try:
            if not f.get("mimetype", "").startswith("image/"):
                continue
            ext = f["mimetype"].split("/")[-1]
            filename = f"{uuid.uuid4().hex}.{ext}"
            resp = requests.get(f["url_private"], headers={"Authorization": f"Bearer {bot_token}"})
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                print(
                    f"POZOR: stažení fotky '{f.get('name')}' vrátilo Content-Type "
                    f"'{content_type}' místo obrázku (prvních 200 znaků odpovědi: "
                    f"{resp.text[:200]!r}). Nejspíš chybí OAuth scope 'files:read' "
                    f"u Slack aplikace — přeskakuji tenhle soubor."
                )
                continue

            with open(os.path.join(ASSETS_DIR, filename), "wb") as out:
                out.write(resp.content)
            saved.append(filename)
        except Exception as e:
            print(f"Přeskakuji jednu přílohu, nepovedlo se stáhnout: {e}")
    return saved


def _render_slide_list(slides: list, name_prefix: str) -> list:
    """Vezme seznam {'type': ..., ...pole} a vyrenderuje každý slide přes odpovídající
    šablonu v templates/slides/, s doplněným slide_number/total_slides pro page indikátor.
    Když jeden konkrétní slide spadne (např. Claude vrátil pole, co šablona nečeká, nebo
    dokonce celou položku jako obyčejný text místo objektu), přeskočí se jen ten jeden —
    zbytek carouselu se pořád doručí, ne že se ztratí vše."""
    total = len(slides)
    out = []
    for i, slide in enumerate(slides):
        try:
            if not isinstance(slide, dict):
                raise TypeError(f"slide má být objekt s polem 'type', dostal jsem {type(slide).__name__}: {slide!r}")
            slide_type = slide["type"]
            template_path = f"slides/{slide_type}.html"
            render_data = {**slide, "slide_number": i + 1, "total_slides": total}
            png = renderer.render(template_path, render_data)
            out.append((f"{name_prefix}_{i+1}_{slide_type}.png", png))
        except Exception as e:
            print(f"Přeskakuji slide {i+1}, nepovedlo se vyrenderovat: {e}")
    return out


def render_pillar(pillar: str, data: dict) -> list:
    """Vrátí seznam (filename, png_bytes) pro daný pilíř. Každý pilíř má vlastní logiku,
    protože každý funguje trochu jinak (pevná data / generovaný text / volné HTML)."""

    if pillar == "yt_nahled":
        data = {**data, "photo_filename": data.get("foto")}
        out = []
        formats = data.get("format") or ["16:9"]
        if "16:9" in formats:
            out.append(("yt_nahled.png", renderer.render("yt_nahled.html", data)))
        if "9:16" in formats:
            out.append(("yt_shorts.png", renderer.render("yt_shorts.html", data)))
        return out

    if pillar == "z_nemovitosti":
        cover_photo = data.get("foto")
        fotky = data.get("fotky") or ([cover_photo] if cover_photo else [])
        if not cover_photo and fotky:
            cover_photo = fotky[0]
        # Extra foto slidy = všechny fotky KROMĚ tý, co je na coveru, v původním
        # pořadí — takže se stejná fotka nikdy neukáže dvakrát (jednou na cover,
        # znovu jako "extra").
        extra_photos = [f for f in fotky if f != cover_photo]

        sluzby_enriched = [{"nazev": s, "icon_svg": _icon_for_service(s)} for s in data.get("sluzby", [])]

        base_data = {**data, "photo_filename": cover_photo, "tagy": data.get("tagy", [])}

        # Sestavíme pořadí — carousel je teď tak dlouhý, kolik dat reálně máme.
        # Cover a statistiky (fixní obsah, nezávisí na ničem volitelném) jsou vždy.
        # "O nemovitosti", "Makléř" a "Služby" se přidají, jen když je pro ně reálně
        # co ukázat — jinak by to byl prázdný nebo nesmyslný slide.
        plan = [("z_nemovitosti_cover.html", base_data)]
        for foto in extra_photos:
            plan.append(("z_nemovitosti_photo.html", {"photo_filename": foto}))
        if data.get("nadpis_nemovitosti") or data.get("popis_nemovitosti"):
            plan.append(("z_nemovitosti_2.html", base_data))
        plan.append(("z_nemovitosti_3.html", base_data))
        if data.get("makler_jmeno"):
            plan.append(("z_nemovitosti_4.html", base_data))
        if sluzby_enriched:
            plan.append(("z_nemovitosti_5.html", {**base_data, "sluzby": sluzby_enriched}))
        plan.append(("z_nemovitosti_6.html", base_data))

        total = len(plan)
        out = []
        for i, (template_name, slide_data) in enumerate(plan):
            render_data = {**slide_data, "slide_number": i + 1, "total_slides": total}
            try:
                out.append((f"z_nemovitosti_{i+1}.png", renderer.render(template_name, render_data)))
            except Exception as e:
                print(f"Přeskakuji slide {i+1} ({template_name}), nepovedlo se vyrenderovat: {e}")
        return out

    if pillar == "edukativni":
        slides = content_generator.generate_edukativni(data["tema"])
        return _render_slide_list(slides, "edukativni")

    if pillar == "myty_srovnani":
        slides = content_generator.generate_myty(data["tvrzeni"])
        return _render_slide_list(slides, "myty")

    if pillar == "bts":
        fotky = data.get("fotky", [])
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

    try:
        _handle_message_inner(event, client, thread_ts, channel_id)
    except Exception as e:
        # Cokoliv nečekaného kdekoliv v celém zpracování (výpadek Supabase, AI
        # volání, cokoliv) — ať o tom ve Slacku víme, místo aby to zmizelo jen
        # v Railway logu a vypadalo to, že bot vůbec nereagoval.
        print(f"Neočekávaná chyba při zpracování zprávy: {e}")
        try:
            client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts,
                text=f"Něco se pokazilo: `{e}`. Zkontroluj prosím logy v Railway.",
            )
        except Exception:
            pass  # i tohle může selhat (např. výpadek Slack API samotného) — nedělat z toho další pád
        raise


def _handle_message_inner(event, client, thread_ts, channel_id):
    # Když někdo zprávu ve Slacku upraví (např. dodatečně přiloží fotku), přijde to
    # jako subtype "message_changed" a text/files jsou schované o úroveň níž, pod
    # event["message"], ne přímo v event — bez tohohle rozlišení by taková fotka
    # zmizela úplně stejně jako ten bug s přepisováním prázdnou hodnotou.
    if event.get("subtype") == "message_changed":
        inner = event.get("message", {})
        text = inner.get("text", "")
        files = inner.get("files", [])
    else:
        text = event.get("text", "")
        files = event.get("files", [])

    req = state.get_or_create(thread_ts, channel_id)
    collected = req["collected_data"]
    kolo = collected.get("_kolo", 0)

    if files:
        saved_filenames = download_slack_files(files, os.environ["SLACK_BOT_TOKEN"])
        if saved_filenames:
            # "foto" = fotka na cover, musí zůstat ta úplně první, co kdy přišla —
            # dřív se tu přepisovala při každé další zprávě s přílohou, takže cover
            # nakonec dostal poslední fotku, ne první. "fotky" (celý seznam, v pořadí)
            # se pořád přirůstá normálně.
            if not collected.get("foto"):
                collected["foto"] = saved_filenames[0]
            collected["fotky"] = collected.get("fotky", []) + saved_filenames

    result = ai_router.analyze(
        message_text=text,
        has_photo=bool(files),
        previously_collected=collected,
        kolo=kolo,
    )
    result["extracted_data"]["_kolo"] = kolo + 1

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
        print(f"Chyba při renderování: {e}")
        return

    if not files_out:
        client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts,
            text="Nepovedlo se vyrenderovat ani jeden slide. Zkontroluj prosím logy v Railway.",
        )
        return

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
