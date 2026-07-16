# AM Studios — Grafika ze Slacku (automatizace)

**Stav: nasazené a běžící.** Tenhle balíček je aktualizace poté, co jsme spolu
prošli ostrým provozem a doladili reálné chyby (viz "Co se opravilo" níže) a
udělali systém pružnější, ať se nezasekává na chybějících nepovinných údajích.

## Co dělá a jak

```
#grafika kanál (Slack)
  → "Potřebuju grafiku na [téma]" + foto (volitelně)
     → Claude rozpozná pilíř, co má a co (opravdu) chybí
        → chybí povinné pole? → doptá se, čeká
        → chybí jen "hezčí, ale nepovinné" pole? → zeptá se nejvýš 2×, pak
          pokračuje bez toho — carousel bude jen o slide kratší
        → má dost? → vygeneruje/vyplní obsah, vyrenderuje, pošle PNG zpět
```

**6 pilířů**, podrobný popis toho, co je u kterého povinné a co jen "hezčí, když
je", je v `ARCHITEKTURA.md`.

## Nasazení (pro připomenutí, pokud stavíš znovu od nuly)

1. **Slack App:** Bot Token Scopes `chat:write`, `files:write`, `files:read`, `channels:history`,
   `channels:read`; Event Subscriptions zapnuté → `message.channels`; bota
   pozvaného do #grafika; zkopírovaný Bot Token + Signing Secret + Channel ID
2. **Supabase tabulka:**
   ```sql
   create table if not exists grafika_requests (
     id uuid primary key default gen_random_uuid(),
     thread_ts text not null unique,
     channel_id text not null,
     pillar text,
     collected_data jsonb not null default '{}',
     status text not null default 'sbírání_dat',
     created_at timestamptz not null default now(),
     updated_at timestamptz not null default now()
   );
   ```
   Potřebuješ `service_role` key, ne `anon`.
3. **Railway:** nahraj do GitHub repa → Deploy from repo → Variables:
   `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY`, `GRAFIKA_CHANNEL_ID` → Generate Domain → dopiš Request
   URL do Slack App (`.../slack/events`)

## Co se v ostrém provozu opravilo (ať víš, na co si dát pozor, kdyby se to vrátilo)

- **WeasyPrint musí být 69.0**, ne 62.3 — starší verze má bug v `transform: rotate()`
  a spadne na `'super' object has no attribute 'transform'`
- **Dockerfile potřebuje `poppler-utils`** (kvůli `pdftoppm`) a správný název
  `libgdk-pixbuf-2.0-0` (ne `libgdk-pixbuf2.0-0` — to je starší, dnes už neexistující název balíčku)
- **Gunicorn timeout je 300s** — delší carousely (víc AI volání + renderování +
  uploadů) by se jinak zabily uprostřed práce
- **Fotka/jméno makléře se občas ztrácely mezi koly konverzace** — opraveno v
  logice slučování dat (prázdná hodnota z nového kola už nikdy nepřepíše dřív
  známou dobrou hodnotu)
- **Chyběl OAuth scope `files:read`** — bez něj bot sice VIDÍ, že zpráva má
  přílohu, ale nemá právo si ji reálně stáhnout ze Slacku. Slack v tom případě
  na stažení může vrátit chybovou stránku se statusem 200 (ne chybu), takže se
  to bez kontroly tiše uložilo, jako by to fotka byla — proto grafiky vycházely
  s prázdnou navy plochou místo fotky. **Musíš přidat scope ručně** (viz krok 1
  výše) **a appku v workspace znovu nainstalovat** — jen přidání scope samo o
  sobě nestačí, Slack vyžaduje reinstall, aby se nové právo projevilo. Kód teď
  navíc kontroluje, jestli stažená data fakt vypadají jako obrázek, a pokud ne,
  napíše to jasně do Railway logů, místo aby to tiše prošlo.
- **Fotky se ořezávaly/zvětšovaly** — šablony je natahovaly přes celou plochu
  slidu (jiný poměr stran než skutečné fotky). Cover a foto slidy teď mají
  fotku v rámečku se stejným poměrem (3:2) jako reálné fotky, takže se vejde
  celá, bez ořezu.
- **Cover fotka se měnila podle poslední zprávy, ne podle první** — opraveno,
  cover teď natrvalo drží tu úplně první fotku, co kdy do vlákna přišla.
- **Jméno makléře úplně chybělo** — v konfiguraci pro AI bylo pole pojmenované
  jinak (`makler`) než v šablonách (`makler_jmeno`), takže se ztrácelo. Navíc
  je teď schéma pro AI přísnější (`additionalProperties: false`) — Claude smí
  použít jen přesně vyjmenované názvy polí, ne si vymyslet vlastní, což by
  tenhle typ chyby mělo do budoucna úplně vyloučit.
- **`update_request` posílal do Supabase text `"now()"`** místo skutečného
  data — přes REST API (na rozdíl od přímého SQL) to Postgres nebere jako
  platnou funkci, takže by to teoreticky shazovalo každou aktualizaci stavu
  konverzace. Opraveno na skutečný vypočítaný časový údaj.
- **Chyby na začátku zpracování (výpadek Supabase, AI volání) mizely potichu**
  — teď je celé zpracování zprávy obalené tak, že cokoliv nečekaného pošle
  aspoň stručnou chybovou hlášku do Slacku, místo aby to vypadalo, že bot
  vůbec nereagoval.

## Otestuj po každém nasazení

```
Potřebuju grafiku na Mělník, 3+kk, makléř Martin Dadík, natočili jsme foto a video
```
+ přiložená fotka. Očekávej: "Dík, mám vše — dělám grafiku..." a během ~10-20s
sadu PNG do vlákna.

Zkus i minimální verzi bez extra údajů (`Potřebuju grafiku na Mělník` + fotka) —
carousel by měl vyjít kratší (cover + statistiky + CTA), ne se zaseknout na
dotazech donekonečna.

Pokud něco nesedí, pošli mi screenshot chybové hlášky (Railway → Deployments → Logs).

## Poznámka k nákladům

Každý požadavek dělá 1-3 volání Anthropic API (routing, případně research + generování
obsahu). Delší edukativní/mýty carousely stojí o něco víc než krátké. Řádově jde o
haléře až jednotky korun na požadavek.
