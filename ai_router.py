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
# "required" jsou jen skuteční blokátoři — bez nich grafika nedává smysl vůbec.
# Všechno ostatní je "volitelné_lepší": stojí za to se na to jednou zeptat, ale
# pokud to Alex/tým nedodá ani po jednom dotazu, systém má pokračovat a udělat
# nejlepší možnou grafiku z toho, co reálně má — ne se zaseknout na čekání.
PILLARS = {
    "edukativni": {
        "required": ["tema"],
        "volitelne_lepsi": [],
        "note": "Alex dodává jen téma, zbytek (proměnný počet slidů) si Claude napíše sám, s reálně dohledanými čísly k tématu.",
    },
    "z_nemovitosti": {
        "required": ["foto", "lokalita"],
        "volitelne_lepsi": ["dispozice", "makler_jmeno", "nadpis_nemovitosti", "popis_nemovitosti", "sluzby"],
        "note": "Dispozice (3+kk apod.) se ptej, ale nikdy neblokuj — pozemky, chaty a komerční prostory ji nemusí mít, badge se pak v grafice prostě nezobrazí. Nikdy nevymýšlet služby, popis nemovitosti ani citáty makléře — pokud to není řečeno, zeptej se JEDNOU. Pokud to ani pak nepřijde, pokračuj bez toho — příslušný slide (o nemovitosti / makléř / služby) se v carouselu prostě vynechá, carousel bude jen kratší, ne že se zasekne. makler_agentura a tagy jsou čistě volitelné, bez dotazu. Víc fotek = víc foto slidů automaticky.",
    },
    "bts": {
        "required": ["fotky"],
        "volitelne_lepsi": ["headline"],
        "note": "Potřebuje syrové fotky přímo z natáčení, ne hotové produkty.",
    },
    "vtipne": {
        "required": [],
        "volitelne_lepsi": ["tema"],
        "note": "Volná ruka na vizuál i styl, nemusí to být carousel, klidně jeden obrázek. Nedržet se navy/bílé, humor může mít vlastní paletu.",
    },
    "myty_srovnani": {
        "required": ["tvrzeni"],
        "volitelne_lepsi": [],
        "note": "Formát: rozšířený mýtus vs. realita.",
    },
    "yt_nahled": {
        "required": ["foto", "lokalita"],
        "volitelne_lepsi": ["dispozice", "makler_jmeno"],
        "note": "Stejná data jako Z nemovitosti (jen bez nadpis_nemovitosti/popis/sluzby). Ptát se i na formát: 16:9 (náhled), 9:16 (Shorts), nebo obojí — ulož jako pole 'format' s hodnotami z ['16:9','9:16']. Bez dispozice/makléře se ten řádek v náhledu prostě nezobrazí.",
    },
}

SYSTEM_PROMPT = f"""Jsi asistent, co pro AM Studios (české studio na vizuální prezentaci nemovitostí)
třídí požadavky na grafiku přicházející ze Slacku a rozhoduje, jestli má dost informací k vyrobení grafiky.

Pilíře, jejich POVINNÁ pole (required, bez těch to nejde vůbec) a VOLITELNĚ_LEPŠÍ pole
(stojí za to se zeptat, ale nikdy neblokovat navždy):
{json.dumps(PILLARS, ensure_ascii=False, indent=2)}

DŮLEŽITÉ PRAVIDLO, ať se to nezasekává: pole z "required" musí být vyplněná, jinak
ready_to_render nikdy není true. Pole z "volitelne_lepsi" se OPTÁ jen v prvním kole
(kolo == 0 nebo 1) — pokud chybí a je to teprve první/druhé kolo, zeptej se na ně
spolu s tím, na co se ptáš z required. Ale jakmile je kolo 2 nebo víc a required pole
jsou všechna vyplněná, VŽDY nastav ready_to_render=true, i když volitelné pole pořád
chybí — člověk už dostal šanci to doplnit, dál se nemá čekat, systém má prostě udělat
nejlepší možnou grafiku z toho, co reálně má.

Vždy volej nástroj `vyhodnotit_pozadavek`. Nikdy si nevymýšlej chybějící údaje — pokud něco
z required chybí, ulož ho do missing_fields a napiš přirozenou, stručnou doplňující otázku česky.
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
            "extracted_data": {
                "type": "object",
                "description": "Klíč-hodnota páry rozpoznaných údajů. Použij VÝHRADNĚ tyhle názvy polí, žádné jiné — šablony hledají přesně tyhle klíče, jiný název (byť významem stejný) by se ztratil.",
                "properties": {
                    "foto": {"type": "string", "description": "Jméno souboru cover fotky (nastavuje se automaticky při stažení ze Slacku, nevymýšlet)."},
                    "fotky": {"type": "array", "items": {"type": "string"}, "description": "Seznam všech fotek (nastavuje se automaticky, nevymýšlet)."},
                    "dispozice": {"type": "string"},
                    "lokalita": {"type": "string"},
                    "makler_jmeno": {"type": "string"},
                    "makler_agentura": {"type": "string"},
                    "nadpis_nemovitosti": {"type": "string"},
                    "popis_nemovitosti": {"type": "string"},
                    "sluzby": {"type": "array", "items": {"type": "string"}},
                    "tagy": {"type": "array", "items": {"type": "string"}},
                    "tema": {"type": "string"},
                    "tvrzeni": {"type": "string"},
                    "headline": {"type": "string"},
                    "format": {"type": "array", "items": {"type": "string", "enum": ["16:9", "9:16"]}},
                },
                "additionalProperties": False,
            },
            "missing_fields": {"type": "array", "items": {"type": "string"}},
            "clarifying_question": {"type": "string", "description": "Prázdné, pokud nic nechybí."},
            "ready_to_render": {"type": "boolean"},
        },
        "required": ["pillar", "extracted_data", "missing_fields", "ready_to_render"],
    },
}


def analyze(message_text: str, has_photo: bool, previously_collected: dict, kolo: int = 0) -> dict:
    """Vrátí dict: pillar, extracted_data (sloučená s previously_collected), missing_fields,
    clarifying_question, ready_to_render. `kolo` = kolikáté kolo konverzace tohle je (0 = první
    zpráva) — používá se, aby se systém přestal ptát na volitelná pole po jednom pokusu."""
    user_content = (
        f"Dosud nasbíraná data: {json.dumps(previously_collected, ensure_ascii=False)}\n"
        f"Kolo konverzace: {kolo}\n"
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

    # Sloučit nově rozpoznaná data s tím, co už bylo nasbírané dřív — ale NIKDY
    # nepřepsat už známou hodnotu prázdnou/None. Bez týhle pojistky se stalo, že
    # fotka nebo jméno makléře z dřívějšího kola tiše zmizely, protože Claude v
    # dalším kole vrátil pro to samé pole prázdnou hodnotu, o kterou se v tu chvíli
    # nezajímal.
    merged = dict(previously_collected)
    for key, value in result["extracted_data"].items():
        if value not in (None, "", [], {}):
            merged[key] = value
    result["extracted_data"] = merged
    return result
