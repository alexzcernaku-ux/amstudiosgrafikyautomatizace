"""
Jádro automatizace: přečte zprávu (+ dosavadní nasbíraná data) a rozhodne:
- který pilíř to je
- co už víme
- co ještě chybí
- jakou doplňující otázku položit, pokud něco chybí

Používá Anthropic tool use pro strukturovaný výstup — ne parsování volného textu,
ať se to neláme na formátování.
"""
import os
import json
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Přesně ta pravidla, co máme uložená pro AM Studios — pilíře a jejich povinná pole.
PILLARS = {
    "edukativni": {
        "required": ["tema"],
        "note": "Alex dodává jen téma, zbytek (6 slidů) si Claude napíše sám z ověřených AM Studios čísel (217% ROI, 78%, 32%).",
    },
    "z_nemovitosti": {
        "required": ["foto", "dispozice", "lokalita", "makler", "nadpis_nemovitosti", "popis_nemovitosti", "sluzby"],
        "note": "Nikdy nevymýšlet služby, které se na zakázce natočily, popis nemovitosti ani citáty makléře — pokud to není řečeno, zeptat se. makler_agentura a tagy jsou nepovinné.",
    },
    "bts": {
        "required": ["fotky"],
        "note": "Potřebuje syrové fotky přímo z natáčení (pole cest k fotkám), ne hotové produkty. headline nepovinný.",
    },
    "vtipne": {
        "required": [],
        "note": "Volná ruka na vizuál i styl, nemusí to být carousel, klidně jeden obrázek. Nedržet se navy/bílé, humor může mít vlastní paletu. tema je nepovinné.",
    },
    "myty_srovnani": {
        "required": ["tvrzeni"],
        "note": "Formát: rozšířený mýtus vs. realita.",
    },
    "yt_nahled": {
        "required": ["foto", "dispozice", "lokalita", "makler"],
        "note": "Stejná data jako Z nemovitosti (jen bez nadpis_nemovitosti/popis/sluzby). Ptát se i na formát: 16:9 (náhled), 9:16 (Shorts), nebo obojí — ulož jako pole 'format' s hodnotami z ['16:9','9:16'].",
    },
}

SYSTEM_PROMPT = f"""Jsi asistent, co pro AM Studios (české studio na vizuální prezentaci nemovitostí)
třídí požadavky na grafiku přicházející ze Slacku a rozhoduje, jestli má dost informací k vyrobení grafiky.

Pilíře a jejich povinná pole:
{json.dumps(PILLARS, ensure_ascii=False, indent=2)}

Vždy volej nástroj `vyhodnotit_pozadavek`. Nikdy si nevymýšlej chybějící údaje — pokud něco
chybí, ulož ho do missing_fields a napiš přirozenou, stručnou doplňující otázku česky.
Pokud je pilíř "vtipne", missing_fields bývá typicky prázdné — tenhle pilíř nepotřebuje
skoro žádná povinná data, stačí nálada/téma, a i to je nepovinné.
"""

TOOL = {
    "name": "vyhodnotit_pozadavek",
    "description": "Zaznamená rozpoznaný pilíř, nasbíraná data, co chybí a případnou doplňující otázku.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pillar": {"type": "string", "enum": list(PILLARS.keys())},
            "extracted_data": {"type": "object", "description": "Klíč-hodnota páry rozpoznaných údajů."},
            "missing_fields": {"type": "array", "items": {"type": "string"}},
            "clarifying_question": {"type": "string", "description": "Prázdné, pokud nic nechybí."},
            "ready_to_render": {"type": "boolean"},
        },
        "required": ["pillar", "extracted_data", "missing_fields", "ready_to_render"],
    },
}


def analyze(message_text: str, has_photo: bool, previously_collected: dict) -> dict:
    """Vrátí dict: pillar, extracted_data (sloučená s previously_collected), missing_fields,
    clarifying_question, ready_to_render."""
    user_content = (
        f"Dosud nasbíraná data: {json.dumps(previously_collected, ensure_ascii=False)}\n"
        f"Nová zpráva: \"{message_text}\"\n"
        f"Zpráva má přiloženou fotku: {has_photo}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "vyhodnotit_pozadavek"},
        messages=[{"role": "user", "content": user_content}],
    )

    tool_call = next(b for b in response.content if b.type == "tool_use")
    result = tool_call.input

    # sloučit nově rozpoznaná data s tím, co už bylo nasbírané dřív
    merged = {**previously_collected, **result["extracted_data"]}
    result["extracted_data"] = merged
    return result
