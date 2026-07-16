"""
Zatímco ai_router.py rozhoduje KTERÝ pilíř a co CHYBÍ, tenhle modul píše
samotný OBSAH pro pilíře, kde ho Alex nedodává (Edukativní, Mýty, Vtipné).

Edukativní a Mýty teď vrací PROMĚNLIVÝ počet slidů — jednoduché téma dostane
kratší carousel, širší/složitější téma delší. Skládají se z knihovny opakovaně
použitelných typů slidů (templates/slides/), ne z pevné šestky.

Než napíše obsah, Claude si k tématu reálně dohledá aktuální čísla přes web search
(server-side nástroj Anthropicu) — nedrží se pořád jen tří pevných čísel, ta slouží
jako záložní jistota, pokud se k tématu nic lepšího nenajde.
"""
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

AM_STUDIOS_FACTS = """Záložní ověřená čísla AM Studios (použij, pokud web search
nenajde nic lepšího/aktuálnějšího k danému tématu — nikdy si nevymýšlej čísla ani
zdroje mimo tohle nebo mimo to, co si reálně dohledáš):
- 217 % — průměrná návratnost investice do profesionální vizuální prezentace (Zdroj: Hypoindex, červen 2024)
- 78 % — kupujících rozhoduje podle fotek dřív, než si přečte popis nemovitosti (Zdroj: Realitan)
- 32 % — rychlejší prodej u nemovitostí s profesionální fotoprezentací (Zdroj: Realitan)"""

RESEARCH_INSTRUCTION = """Než začneš psát obsah, POUŽIJ web search a dohledej si
aktuální, k tématu relevantní statistiku (realitní trh, fotografie/video nemovitostí,
prodejnost, chování kupujících apod.) — nespoléhej automaticky na ty samé tři čísla
pořád dokola, hledej něco, co sedí přímo k danému tématu. Cituj přesně zdroj, co jsi
našel (název a datum, pokud ho stránka uvádí). Pokud nic použitelného nenajdeš,
teprve pak sáhni po záložních číslech výš. Nikdy nic nevymýšlej ani neuváděj zdroj,
který jsi reálně neviděl ve výsledcích hledání."""

# Popis dostupných typů slidů — musí přesně sedět s templates/slides/*.html
SLIDE_TYPES = """Dostupné typy slidů (pole "type") a jejich POVINNÁ pole:

- "stat_cover": eyebrow (max 30 znaků), stat (max 6 znaků, např. "78 %"), stat_popis
  (max 90 znaků, 2 řádky), zdroj (nepovinné, ale pokud cituješ číslo, vždy vyplň)
- "quote_cover": eyebrow (max 25 znaků, nepovinné), quote (max 42 znaků!! delší text
  se zalomí a najede do razítka), stamp_label (max 10 znaků, nepovinné, default "Mýtus")
- "text_highlight": nadpis (max 45 znaků), text (max 140 znaků), zvyrazneni (nepovinné,
  max 70 znaků)
- "list_x": nadpis (max 45 znaků), body (pole 3-4 položek, každá max 55 znaků)
- "titled_list": nadpis (max 45 znaků), body (pole 3 objektů {title, text}, title max
  25 znaků, text max 75 znaků)
- "checklist": nadpis (max 45 znaků), body (pole 4-6 krátkých položek, každá max 35 znaků)
- "comparison": nadpis (max 45 znaků), label_spatne (max 15 znaků, default "Mýtus"),
  body_spatne (pole 3 položek, max 50 znaků), label_dobre (max 15 znaků, default "Realita"),
  body_dobre (pole 3 položek, max 50 znaků)
- "cta": nadpis (max 40 znaků), text (max 130 znaků)

Tyhle délkové limity jsou vyladěné na skutečné rozestupy v šablonách přes reálné
testování — dodržuj je přesně, delší text se v šabloně přeleje a překryje s dalším prvkem."""

SLIDES_TOOL = {
    "name": "vratit_slidy",
    "description": "Vrátí finální seznam slidů pro Instagram carousel. Volej až po dohledání relevantní statistiky.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": [
                            "stat_cover", "quote_cover", "text_highlight", "list_x",
                            "titled_list", "checklist", "comparison", "cta",
                        ]},
                        "eyebrow": {"type": "string"},
                        "stat": {"type": "string"},
                        "stat_popis": {"type": "string"},
                        "zdroj": {"type": "string"},
                        "quote": {"type": "string"},
                        "stamp_label": {"type": "string"},
                        "nadpis": {"type": "string"},
                        "text": {"type": "string"},
                        "zvyrazneni": {"type": "string"},
                        "body": {"type": "array", "items": {}},
                        "label_spatne": {"type": "string"},
                        "body_spatne": {"type": "array", "items": {"type": "string"}},
                        "label_dobre": {"type": "string"},
                        "body_dobre": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["type"],
                },
            }
        },
        "required": ["slides"],
    },
}

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}


def _call_and_parse(system: str, user_message: str) -> dict:
    """Dvoufázově: 1) necháme Claude volně hledat na webu a přemýšlet (web_search je
    server-side nástroj, Anthropic ho vyřídí sám v rámci téhož volání), 2) jakmile
    je připravený, zavolá vratit_slidy. Pokud by to sám neudělal (jen by dohledal a
    přestal), druhým, vynuceným voláním si finální strukturu stejně vyžádáme —
    takže výstup je vždy syntakticky validní JSON, nikdy ruční parsování textu."""
    messages = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=system,
        tools=[WEB_SEARCH_TOOL, SLIDES_TOOL],
        messages=messages,
    )

    tool_call = next((b for b in response.content if b.type == "tool_use" and b.name == "vratit_slidy"), None)
    if tool_call:
        return tool_call.input

    # Claude dohledával/přemýšlel, ale sám nezavolal finální nástroj — dotáhneme to
    # jedním dalším, tentokrát vynuceným voláním, se vším, co už zatím ví.
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": "Teď na základě toho, co jsi zjistil, zavolej vratit_slidy."})
    response2 = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=system,
        tools=[SLIDES_TOOL],
        tool_choice={"type": "tool", "name": "vratit_slidy"},
        messages=messages,
    )
    tool_call2 = next(b for b in response2.content if b.type == "tool_use")
    return tool_call2.input


def generate_edukativni(tema: str) -> list:
    """Vrátí seznam slidů (proměnlivá délka) pro edukativní carousel."""
    system = f"""Píšeš vzdělávací Instagram carousel pro AM Studios (české studio na
vizuální prezentaci nemovitostí — foto, video, 3D, vizualizace pro realitní makléře).

{RESEARCH_INSTRUCTION}

{AM_STUDIOS_FACTS}

{SLIDE_TYPES}

Tón: přímý, sebevědomý, věcný. NIKDY nemluv o makléřích shazujícím způsobem — vždy
rámuj kolem příležitosti a výsledků, ne selhání.

KOLIK SLIDŮ: podle šíře tématu, ne pevně. Úzké, jednoduché téma (jeden konkrétní úhel,
např. "fotka rozhoduje jako první") → 5-6 slidů. Širší nebo composed téma (víc
podtémat, např. "vše o vizuální prezentaci nemovitostí") → 8-10 slidů, ale POŘÁD
každý jednotlivý slide musí dodržet svůj délkový limit — víc obsahu znamená víc
slidů, ne nabité slidy.

STRUKTURA: první slide je vždy "stat_cover", poslední vždy "cta". Mezi tím libovolná
kombinace ostatních typů, co dává smysl pro dané téma."""

    return _call_and_parse(system, f"Téma: {tema}")["slides"]


def generate_myty(tvrzeni: str) -> list:
    """Vrátí seznam slidů pro carousel vyvracející mýtus."""
    system = f"""Píšeš Instagram carousel pro AM Studios vyvracející realitní mýtus.

{RESEARCH_INSTRUCTION}

{AM_STUDIOS_FACTS}

{SLIDE_TYPES}

KOLIK SLIDŮ: podle složitosti mýtu. Jednoduchý, jasně vyvratitelný mýtus → 5-6 slidů.
Mýtus, co potřebuje víc argumentů/kontextu → 7-9 slidů.

STRUKTURA: první slide vždy "quote_cover" (s citací mýtu), hned po něm nebo brzy
"comparison" (mýtus vs. realita), poslední vždy "cta". Mezi tím libovolná kombinace
ostatních typů pro rozvinutí argumentace."""

    return _call_and_parse(system, f"Mýtus k vyvrácení: {tvrzeni}")["slides"]


VTIPNE_SYSTEM = """Navrhuješ jeden vtipný Instagram post pro AM Studios (české studio na
vizuální prezentaci nemovitostí). Tenhle pilíř má výslovně volnou ruku na vizuál —
NEDRŽÍ se navy/bílé palety AM Studios, může mít vlastní barvy, energii, formát.
Humor musí být skutečně vtipný, ne jen "hezčí verze reklamy" — přehánění, absurdita,
tabloidní/meme formáty fungují líp než uhlazený vtip.

Musíš vrátit KOMPLETNÍ, sám o sobě fungující HTML soubor (1080×1080px, @page pravidlo,
Poppins font, cesty k assets jako "assets/logo_navy.png" / "assets/logo_white.png" /
"assets/texture_ad.png" / "assets/icon_white.png" — tyhle 4 soubory jsou jediné
dostupné obrázky, nepoužívej žádné jiné).

Tady jsou dvě schválené ukázky stylu — NEKOPÍRUJ je doslova, ale drž se podobné
úrovně vizuální jistoty a přímočarosti:

--- UKÁZKA 1 (formát: relatable listicle) ---
{example1}

--- UKÁZKA 2 (formát: tabloidní titulek) ---
{example2}

Vrať POUZE hotový HTML kód, nic jiného — žádné vysvětlení před ani po."""


def generate_vtipne(tema: str, example1_html: str, example2_html: str) -> str:
    """Vrátí kompletní HTML string, co jde přímo do renderer.render_raw_html()."""
    system = VTIPNE_SYSTEM.format(example1=example1_html, example2=example2_html)
    user_msg = f"Téma/nálada: {tema}" if tema else "Vymysli vlastní téma z realitního/fotografického prostředí."

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3072,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    html = response.content[0].text.strip()
    html = html.removeprefix("```html").removeprefix("```").removesuffix("```").strip()
    return html
