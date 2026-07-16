# AM Studios — Automatizace grafiky ze Slacku

## Jak to funguje

```
#grafika kanál (Slack)
  → "Potřebuju grafiku na [téma]" + foto (volitelně)
     → Claude rozpozná pilíř, co má a co (opravdu) chybí
        → chybí povinné pole? → doptá se ve vlákně, čeká na odpověď
        → chybí jen "hezčí, ale nepovinné" pole? → zeptá se JEDNOU, ale
          po druhé zprávě pokračuje i bez odpovědi — necháká navždy
        → má dost? → vygeneruje/vyplní obsah, vyrenderuje, pošle PNG zpět
```

Stav rozhovoru (co se ví/chybí, kolikáté je to kolo) se drží ve Supabase — tabulka
`grafika_requests`. Díky tomu funguje i vícekrokové doptávání přes samostatné, krátké
Slack eventy.

## Filozofie: funkční především, ne "musí sedět přesně na šablonu"

Systém rozlišuje u každého pilíře dvě kategorie polí:

- **required** — bez těch grafika nedává smysl vůbec (typicky: fotka, lokalita).
  Bez nich se systém ptá pořád, dokud je nedostane.
- **volitelne_lepsi** — carousel bez nich funguje, jen bude o slide kratší nebo
  míň bohatý (dispozice, makléř, popis nemovitosti, služby...). Zeptá se na ně
  jednou, maximálně dvakrát, a pak POKRAČUJE s tím, co má — nečeká věčně.

Konkrétně u pilíře **Z nemovitosti**: pokud nepřijde jméno makléře, popis
nemovitosti nebo seznam služeb, příslušný slide (Makléř / O nemovitosti / Služby)
se v carouselu prostě VYNECHÁ — carousel bude mít 3, 4, 5 nebo 6+ slidů podle
toho, co reálně dostal, ne vždy přesně 6. Stejně tak dispozice (3+kk) se
nezobrazí vůbec, pokud nedává smysl (pozemek, chata, komerční prostor).

## Pilíře

| Pilíř | Povinné | Volitelně lepší | Kdo dodává obsah |
|---|---|---|---|
| Edukativní | téma | — | Claude si sám dohledá aktuální čísla (web search) a napíše celý obsah; počet slidů (typicky 5-10) volí podle šíře tématu |
| Z nemovitosti | foto, lokalita | dispozice, makléř, popis nemovitosti, služby | Alex/tým — nikdy se nevymýšlí, jen se ptá |
| BTS | fotky | headline | Alex/tým — počet slidů = počet fotek |
| Vtipné | — | téma/nálada | Claude navrhne úplně nové HTML pokaždé znovu (žádná pevná šablona), podle 2 schválených stylových vzorů |
| Mýty/srovnání | tvrzení k vyvrácení | — | Claude dohledá čísla a napíše argumentaci, proměnná délka |
| YT náhled / Shorts | foto, lokalita | dispozice, makléř | Alex/tým — stejná data jako Z nemovitosti |

## Drobnosti, co dělají systém odolnější (ne jen "hezký na papíře")

- **Ikony u seznamu služeb** se párují podle klíčového slova v názvu (foto, video,
  vizualizace, půdorys, matterport, dron) — služby jsou volný text, ne pevný seznam
- **Víc fotek u Z nemovitosti** = víc samostatných foto slidů automaticky, bez nutnosti o to žádat
- **Když se nepodaří vyrenderovat jeden konkrétní slide** (např. Claude vrátí
  neočekávaná data), přeskočí se jen ten jeden — zbytek carouselu se pořád pošle
- **Když se nepodaří nahrát jeden obrázek do Slacku**, zkusí se to ještě jednou,
  a pak se pokračuje s ostatními — jedna chyba nezahodí celou dávku
- **Nová/upravená data nikdy nepřepíšou už známá dobrá data prázdnou hodnotou** —
  toohle byl reálný bug (fotka a jméno makléře občas zmizely mezi koly konverzace),
  teď je to ošetřené

## Technický stack

- **Backend:** Python (Flask) + Slack Bolt SDK
- **Renderování:** WeasyPrint 69.0 (verze je důležitá — 62.3 má bug v `transform: rotate()`)
- **Hosting:** Railway (Docker — proto potřeba `poppler-utils` v Dockerfile pro `pdftoppm`, které Railway/Debian trixie nemá ve výchozím obraze)
- **Stav rozhovoru:** Supabase (`grafika_requests` tabulka)
- **AI vrstva:** Anthropic API — tool use pro veškerý strukturovaný výstup (nikdy ruční parsování JSON textu, to se dřív lámalo na neuzavřených uvozovkách), web search pro reálné statistiky u Edukativní/Mýty
